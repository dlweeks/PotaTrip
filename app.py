#!/usr/bin/python3
# POTATrip — POTA Trip Planner (Flask backend)
#
# SPDX-License-Identifier: CDDL-1.1
#
# This Source Code Form is subject to the terms of the
# Common Development and Distribution License, Version 1.1
# (the "License"). You may not use this file except in
# compliance with the License.
#
# You can obtain a copy of the License at
#     https://spdx.org/licenses/CDDL-1.1.txt
# or see the LICENSE file distributed with this project.
# See the License for the specific language governing
# permissions and limitations under the License.
#
# Copyright (c) 2026 Don L. Weeks, N5SKT <Don.L.Weeks@gmail.com>.
# All Rights Reserved.
#
# ---------------------------------------------------------------------------
# VERSION HISTORY
# ---------------------------------------------------------------------------
# 1.0.0  2026-09-11  Initial commit of PotaTrip web application.
# 1.1.0  2026-09-18  Trip-planning algorithm iterations; radius filtering.
# 1.2.0  2026-09-21  Fixed time-constraint algorithm; Purtis Creek inclusion.
# 1.2.1  2026-09-26  Hour-handling fix; work on ignoring inactive parks.
# 1.3.0  2026-09-29  Fixed trip math; filter inactive parks (active==1);
#                    hardened cache (atomic writes, locks, timeouts),
#                    geocoding (polite UA) and request validation.
# 1.4.0  2026-09-29  Debian packaging, systemd deployment and
#                    44net/CGNAT hosting documentation.
# 1.5.0  2026-09-29  Freeform location entry: one field, worldwide,
#                    no dropdown (legacy city+state API retained).
# 1.5.1  2026-09-29  Reject non-settlement geocode matches: invalid city
#                    names like "Manta, TX" no longer resolve to unrelated
#                    street/POI coordinates (fixes phantom park results).
# 1.6.0  2026-09-29  Relicensed under CDDL 1.1; version history added.
#                    Author callsign N5SKT credited in headers and UI.
# 1.7.0  2026-09-29  Security hardening from code review:
#                    - per-IP rate limiting on /plan_trip (DoS guard)
#                    - bounded geocode cache (LRU, no memory exhaustion)
#                    - caps on radius/hours/miles (CPU DoS guard)
#                    - location length cap + control-char stripping
#                    - security headers (CSP, X-Frame-Options, nosniff)
#                    - default cache/log paths moved off shared /tmp
#                    - /health no longer discloses the cache file path
# ---------------------------------------------------------------------------
"""
POTA Trip Planner — Flask backend.

Plans Parks on the Air activation trips from a city: filters the POTA park
database by radius / trip-hours / trip-miles, greedily builds a multi-park
route that fits the budget (including the drive home), and returns a
Google Maps directions URL with the parks as ordered waypoints.
"""
import io
import math
import os
import re
import sys
import time
import logging
import threading
from urllib.parse import quote
from datetime import datetime, timedelta

import pandas as pd
import requests
from flask import Flask, request, jsonify, render_template_string
from geopy.distance import geodesic
from geopy.geocoders import Nominatim

# ---------------------------------------------------------------- constants
APP_VERSION = "1.7.0"             # keep in sync with VERSION HISTORY above
AVG_SPEED_MPH = 40.0          # assumed average driving speed
ACTIVATION_HOURS = 2.0        # time spent at the park activating
CACHE_MAX_AGE_DAYS = 7
DEFAULT_RADIUS_MILES = 100.0
MAX_MAP_WAYPOINTS = 10        # parks included in the Google Maps route
POTA_CSV_URL = "https://pota.app/all_parks_ext.csv"

# Security limits (see VERSION HISTORY 1.7.0).
MAX_RADIUS_MILES = 500.0      # beyond this the whole-planet scan is a DoS
MAX_TRIP_HOURS = 72.0         # sane upper bounds for user budgets
MAX_TRIP_MILES = 3000.0
MAX_LOCATION_LEN = 200        # chars; longer is abuse, not a place name
GEOCODE_CACHE_MAX = 1000      # LRU cap: attacker-controlled keys, bound it
RATE_LIMIT_MAX = 30           # /plan_trip requests per window per IP
RATE_LIMIT_WINDOW_S = 60.0

# Default off shared /tmp (symlink risk on multi-user hosts); override with
# POTA_CACHE_FILE / POTA_LOG_FILE (the systemd unit already does).
_USER_CACHE_DIR = os.path.join(
    os.environ.get("XDG_CACHE_HOME",
                  os.path.join(os.path.expanduser("~"), ".cache")),
    "potatrip")
os.makedirs(_USER_CACHE_DIR, exist_ok=True)
CACHE_FILE = os.environ.get(
    "POTA_CACHE_FILE", os.path.join(_USER_CACHE_DIR, "all_parks_ext.csv"))
LOG_FILE = os.environ.get(
    "POTA_LOG_FILE", os.path.join(_USER_CACHE_DIR, "pota_trip_log.txt"))
NOMINATIM_UA = os.environ.get(
    "POTA_GEOCODE_UA",
    "PotaTripPlanner/2.0 (amateur radio trip planner; run locally)",
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

_cache_lock = threading.Lock()
_geocode_cache = {}


class _LRUGeocodeCache:
    """Bounded geocode cache: attacker-controlled keys can't exhaust memory.

    Dict + move-to-end on hit; evicts oldest beyond GEOCODE_CACHE_MAX.
    Guarded by its own lock (safe under Flask's threaded server).
    """

    def __init__(self, maxsize):
        self._data = {}
        self._order = []
        self._max = maxsize
        self._lock = threading.Lock()

    def get(self, key, default=None):
        with self._lock:
            if key in self._data:
                try:
                    self._order.remove(key)
                except ValueError:
                    pass
                self._order.append(key)
                return self._data[key]
            return default

    def __getitem__(self, key):
        with self._lock:
            return self._data[key]

    def __setitem__(self, key, value):
        self.set(key, value)

    def __contains__(self, key):
        with self._lock:
            return key in self._data

    def set(self, key, value):
        with self._lock:
            if key in self._data:
                try:
                    self._order.remove(key)
                except ValueError:
                    pass
            elif len(self._data) >= self._max:
                oldest = self._order.pop(0)
                self._data.pop(oldest, None)
            self._data[key] = value
            self._order.append(key)

    def clear(self):
        with self._lock:
            self._data.clear()
            self._order.clear()

    def __len__(self):
        with self._lock:
            return len(self._data)


_geocode_cache = _LRUGeocodeCache(GEOCODE_CACHE_MAX)


class _RateLimiter:
    """Fixed-window per-key rate limiter (per-IP). Thread-safe, no deps.

    Returns True if the request is allowed, False if over the limit.
    Old windows are pruned on each check so memory stays bounded by the
    number of active IPs.
    """

    def __init__(self, max_requests, window_s):
        self._max = max_requests
        self._window = window_s
        self._hits = {}   # key -> [timestamps]
        self._lock = threading.Lock()

    def allow(self, key):
        now = time.monotonic()
        with self._lock:
            # Prune stale entries globally (cheap: bounded by active IPs).
            stale = [k for k, ts in self._hits.items()
                     if not ts or now - ts[-1] > self._window]
            for k in stale:
                del self._hits[k]
            ts = [t for t in self._hits.get(key, []) if now - t <= self._window]
            if len(ts) >= self._max:
                self._hits[key] = ts
                return False
            ts.append(now)
            self._hits[key] = ts
            return True


_plan_trip_limiter = _RateLimiter(RATE_LIMIT_MAX, RATE_LIMIT_WINDOW_S)


# ---------------------------------------------------------------- validation
def parse_positive_float(raw, max_value=None):
    """Parse a user-supplied constraint to a positive float.

    Returns None for empty/missing/invalid/non-positive values so that
    0 and "0" are handled consistently (treated as 'not provided').
    Values above max_value are also rejected (None) to bound CPU work.
    """
    if raw is None:
        return None
    try:
        value = float(raw)
    except (ValueError, TypeError):
        return None
    if math.isnan(value) or value <= 0:
        return None
    if math.isinf(value):
        return None
    if max_value is not None and value > max_value:
        return None
    return value


_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_location(raw):
    """Sanitize a user-supplied location string.

    Strips control characters (CRLF log-injection, NULs), collapses
    whitespace, and enforces a length cap. Returns the cleaned string
    (possibly empty).
    """
    if raw is None:
        return ""
    s = _CONTROL_CHARS.sub("", str(raw))
    s = " ".join(s.split())
    return s[:MAX_LOCATION_LEN]


# ---------------------------------------------------------------- cache
def is_cache_valid():
    """True if the cache file exists and is younger than CACHE_MAX_AGE_DAYS."""
    if not os.path.exists(CACHE_FILE):
        return False
    mod_datetime = datetime.fromtimestamp(os.path.getmtime(CACHE_FILE))
    return mod_datetime > datetime.now() - timedelta(days=CACHE_MAX_AGE_DAYS)


def _filter_active(df):
    """Keep only currently-active POTA parks."""
    if "active" in df.columns:
        before = len(df)
        df = df[df["active"] == 1]
        logger.info(
            "Filtered out %d inactive parks (%d active remain)",
            before - len(df), len(df),
        )
    return df


def _download_parks():
    """Download the full POTA park database with explicit timeout/status checks."""
    resp = requests.get(POTA_CSV_URL, timeout=30)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    if "reference" not in df.columns:
        raise ValueError("Downloaded CSV is not the POTA parks file "
                        "(missing 'reference' column)")
    return df


def _atomic_to_csv(df, path):
    """Write CSV atomically: temp file in the same dir, then os.replace()."""
    tmp_path = f"{path}.tmp.{os.getpid()}"
    df.to_csv(tmp_path, index=False)
    os.replace(tmp_path, path)


def load_parks_from_cache():
    """Load active parks from cache, downloading fresh data when stale."""
    try:
        if os.path.exists(CACHE_FILE) and is_cache_valid():
            df = pd.read_csv(CACHE_FILE)
            logger.info("Loaded %d parks from cache", len(df))
            return _filter_active(df)

        with _cache_lock:
            # Re-check: another thread may have refreshed while we waited.
            if os.path.exists(CACHE_FILE) and is_cache_valid():
                df = pd.read_csv(CACHE_FILE)
            else:
                logger.info("Cache stale/missing — downloading fresh data...")
                df = _download_parks()
                _atomic_to_csv(df, CACHE_FILE)
                logger.info("Downloaded and cached %d parks", len(df))
        return _filter_active(df)
    except Exception as e:
        logger.exception("Error refreshing park data: %s", e)
        # Fall back to stale cache if we have one.
        try:
            if os.path.exists(CACHE_FILE):
                df = pd.read_csv(CACHE_FILE)
                logger.info("Loaded %d parks from stale cache", len(df))
                return _filter_active(df)
        except Exception as e2:
            logger.exception("Error loading stale cache: %s", e2)
        return pd.DataFrame()


# ---------------------------------------------------------------- geocoding
_STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska",
    "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey",
    "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
    "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
}
_PROVINCE_NAMES = {
    "AB": "Alberta", "BC": "British Columbia", "MB": "Manitoba",
    "NB": "New Brunswick", "NL": "Newfoundland and Labrador",
    "NS": "Nova Scotia", "NT": "Northwest Territories", "NU": "Nunavut",
    "ON": "Ontario", "PE": "Prince Edward Island", "QC": "Quebec",
    "SK": "Saskatchewan", "YT": "Yukon",
}


def normalize_state(state):
    """Expand 'US-TX'/'CA-ON' style codes to full names + country.

    Returns (state_string, country_string_or_None).
    """
    if not state:
        return state, None
    s = str(state).strip()
    if "-" in s:
        prefix, code = s.split("-", 1)
        code_u = code.upper()
        if prefix.upper() == "US" and code_u in _STATE_NAMES:
            return _STATE_NAMES[code_u], "USA"
        if prefix.upper() == "CA" and code_u in _PROVINCE_NAMES:
            return _PROVINCE_NAMES[code_u], "Canada"
    return s, None


# Nominatim addresstype/type values that represent a real settlement or
# administrative area. Anything else (residential, road, landuse, farm,
# hotel, ...) is a street-level or POI match and must NOT be treated as
# a city — e.g. "Manta, TX" only matches "Villa Manta" (a residential
# area in San Antonio), which silently pulled in San Antonio parks.
_SETTLEMENT_TYPES = {
    "city", "town", "village", "hamlet", "municipality", "suburb",
    "neighbourhood", "quarter", "borough", "capital", "isolated_dwelling",
    "locality", "state", "province", "county", "county borough",
    "local_administrative_area", "administrative", "civil",
    "metropolitan_borough", "unitary_authority", "prefecture",
    "regency", "district", "governorate", "oblast", "oblast_2",
    "municipality_law", "commune", "parish", "census",
    "census_designated_place", "local_government_area",
}


def _is_settlement(location):
    """True if a Nominatim result is a settlement/admin area, not a road/POI."""
    raw = getattr(location, "raw", None) or {}
    kinds = {str(raw.get("addresstype", "")).lower(),
             str(raw.get("type", "")).lower()}
    return bool(kinds & _SETTLEMENT_TYPES)


def _address_matches_state(location, state_or_province):
    """When a state/province was given, the result must actually be in it.

    Prevents a city-only retry from silently landing in another country
    (e.g. bare "Manta" -> Manta, Italy).
    """
    if not state_or_province:
        return True
    display = (getattr(location, "address", "") or "").lower()
    raw_display = (getattr(location, "raw", None) or {}).get(
        "display_name", "").lower()
    hay = display + " " + raw_display
    state_l = str(state_or_province).lower()
    if state_l in hay:
        return True
    # "TX" -> "Texas", "BC" -> "British Columbia"
    code = state_l.upper()
    full = _STATE_NAMES.get(code) or _PROVINCE_NAMES.get(code)
    if full and full.lower() in hay:
        return True
    return False


def _pick_settlement(locations, state_or_province=None):
    """First settlement-level result that lies in the requested state, or None."""
    for loc in locations or []:
        if _is_settlement(loc) and _address_matches_state(loc,
                                                        state_or_province):
            return (loc.latitude, loc.longitude)
    return None


def geocode_city(city_name, state_or_province=None, country=None):
    """Geocode 'city, state, country' via Nominatim (cached, polite UA).

    Only settlement-level matches are accepted; street/POI matches
    (residential areas, roads, land use) are rejected so an invalid city
    name returns None instead of coordinates for an unrelated place.
    """
    if country is None and state_or_province:
        state_or_province, country = normalize_state(state_or_province)
    parts = [p for p in (city_name, state_or_province, country) if p]
    location_string = ", ".join(parts)
    if location_string in _geocode_cache:
        return _geocode_cache[location_string]

    geolocator = Nominatim(user_agent=NOMINATIM_UA)
    coords = None
    try:
        results = geolocator.geocode(location_string, exactly_one=False) or []
        coords = _pick_settlement(results, state_or_province)
        if coords is None and state_or_province:
            # State/province may confuse Nominatim — retry with city only,
            # still requiring a settlement inside the requested state.
            results = geolocator.geocode(str(city_name), exactly_one=False) or []
            coords = _pick_settlement(results, state_or_province)
    except Exception as e:
        logger.error("Error geocoding %r: %s", location_string, e)

    if coords is None:
        logger.warning("Could not geocode location: %s", location_string)
    _geocode_cache[location_string] = coords
    return coords


# ---------------------------------------------------------------- core math
def _park_coords(park):
    """Return (lat, lon) for a park dict/row, or None if unusable."""
    try:
        lat = float(park["latitude"])
        lon = float(park["longitude"])
    except (KeyError, TypeError, ValueError):
        return None
    if math.isnan(lat) or math.isnan(lon):
        return None
    return (lat, lon)


def one_way_miles(city_coords, park):
    """Great-circle one-way distance from city to park, or None."""
    coords = _park_coords(park)
    if coords is None:
        return None
    return geodesic(city_coords, coords).miles


def trip_hours_for_park(one_way):
    """Round-trip driving hours plus the activation stop for a single park."""
    return 2 * one_way / AVG_SPEED_MPH + ACTIVATION_HOURS


def find_nearby_parks(parks_df, city_coords, max_distance_miles=None,
                     max_hours=None, max_miles=None):
    """Return active park records (dicts) satisfying ALL given constraints.

    Constraints are a funnel, not an either/or:
      - max_distance_miles: straight-line radius from the city
      - max_hours: round-trip drive time + ACTIVATION_HOURS per park
      - max_miles: round-trip mileage per park
    Results are sorted nearest-first with a `distance_miles` key.
    """
    if parks_df is None or parks_df.empty:
        return []
    if not {"latitude", "longitude"} <= set(parks_df.columns):
        return []

    df = _filter_active(parks_df).dropna(subset=["latitude", "longitude"]).copy()

    # Bounding-box prefilter so we only run geodesic on plausible parks.
    radius = max_distance_miles
    if radius is None:
        radius = float("inf")
    if max_hours is not None:
        # hours budget -> max one-way miles
        budget_miles = (max_hours - ACTIVATION_HOURS) * AVG_SPEED_MPH / 2
        radius = min(radius, max(budget_miles, 0.0))
    if max_miles is not None:
        radius = min(radius, max_miles / 2)
    if math.isfinite(radius) and radius > 0:
        lat0, lon0 = float(city_coords[0]), float(city_coords[1])
        lat_span = radius / 69.0
        cos_lat = max(math.cos(math.radians(lat0)), 1e-6)
        lon_span = radius / (69.0 * cos_lat)
        df = df[
            df["latitude"].between(lat0 - lat_span, lat0 + lat_span)
            & df["longitude"].between(lon0 - lon_span, lon0 + lon_span)
        ]

    results = []
    for park in df.to_dict("records"):
        one_way = one_way_miles(city_coords, park)
        if one_way is None:
            continue
        if max_distance_miles is not None and one_way > max_distance_miles:
            continue
        if max_miles is not None and 2 * one_way > max_miles:
            continue
        if max_hours is not None and trip_hours_for_park(one_way) > max_hours:
            continue
        park["distance_miles"] = one_way
        results.append(park)

    results.sort(key=lambda p: p["distance_miles"])
    logger.info("find_nearby_parks: %d parks (radius=%s hours=%s miles=%s)",
               len(results), max_distance_miles, max_hours, max_miles)
    return results


def generate_optimized_trip(parks, city_coords, max_hours=None, max_miles=None):
    """Greedy nearest-neighbour multi-park route that fits the budget.

    Budget accounting includes the drive from the last park back home.
    Parks that don't fit are skipped (not a hard stop), so a farther-then-
    nearer ordering can still add closer parks later.
    """
    if not parks:
        return []
    if max_hours is None and max_miles is None:
        return list(parks)

    selected = []
    remaining = list(parks)
    current = tuple(city_coords)
    time_used = 0.0   # driving hours + activations so far
    route_miles = 0.0  # driven miles so far

    while True:
        best = None
        best_leg = None
        for park in remaining:
            coords = _park_coords(park)
            if coords is None:
                continue
            leg = geodesic(current, coords).miles
            home_leg = geodesic(coords, city_coords).miles
            if max_hours is not None:
                projected = time_used + leg / AVG_SPEED_MPH + ACTIVATION_HOURS \
                    + home_leg / AVG_SPEED_MPH
                if projected > max_hours:
                    continue
            if max_miles is not None:
                if route_miles + leg + home_leg > max_miles:
                    continue
            if best_leg is None or leg < best_leg:
                best, best_leg = park, leg

        if best is None:
            break
        coords = _park_coords(best)
        time_used += best_leg / AVG_SPEED_MPH + ACTIVATION_HOURS
        route_miles += best_leg
        selected.append(best)
        current = coords
        remaining.remove(best)

    return selected


def generate_google_maps_url_with_markers(city, parks):
    """Google Maps directions URL: city -> parks (numbered stops) -> city.

    Google renders directions waypoints as numbered stops, which matches
    the numbered list shown in the UI.
    """
    try:
        waypoints = []
        for park in parks[:MAX_MAP_WAYPOINTS]:
            coords = _park_coords(park)
            if coords:
                waypoints.append(f"{coords[0]},{coords[1]}")

        origin = quote(str(city))
        url = ("https://www.google.com/maps/dir/?api=1"
               f"&origin={origin}&destination={origin}")
        if waypoints:
            url += "&waypoints=" + "|".join(waypoints)
        logger.info("Generated Google Maps URL: %s", url)
        return url
    except Exception as e:
        logger.exception("Error generating Google Maps URL: %s", e)
        return "https://www.google.com/maps"


# ---------------------------------------------------------------- frontend
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>POTA Trip Planner - Plan Your Ham Radio Adventures!</title>
    <style>
        :root {
            --bg-color: #f5f5f5;
            --container-bg: white;
            --text-color: #333;
            --header-color: #2c5aa0;
            --button-bg: #2c5aa0;
            --button-hover: #1a3d7a;
            --result-bg: #d4edda;
            --error-bg: #fff3cd;
            --border-color: #ddd;
            --park-item-bg: #e9ecef;
            --map-bg: #f0f0f0;
            --accent-color-1: #e74c3c;
            --accent-color-2: #3498db;
            --accent-color-3: #2ecc71;
            --sidebar-bg: rgba(44, 90, 160, 0.9);
            --success-color: #28a745;
            --warning-color: #ffc107;
            --danger-color: #dc3545;
        }

        .dark-mode {
            --bg-color: #1a1a1a;
            --container-bg: #2d2d2d;
            --text-color: #f0f0f0;
            --header-color: #4a7bff;
            --button-bg: #4a7bff;
            --button-hover: #3a6be0;
            --result-bg: #2d5a2d;
            --error-bg: #ffd700;
            --border-color: #444;
            --park-item-bg: #3d3d3d;
            --map-bg: #333;
            --accent-color-1: #ff6b6b;
            --accent-color-2: #64b5f6;
            --accent-color-3: #66bb6a;
            --sidebar-bg: rgba(74, 123, 255, 0.9);
            --success-color: #4caf50;
            --warning-color: #ffd54f;
            --danger-color: #f44336;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: var(--bg-color);
            color: var(--text-color);
            transition: background-color 0.3s, color 0.3s;
            background-image: url('https://images.unsplash.com/photo-1501854140801-50d01698950b?ixlib=rb-4.0.3&ixid=M3wxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8fA%3D%3D&auto=format&fit=crop&w=1770&q=80');
            background-size: cover;
            background-position: center;
            background-attachment: fixed;
        }

        .container {
            display: flex;
            background-color: var(--container-bg);
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            overflow: hidden;
            transition: background-color 0.3s, color 0.3s;
            backdrop-filter: blur(10px);
        }

        .sidebar {
            width: 250px;
            background: var(--sidebar-bg);
            color: white;
            padding: 25px;
            height: fit-content;
        }

        .main-content {
            flex: 1;
            padding: 30px;
        }

        .title-container {
            text-align: center;
            margin-bottom: 30px;
            padding: 20px;
            background: linear-gradient(90deg, var(--accent-color-1), var(--accent-color-2), var(--accent-color-3));
            border-radius: 10px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0% { box-shadow: 0 0 0 0 rgba(231, 76, 60, 0.4); }
            70% { box-shadow: 0 0 0 10px rgba(231, 76, 60, 0); }
            100% { box-shadow: 0 0 0 0 rgba(231, 76, 60, 0); }
        }

        h1 {
            color: white;
            margin: 0;
            font-size: 2.5em;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }

        .subtitle {
            color: rgba(255, 255, 255, 0.9);
            font-size: 1.2em;
            margin-top: 5px;
        }

        .instructions {
            background-color: rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 20px;
        }

        .instructions h3 {
            margin-top: 0;
            color: white;
            border-bottom: 1px solid rgba(255, 255, 255, 0.3);
            padding-bottom: 8px;
        }

        .instructions ul {
            padding-left: 20px;
        }

        .instructions li {
            margin-bottom: 10px;
            line-height: 1.4;
        }

        .form-group {
            margin-bottom: 20px;
        }

        .hint {
            display: block;
            margin-top: 6px;
            font-size: 0.82em;
            opacity: 0.75;
        }

        label {
            display: block;
            margin-bottom: 8px;
            font-weight: 600;
            color: var(--header-color);
        }

        input[type="text"], input[type="number"], select {
            width: 100%;
            padding: 12px;
            border: 2px solid var(--border-color);
            border-radius: 8px;
            box-sizing: border-box;
            background-color: var(--container-bg);
            color: var(--text-color);
            font-size: 16px;
            transition: border-color 0.3s, box-shadow 0.3s;
        }

        input[type="text"]:focus, input[type="number"]:focus, select:focus {
            border-color: var(--accent-color-2);
            box-shadow: 0 0 0 3px rgba(52, 152, 219, 0.2);
            outline: none;
        }

        button {
            background: linear-gradient(90deg, var(--button-bg), #3a6be0);
            color: white;
            padding: 14px 20px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 18px;
            font-weight: 600;
            width: 100%;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(44, 90, 160, 0.3);
        }

        button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(44, 90, 160, 0.4);
        }

        .result {
            margin-top: 30px;
            padding: 25px;
            border-radius: 10px;
            display: none;
            background-color: var(--result-bg);
            color: #155724;
            border-left: 5px solid var(--accent-color-3);
            animation: fadeIn 0.5s;
        }

        .result h2 {
            color: var(--text-color);
            margin-top: 0;
        }

        .result .park-name {
            color: var(--text-color);
        }

        .result .park-reference {
            color: var(--accent-color-2);
        }

        .result .park-number {
            color: var(--accent-color-3);
        }

        .result .park-distance {
            background-color: var(--accent-color-1);
            color: white;
        }

        .result .error {
            color: #721c24;
            background-color: var(--error-bg);
            border-left-color: var(--accent-color-1);
            border-radius: 8px;
            padding: 15px;
            margin-top: 15px;
        }

        .dark-mode .result .error {
            color: #721c24;
            background-color: var(--error-bg);
            border-left-color: var(--accent-color-1);
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .error {
            background-color: var(--error-bg);
            color: #721c24;
            border-left-color: var(--accent-color-1);
        }

        .park-list {
            margin-top: 20px;
        }

        .park-item {
            padding: 15px;
            margin: 10px 0;
            background-color: var(--park-item-bg);
            border-radius: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: transform 0.2s, box-shadow 0.2s;
            border-left: 4px solid var(--accent-color-3);
        }

        .park-item:hover {
            transform: translateX(5px);
            box-shadow: 0 4px 10px rgba(0,0,0,0.1);
        }

        .park-info {
            flex: 1;
        }

        .park-number {
            font-weight: bold;
            color: var(--accent-color-3);
            font-size: 1.2em;
            margin-right: 10px;
        }

        .park-name {
            font-weight: 600;
            font-size: 1.1em;
            color: var(--text-color);
        }

        .park-reference {
            color: var(--accent-color-2);
            font-weight: 500;
        }

        .park-distance {
            background-color: var(--accent-color-1);
            color: white;
            padding: 5px 10px;
            border-radius: 20px;
            font-weight: 600;
        }

        .google-maps-link {
            display: block;
            margin-top: 20px;
            padding: 15px;
            background: linear-gradient(90deg, var(--accent-color-2), var(--accent-color-3));
            color: white;
            text-align: center;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(52, 152, 219, 0.3);
        }

        .google-maps-link:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(52, 152, 219, 0.4);
        }

        .dark-mode-toggle {
            position: absolute;
            top: 20px;
            right: 20px;
            background-color: var(--button-bg);
            color: white;
            border: none;
            border-radius: 8px;
            padding: 12px 20px;
            cursor: pointer;
            font-size: 16px;
            font-weight: 600;
            z-index: 100;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2);
        }

        .dark-mode-toggle:hover {
            background-color: var(--button-hover);
        }

        .park-number-marker {
            display: inline-block;
            width: 24px;
            height: 24px;
            background-color: var(--accent-color-1);
            color: white;
            border-radius: 50%;
            text-align: center;
            line-height: 24px;
            font-size: 12px;
            font-weight: bold;
            margin-right: 10px;
        }

        .park-item {
            display: flex;
            align-items: center;
        }

        .park-item .park-info {
            flex: 1;
        }

        .park-item .park-distance {
            margin-left: 15px;
        }
    </style>
</head>
<body>
    <button class="dark-mode-toggle" onclick="toggleDarkMode()">Toggle Dark Mode</button>
    
    <div class="container">
        <div class="sidebar">
            <div class="instructions">
                <h3>How to Use</h3>
                <ul>
                    <li>Enter a location anywhere in the world</li>
                    <li>Set radius in miles (default 100)</li>
                    <li>Optionally set hours or miles limits</li>
                    <li>Click "Plan My Trip"</li>
                    <li>View results and Google Maps route</li>
                </ul>
            </div>
            
            <div class="instructions">
                <h3>Features</h3>
                <ul>
                    <li>Worldwide active POTA parks only</li>
                    <li>Dark/light mode toggle</li>
                    <li>Google Maps integration</li>
                    <li>Time constraint support (includes drive home)</li>
                    <li>Distance filtering</li>
                    <li>Constraints combine (radius AND hours AND miles)</li>
                </ul>
            </div>
            
            <div class="instructions">
                <h3>Pro Tips</h3>
                <ul>
                    <li>Try "Eustace" with Texas and 4 hours</li>
                    <li>Hours budget = round-trip driving + 2h activation per park</li>
                    <li>Check Google Maps for the numbered route</li>
                </ul>
            </div>
        </div>
        
        <div class="main-content">
            <div class="title-container">
                <h1>🚀 POTA Trip Planner</h1>
                <div class="subtitle">Plan Your Ham Radio Adventures Worldwide!
                    <br><small>by N5SKT</small></div>
            </div>
            
            <form id="tripForm">
                <div class="form-group">
                    <label for="location">Location:</label>
                    <input type="text" id="location" name="location" required
                           placeholder="City, State/Province, Country"
                           autocomplete="street-address">
                    <small class="hint">Anywhere Google Maps can find it —
                        e.g. "Eustace, TX", "Vancouver, BC, Canada",
                        "Melbourne, Australia". More detail = more accurate.</small>
                </div>
                
                <div class="form-group">
                    <label for="radius">Radius (miles):</label>
                    <input type="number" id="radius" name="radius" value="100" min="1">
                </div>
                
                <div class="form-group">
                    <label for="hours">Hours (optional):</label>
                    <input type="number" id="hours" name="hours" step="0.1" min="0">
                </div>
                
                <div class="form-group">
                    <label for="miles">Trip Miles (optional):</label>
                    <input type="number" id="miles" name="miles" step="0.1" min="0">
                </div>
                
                <button type="submit">Plan My Trip</button>
            </form>
            
            <div id="result" class="result">
                <h2>Results for <span id="resultCity"></span></h2>
                <div id="resultContent"></div>
                <a id="mapsLink" class="google-maps-link" href="#" target="_blank">View on Google Maps</a>
            </div>
        </div>
    </div>

    <script>
        // Escape untrusted strings before inserting into innerHTML
        // (POTA park names are user-editable upstream).
        function esc(s) {
            return String(s).replace(/[&<>"']/g, c => ({
                '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
            }[c]));
        }

        function toggleDarkMode() {
            document.body.classList.toggle('dark-mode');
            const isDarkMode = document.body.classList.contains('dark-mode');
            localStorage.setItem('darkMode', isDarkMode);
        }

        // Check for saved theme preference
        document.addEventListener('DOMContentLoaded', function() {
            const savedDarkMode = localStorage.getItem('darkMode');
            if (savedDarkMode === 'true') {
                document.body.classList.add('dark-mode');
            }
        });

        document.getElementById('tripForm').addEventListener('submit', function(e) {
            e.preventDefault();
            
            // Clear previous results
            const resultDiv = document.getElementById('result');
            const resultContent = document.getElementById('resultContent');
            resultContent.innerHTML = '';
            resultDiv.style.display = 'none';
            
            const formData = new FormData(this);
            const data = {};
            for (let [key, value] of formData.entries()) {
                if (value.trim() !== '') {
                    data[key] = value;
                }
            }
            
            // Show loading state
            const submitButton = this.querySelector('button');
            const originalText = submitButton.textContent;
            submitButton.textContent = 'Processing...';
            submitButton.disabled = true;
            
            // Make API request
            fetch('/plan_trip', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(data)
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(result => {
                const resultCity = document.getElementById('resultCity');
                const resultContent = document.getElementById('resultContent');
                const mapsLink = document.getElementById('mapsLink');
                
                if (result.error) {
                    resultContent.innerHTML = `<div class="error">${esc(result.error)}</div>`;
                    resultDiv.style.display = 'block';
                } else {
                    resultCity.textContent = data.location || data.city;
                    let parksHTML = '<div class="park-list">';
                    result.parks.forEach((park, index) => {
                        parksHTML += `
                            <div class="park-item">
                                <div class="park-info">
                                    <span class="park-number-marker">${index + 1}</span>
                                    <span class="park-name">${esc(park.name)}</span>
                                    <br>
                                    <span class="park-reference">${esc(park.reference)}</span>
                                </div>
                                <div class="park-distance">${park.distance.toFixed(1)} miles</div>
                            </div>
                        `;
                    });
                    parksHTML += '</div>';
                    
                    resultContent.innerHTML = parksHTML;
                    mapsLink.href = result.googleMapsUrl;
                    resultDiv.style.display = 'block';
                }
            })
            .catch(error => {
                const resultContent = document.getElementById('resultContent');
                resultContent.innerHTML = `<div class="error">Network error: ${esc(error.message)}</div>`;
                resultDiv.style.display = 'block';
            })
            .finally(() => {
                submitButton.textContent = originalText;
                submitButton.disabled = false;
            });
        });
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/health')
def health():
    return jsonify({'status': 'ok',
                   'version': APP_VERSION,
                   'cache_valid': is_cache_valid()})


@app.after_request
def set_security_headers(response):
    response.headers.setdefault(
        'Content-Security-Policy',
        "default-src 'self'; "
        "img-src 'self' https://images.unsplash.com; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'")
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'DENY')
    response.headers.setdefault('Referrer-Policy', 'no-referrer')
    return response


@app.route('/plan_trip', methods=['POST'])
def plan_trip():
    try:
        # DoS guard: bound requests per client IP.
        client_ip = (request.headers.get('X-Forwarded-For', '')
                     .split(',')[0].strip() or request.remote_addr or 'unknown')
        if not _plan_trip_limiter.allow(client_ip):
            logger.warning("Rate limit exceeded for %s", client_ip)
            return jsonify({'error': 'Too many requests. Please slow down.'}), 429

        data = request.get_json(silent=True) or {}

        # New freeform API: a single 'location' string ("Eustace, TX",
        # "Vancouver, BC, Canada", "Melbourne, Australia").
        # Legacy API ('city' + optional 'state') is still accepted.
        if len(str(data.get('location') or '')) > MAX_LOCATION_LEN:
            return jsonify({'error': f'Location too long '
                                    f'(max {MAX_LOCATION_LEN} chars).'}), 400
        location = sanitize_location(data.get('location'))
        if not location:
            city = sanitize_location(data.get('city'))
            if not city:
                return jsonify({'error': 'Please provide a location '
                                        '(e.g. "Eustace, TX").'}), 400
            state = sanitize_location(data.get('state')) or None
            if state == 'Other':
                state = None
            if state:
                state, country = normalize_state(state)
                location = ", ".join(p for p in (city, state, country) if p)
            else:
                location = city

        radius_value = parse_positive_float(data.get('radius'),
                                          MAX_RADIUS_MILES)
        hours_value = parse_positive_float(data.get('hours'), MAX_TRIP_HOURS)
        miles_value = parse_positive_float(data.get('miles'), MAX_TRIP_MILES)

        if (data.get('radius') is not None and radius_value is None
                and parse_positive_float(data.get('radius')) is not None):
            return jsonify({'error': f'Radius too large '
                                    f'(max {MAX_RADIUS_MILES:g} miles).'}), 400

        if radius_value is None and hours_value is None and miles_value is None:
            return jsonify({'error': 'Please provide at least one positive '
                                    'constraint (Radius, Hours, or Miles) '
                                    'within the allowed limits.'}), 400
        if radius_value is None:
            radius_value = DEFAULT_RADIUS_MILES

        logger.info("Planning trip for %s: radius=%s hours=%s miles=%s",
                    location, radius_value, hours_value, miles_value)

        parks_df = load_parks_from_cache()
        if parks_df.empty:
            return jsonify({'error': 'Could not load park data. '
                                    'Please try again later.'}), 500

        city_coords = geocode_city(location)
        if not city_coords:
            return jsonify({'error': 'Could not find location coordinates. '
                                    'Please check the place name and try '
                                    'again.'}), 400

        # Apply ALL constraints as a funnel (radius always applies).
        nearby_parks = find_nearby_parks(
            parks_df, city_coords,
            max_distance_miles=radius_value,
            max_hours=hours_value,
            max_miles=miles_value,
        )

        # Build a multi-park route that fits the budget (if any budget given).
        if hours_value or miles_value:
            optimized = generate_optimized_trip(
                nearby_parks, city_coords,
                max_hours=hours_value, max_miles=miles_value)
            if optimized:
                nearby_parks = optimized

        parks_data = [{
            'name': park.get('name', 'Unnamed Park'),
            'reference': park.get('reference', 'Unknown'),
            'distance': round(park.get('distance_miles', 0.0), 2),
        } for park in nearby_parks]

        response_data = {
            'city': location,          # legacy key: full location string
            'location': location,
            'parkCount': len(parks_data),
            'parks': parks_data,
            'googleMapsUrl': generate_google_maps_url_with_markers(location,
                                                                  nearby_parks),
        }
        logger.info("Planned trip: %d parks for %s", len(parks_data), location)
        return jsonify(response_data)

    except Exception as e:
        logger.exception("Application error: %s", e)
        return jsonify({'error': f'Application error: {type(e).__name__}'}), 500


if __name__ == '__main__':
    logger.info("Initializing POTA Trip Planner...")
    parks_df = load_parks_from_cache()
    logger.info("Loaded %d active parks", len(parks_df))
    host = os.environ.get("POTA_HOST", "127.0.0.1")
    port = int(os.environ.get("POTA_PORT", "5001"))
    debug = os.environ.get("POTA_DEBUG", "0") == "1"
    logger.info("Starting POTA Trip Planner at http://%s:%d", host, port)
    app.run(host=host, port=port, debug=debug)

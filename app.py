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
# 1.8.1  2026-09-30  Error-UX fixes: frontend now shows the server's
#                    actual error message instead of a generic "network
#                    error"; friendly "no parks fit your criteria" message
#                    for empty results; unit toggle greys out with a
#                    tooltip in hours mode. Crash fix: reject out-of-range
#                    coordinates in the upstream POTA CSV (lat > 90 rows
#                    crashed geopy with ValueError -> HTTP 500).
# 1.8.0  2026-09-30  Single-choice trip constraint UI (radius / driving
#                    time / trip distance) + miles-or-kilometers units.
#                    New API: mode + value + unit (legacy radius/hours/miles
#                    fields still accepted).
# 1.7.0  2026-09-29  Security hardening from code review:
#                    - per-IP rate limiting on /plan_trip (DoS guard)
#                    - bounded geocode cache (LRU, no memory exhaustion)
#                    - caps on radius/hours/miles (CPU DoS guard)
#                    - location length cap + control-char stripping
#                    - security headers (CSP, X-Frame-Options, nosniff)
#                    - default cache/log paths moved off shared /tmp
#                    - /health no longer discloses the cache file path
# 1.8.0  2026-09-30  Single-choice trip constraint UI (radius / driving
#                    time / trip distance) + miles/km unit toggle.
# 1.8.1  2026-09-30  Error-UX fixes (show server error messages, friendly
#                    empty-result guidance) + bad-coordinate crash fix.
# 1.9.0  2026-10-02  Configurable activation hours per park: new optional
#                    'activation_hours' input (0.5-12h, default 2) shown
#                    in Driving-time mode; flows through trip_hours_for_park,
#                    find_nearby_parks and generate_optimized_trip.
# 2.0.0  2026-10-02  Road Trip tab: point-to-point trips. Enter origin +
#                    destination; the driving route is fetched from OSRM
#                    (free, no API key), active POTA parks within a
#                    configurable corridor (default 25 mi) of the road
#                    are found, ordered by trip progress, and returned
#                    with a Google Maps point-to-point waypoint URL
#                    (origin -> parks -> destination). New endpoint
#                    POST /road_trip {origin, destination, corridor, unit}.
# 2.0.1  2026-10-04  Architecture-independent .deb: the venv is built on
#                    the install target (postinst) instead of shipped, so
#                    one package serves amd64 and arm64 (Raspberry Pi).
#                    App installs to /opt/PotaTrip with .venv; postrm
#                    purge removes it. Added PI-INSTALL.md (Raspberry Pi
#                    guide) and 44NET-HOSTING.md (publishing on a 44Net
#                    address via a GL.iNet WireGuard tunnel; tested on
#                    the GL.iNet Beryl AX GL-MT3600BE).
# 2.0.2  2026-10-05  Log rotation: the package now installs an
#                    /etc/logrotate.d/potatrip config (daily / 10 MB,
#                    7 kept, gzip, copytruncate) and Depends on logrotate.
#                    Previously the app's own log grew unbounded.
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
APP_VERSION = "2.0.2"             # keep in sync with VERSION HISTORY above
AVG_SPEED_MPH = 40.0          # assumed average driving speed
ACTIVATION_HOURS = 2.0        # default time spent at the park activating
MAX_ACTIVATION_HOURS = 12.0   # cap for user-supplied hours-per-park
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

# Road-trip (point-to-point) settings — see VERSION HISTORY 2.0.0.
OSRM_ROUTE_URL = os.environ.get(
    "POTA_OSRM_URL",
    "https://router.project-osrm.org/route/v1/driving")
DEFAULT_CORRIDOR_MILES = 25.0   # how far off the road a park may sit
MAX_CORRIDOR_MILES = 100.0
MAX_ROAD_TRIP_MILES = 3000.0  # same sanity bound as trip distance
ROAD_TRIP_MAX_PARKS = 10        # Google Maps waypoint cap
ROAD_TRIP_CANDIDATES = 30       # parks offered for selection (user picks <=10)

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


# ------------------------------------------------------- constraint modes
# v1.8.0: the UI sends exactly ONE constraint: mode + value + unit.
#   mode: "radius"  — straight-line distance from the location
#         "hours"   — round-trip driving time + activation per park
#         "distance"— round-trip mileage per park
#   unit: "mi" (default) or "km".
# Legacy clients sending radius/hours/miles directly still work.

VALID_MODES = ("radius", "hours", "distance")
KM_PER_MILE = 1.609344


def to_miles(value, unit):
    """Convert a distance value in `unit` ('mi'|'km') to miles."""
    if unit == "km":
        return value * KM_PER_MILE
    return value


def resolve_constraint(data):
    """Resolve the request's single constraint into (radius, hours, miles)
    in internal (mile) units.

    Returns (radius_value, hours_value, miles_value, error).
    On new-style input exactly one of the three is set (radius always set
    as the coarse funnel). On legacy input the three raw fields pass
    through with unit conversion applied if a unit is given.
    """
    mode = (data.get("mode") or "").strip().lower() or None
    unit = (data.get("unit") or "mi").strip().lower()
    if unit not in ("mi", "km"):
        return None, None, None, "Unknown unit (use 'mi' or 'km')."

    # Optional: custom activation hours per park (default 2). Applies to
    # the hours budget math; ignored for radius/distance modes.
    activation = ACTIVATION_HOURS
    if data.get("activation_hours") is not None:
        a = parse_positive_float(data.get("activation_hours"),
                                MAX_ACTIVATION_HOURS)
        if a is None:
            return None, None, None, (
                f"Activation hours per park must be a positive number "
                f"up to {MAX_ACTIVATION_HOURS:g}.")
        activation = a
    # Stash for the route handler (avoids widening every return tuple).
    data["_activation_hours"] = activation

    if mode:
        if mode not in VALID_MODES:
            return None, None, None, (f"Unknown mode '{mode}' "
                                    f"(use radius, hours, or distance).")
        raw = data.get("value")
        if raw is None:
            return None, None, None, "No value provided for the constraint."
        if mode == "hours":
            v = parse_positive_float(raw, MAX_TRIP_HOURS)  # unit-free
            if v is None:
                return None, None, None, (f"Hours too large or invalid "
                                        f"(max {MAX_TRIP_HOURS:g}).")
            # find_nearby_parks converts the hours budget to a radius
            # itself; no funnel needed here.
            return None, v, None, None
        v = parse_positive_float(raw)
        if v is None:
            return None, None, None, "Constraint value must be a positive number."
        v_mi = to_miles(v, unit)
        if mode == "radius":
            if v_mi > MAX_RADIUS_MILES:
                return None, None, None, (
                    f"Radius too large (max {MAX_RADIUS_MILES:g} mi / "
                    f"{MAX_RADIUS_MILES * KM_PER_MILE:g} km).")
            return v_mi, None, None, None
        # distance mode: round-trip budget per park.
        if v_mi > MAX_TRIP_MILES:
            return None, None, None, (
                f"Trip distance too large (max {MAX_TRIP_MILES:g} mi / "
                f"{MAX_TRIP_MILES * KM_PER_MILE:g} km).")
        return None, None, v_mi, None

    # ---- legacy path: raw radius/hours/miles fields (miles assumed unless
    # a unit is supplied, which applies to radius and miles).
    radius_value = parse_positive_float(to_miles_arg(data.get("radius"), unit),
                                      MAX_RADIUS_MILES)
    hours_value = parse_positive_float(data.get("hours"), MAX_TRIP_HOURS)
    miles_value = parse_positive_float(to_miles_arg(data.get("miles"), unit),
                                     MAX_TRIP_MILES)
    return radius_value, hours_value, miles_value, None


def to_miles_arg(raw, unit):
    """Convert a raw user distance field to miles if it parses and unit=km.

    Non-numeric input passes through untouched so parse_positive_float
    produces its usual None.
    """
    if unit != "km" or raw is None:
        return raw
    v = parse_positive_float(raw)
    return to_miles(v, unit) if v is not None else raw


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
    """Return (lat, lon) for a park dict/row, or None if unusable.

    Rejects NaN and out-of-range coordinates: the upstream POTA CSV
    contains a few rows with latitudes > 90 (bad data), which crash
    geopy's Point constructor.
    """
    try:
        lat = float(park["latitude"])
        lon = float(park["longitude"])
    except (KeyError, TypeError, ValueError):
        return None
    if math.isnan(lat) or math.isnan(lon):
        return None
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        return None
    return (lat, lon)


def one_way_miles(city_coords, park):
    """Great-circle one-way distance from city to park, or None."""
    coords = _park_coords(park)
    if coords is None:
        return None
    return geodesic(city_coords, coords).miles


def trip_hours_for_park(one_way, activation_hours=ACTIVATION_HOURS):
    """Round-trip driving hours plus the activation stop for a single park."""
    return 2 * one_way / AVG_SPEED_MPH + activation_hours


def find_nearby_parks(parks_df, city_coords, max_distance_miles=None,
                     max_hours=None, max_miles=None,
                     activation_hours=ACTIVATION_HOURS):
    """Return active park records (dicts) satisfying ALL given constraints.

    Constraints are a funnel, not an either/or:
      - max_distance_miles: straight-line radius from the city
      - max_hours: round-trip drive time + activation_hours per park
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
        budget_miles = (max_hours - activation_hours) * AVG_SPEED_MPH / 2
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
        if max_hours is not None and trip_hours_for_park(
                one_way, activation_hours) > max_hours:
            continue
        park["distance_miles"] = one_way
        results.append(park)

    results.sort(key=lambda p: p["distance_miles"])
    logger.info("find_nearby_parks: %d parks (radius=%s hours=%s miles=%s)",
               len(results), max_distance_miles, max_hours, max_miles)
    return results


def generate_optimized_trip(parks, city_coords, max_hours=None, max_miles=None,
                           activation_hours=ACTIVATION_HOURS):
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
                projected = time_used + leg / AVG_SPEED_MPH + activation_hours \
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
        time_used += best_leg / AVG_SPEED_MPH + activation_hours
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


def generate_google_maps_url_point_to_point(origin_name, dest_name, parks):
    """Google Maps directions URL: origin -> parks (numbered) -> destination.

    Same numbered-stop rendering as the round-trip variant, but the trip
    starts at one city and ends at another.
    """
    try:
        waypoints = []
        for park in parks[:ROAD_TRIP_MAX_PARKS]:
            coords = _park_coords(park)
            if coords:
                waypoints.append(f"{coords[0]},{coords[1]}")
        url = ("https://www.google.com/maps/dir/?api=1"
               f"&origin={quote(str(origin_name))}"
               f"&destination={quote(str(dest_name))}")
        if waypoints:
            url += "&waypoints=" + "|".join(waypoints)
        return url
    except Exception as e:
        logger.exception("Error generating point-to-point Maps URL: %s", e)
        return "https://www.google.com/maps"


# ------------------------------------------------------------- road trips
_route_cache = _LRUGeocodeCache(100)   # (origin,dest) -> route dict


def fetch_driving_route(origin_coords, dest_coords):
    """Fetch the driving route polyline between two points from OSRM.

    Returns a dict:
      {'coords': [(lat, lon), ...],   # ordered along the route
       'distance_miles': float,
       'duration_hours': float}
    or None on failure. Cached per coordinate pair.

    Note: OSRM's public demo server is used (no API key). The response
    geometry is Google-independent; the user-facing route is still
    rendered by Google Maps via the waypoint URL.
    """
    key = (round(origin_coords[0], 4), round(origin_coords[1], 4),
           round(dest_coords[0], 4), round(dest_coords[1], 4))
    cached = _route_cache.get(key)
    if cached is not None:
        return cached
    try:
        url = (f"{OSRM_ROUTE_URL}/"
               f"{origin_coords[1]},{origin_coords[0]};"
               f"{dest_coords[1]},{dest_coords[0]}"
               f"?overview=full&geometries=geojson")
        resp = requests.get(url, timeout=30,
                           headers={"User-Agent": NOMINATIM_UA})
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("code") != "Ok" or not payload.get("routes"):
            logger.warning("OSRM no route: %s", payload.get("code"))
            return None
        route = payload["routes"][0]
        # GeoJSON coords are [lon, lat] — flip to (lat, lon).
        coords = [(pt[1], pt[0]) for pt in route["geometry"]["coordinates"]]
        result = {
            "coords": coords,
            "distance_miles": route["distance"] / 1609.344,
            "duration_hours": route["duration"] / 3600.0,
        }
        _route_cache.set(key, result)
        return result
    except Exception as e:
        logger.error("OSRM route fetch failed: %s", e)
        return None


def _point_along_progress(route_coords, point):
    """Fraction (0..1) of the route nearest to `point`, plus distance in miles.

    Projects the park onto the nearest route segment; returns
    (progress_fraction, miles_off_route). Uses planar approximation on
    the segment — fine at corridor scales.
    """
    if not route_coords:
        return None, None
    lat, lon = point
    cos_lat = max(math.cos(math.radians(lat)), 1e-6)
    # Convert to planar miles.
    px, py = lon * 69.0 * cos_lat, lat * 69.0
    seg_lengths = []
    total = 0.0
    for a, b in zip(route_coords, route_coords[1:]):
        ax, ay = a[1] * 69.0 * cos_lat, a[0] * 69.0
        bx, by = b[1] * 69.0 * cos_lat, b[0] * 69.0
        seg_lengths.append(math.hypot(bx - ax, by - ay))
        total += seg_lengths[-1]
    if total <= 0:
        return 0.0, 0.0
    best_d2 = None
    best_along = 0.0
    acc = 0.0
    for (a, b), seg_len in zip(zip(route_coords, route_coords[1:]),
                              seg_lengths):
        ax, ay = a[1] * 69.0 * cos_lat, a[0] * 69.0
        bx, by = b[1] * 69.0 * cos_lat, b[0] * 69.0
        if seg_len == 0:
            continue
        # Projection of p onto segment a-b, clamped to [0,1].
        t = ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / (seg_len ** 2)
        t = max(0.0, min(1.0, t))
        cx, cy = ax + t * (bx - ax), ay + t * (by - ay)
        d2 = (px - cx) ** 2 + (py - cy) ** 2
        if best_d2 is None or d2 < best_d2:
            best_d2 = d2
            best_along = (acc + t * seg_len) / total
        acc += seg_len
    if best_d2 is None:
        return 0.0, 0.0
    return best_along, math.sqrt(best_d2)


def parks_along_route(parks_df, route_coords, corridor_miles=DEFAULT_CORRIDOR_MILES):
    """Active parks within `corridor_miles` of the route, ordered along it.

    Each returned park dict gains:
      - 'off_route_miles': perpendicular distance from the road
      - 'progress': 0..1 fraction of the trip where the park sits
    """
    if parks_df is None or parks_df.empty or not route_coords:
        return []
    df = _filter_active(parks_df).dropna(subset=["latitude", "longitude"])

    # Bounding-box prefilter: only parks within corridor of the route's
    # lat/lon extent can possibly be within the corridor. Cuts the O(n*m)
    # projection from ~90k parks down to the handful near the road.
    lats = [c[0] for c in route_coords]
    lons = [c[1] for c in route_coords]
    lat_pad = corridor_miles / 69.0
    lon_pad = corridor_miles / (69.0 * max(
        math.cos(math.radians(sum(lats) / len(lats))), 1e-6))
    df = df[df["latitude"].between(min(lats) - lat_pad, max(lats) + lat_pad)
            & df["longitude"].between(min(lons) - lon_pad, max(lons) + lon_pad)]

    # Simplify the route for projection: cap at ~200 points. Corridor
    # decisions don't need full polyline resolution.
    step = max(1, len(route_coords) // 200)
    simple = route_coords[::step]
    if simple[-1] != route_coords[-1]:
        simple.append(route_coords[-1])

    results = []
    for park in df.to_dict("records"):
        coords = _park_coords(park)
        if coords is None:
            continue
        progress, off = _point_along_progress(simple, coords)
        if progress is None or off > corridor_miles:
            continue
        park["off_route_miles"] = off
        park["progress"] = progress
        results.append(park)
    results.sort(key=lambda p: p["progress"])
    logger.info("parks_along_route: %d parks within %g mi of route",
                len(results), corridor_miles)
    return results


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

        .mode-selector {
            display: flex;
            gap: 10px;
            margin-bottom: 12px;
        }

        .mode-option {
            flex: 1;
            border: 2px solid var(--border-color, #d0d7e2);
            border-radius: 10px;
            padding: 10px 12px;
            cursor: pointer;
            transition: border-color 0.2s, background-color 0.2s;
            display: flex;
            flex-direction: column;
            gap: 2px;
        }

        .mode-option:hover {
            border-color: var(--accent-color-1, #4a7cf0);
        }

        .mode-option.selected {
            border-color: var(--accent-color-1, #4a7cf0);
            background-color: rgba(74, 124, 240, 0.10);
        }

        .mode-option input[type="radio"] {
            margin-bottom: 4px;
            accent-color: var(--accent-color-1, #4a7cf0);
        }

        .mode-title {
            font-weight: 700;
            font-size: 0.95rem;
        }

        .mode-desc {
            font-size: 0.78rem;
            opacity: 0.75;
        }

        .value-row {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .value-row input[type="number"] {
            width: 140px;
        }

        .unit-toggle {
            display: inline-flex;
            border: 2px solid var(--border-color, #d0d7e2);
            border-radius: 10px;
            overflow: hidden;
        }

        .unit-option {
            padding: 8px 14px;
            cursor: pointer;
            font-weight: 600;
            transition: background-color 0.2s;
            user-select: none;
        }

        .unit-option + .unit-option {
            border-left: 2px solid var(--border-color, #d0d7e2);
        }

        .unit-option.selected {
            background-color: var(--accent-color-1, #4a7cf0);
            color: #fff;
        }

        .unit-option input[type="radio"] {
            display: none;
        }

        .unit-toggle.disabled {
            opacity: 0.4;
            pointer-events: none;
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

        .tab-bar {
            display: flex;
            gap: 8px;
            margin-bottom: 20px;
            border-bottom: 2px solid var(--border-color);
        }

        .tab-btn {
            background: transparent;
            color: var(--header-color);
            border: none;
            border-bottom: 3px solid transparent;
            padding: 12px 24px;
            font-size: 17px;
            font-weight: 600;
            cursor: pointer;
            width: auto;
            box-shadow: none;
            transition: all 0.2s ease;
        }

        .tab-btn:hover {
            transform: none;
            background: rgba(52, 152, 219, 0.08);
        }

        .tab-btn.selected {
            border-bottom-color: var(--accent-color-2);
            color: var(--accent-color-2);
        }

        .tab-panel[hidden] {
            display: none;
        }

        .road-summary {
            margin: 10px 0;
            font-weight: 600;
        }

        .park-select {
            display: flex;
            align-items: center;
            margin-right: 12px;
            cursor: pointer;
        }

        .park-select input[type="checkbox"] {
            width: 20px;
            height: 20px;
            cursor: pointer;
        }

        #buildRouteBtn {
            margin-top: 12px;
            width: auto;
            padding: 12px 28px;
            font-size: 16px;
        }

        #buildRouteBtn:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
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
                    <li>Hours budget = round-trip driving + activation time per park (default 2h, adjustable)</li>
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

            <div class="tab-bar" role="tablist" aria-label="Trip planner tabs">
                <button type="button" class="tab-btn selected" id="tabHome"
                        role="tab" aria-selected="true"
                        onclick="switchTab('home')">Home Trip</button>
                <button type="button" class="tab-btn" id="tabRoad"
                        role="tab" aria-selected="false"
                        onclick="switchTab('road')">Road Trip</button>
            </div>

            <div id="panelHome" class="tab-panel">
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
                    <label>Trip limit — choose one:</label>
                    <div class="mode-selector" role="radiogroup"
                         aria-label="Trip constraint type">
                        <label class="mode-option">
                            <input type="radio" name="mode" value="radius"
                                   checked>
                            <span class="mode-title">Radius</span>
                            <span class="mode-desc">Straight-line distance
                                from your location</span>
                        </label>
                        <label class="mode-option">
                            <input type="radio" name="mode" value="hours">
                            <span class="mode-title">Driving time</span>
                            <span class="mode-desc">Round trip + 2h
                                activation per park</span>
                        </label>
                        <label class="mode-option">
                            <input type="radio" name="mode" value="distance">
                            <span class="mode-title">Trip distance</span>
                            <span class="mode-desc">Round-trip distance
                                per park</span>
                        </label>
                    </div>
                    <div class="value-row">
                        <input type="number" id="value" name="value"
                               value="100" min="1" step="any"
                               aria-label="Constraint value">
                        <div class="unit-toggle" role="radiogroup"
                             aria-label="Distance unit">
                            <label class="unit-option">
                                <input type="radio" name="unit" value="mi"
                                       checked> Miles
                            </label>
                            <label class="unit-option">
                                <input type="radio" name="unit" value="km">
                                Kilometers
                            </label>
                        </div>
                    </div>
                    <small class="hint" id="modeHint"></small>
                </div>

                <div class="form-group" id="activationGroup" hidden>
                    <label for="activation_hours">Hours per park:</label>
                    <input type="number" id="activation_hours"
                           name="activation_hours" value="2" min="0.5"
                           max="12" step="0.5"
                           aria-label="Activation hours per park">
                    <small class="hint">Time you spend at each park
                        activating (default 2h). Included in your time
                        budget per park.</small>
                </div>
                
                <button type="submit">Plan My Trip</button>
            </form>
            
            <div id="result" class="result">
                <h2>Results for <span id="resultCity"></span></h2>
                <div id="resultContent"></div>
                <a id="mapsLink" class="google-maps-link" href="#" target="_blank">View on Google Maps</a>
            </div>
            </div><!-- /panelHome -->

            <div id="panelRoad" class="tab-panel" hidden>
                <form id="roadForm">
                    <div class="form-group">
                        <label for="origin">Start from:</label>
                        <input type="text" id="origin" name="origin" required
                               placeholder="Origin city, e.g. Dallas, TX"
                               autocomplete="off">
                    </div>
                    <div class="form-group">
                        <label for="destination">Driving to:</label>
                        <input type="text" id="destination" name="destination"
                               required
                               placeholder="Destination city, e.g. Denver, CO"
                               autocomplete="off">
                    </div>
                    <div class="form-group">
                        <label for="corridor">Corridor width (how far from
                            the road to look for parks):</label>
                        <div class="value-row">
                            <input type="number" id="corridor" name="corridor"
                                   value="25" min="1" step="any"
                                   aria-label="Corridor width">
                            <div class="unit-toggle" id="roadUnitToggle"
                                 role="radiogroup" aria-label="Distance unit">
                                <label class="unit-option">
                                    <input type="radio" name="road_unit"
                                           value="mi" checked> Miles
                                </label>
                                <label class="unit-option">
                                    <input type="radio" name="road_unit"
                                           value="km">
                                    Kilometers
                                </label>
                            </div>
                        </div>
                        <small class="hint">Parks within this distance of the
                            driving route are added as stops (max 10 stops —
                            Google Maps waypoint limit).</small>
                    </div>
                    <button type="submit">Find Parks Along the Route</button>
                </form>

                <div id="roadResult" class="result">
                    <h2 id="roadResultTitle">Road trip</h2>
                    <div id="roadSummary" class="hint"></div>
                    <div id="roadContent"></div>
                    <div id="roadSelectionBar" hidden>
                        <small class="hint" id="selectionCount"></small>
                        <button type="button" id="buildRouteBtn"
                                onclick="buildSelectedRoute()">
                            Add Selected Parks to Trip
                        </button>
                    </div>
                    <a id="roadMapsLink" class="google-maps-link" href="#"
                       target="_blank" hidden>View route on Google Maps</a>
                </div>
            </div><!-- /panelRoad -->
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

        // ---- v1.8.0: single-choice constraint + unit toggle ----
        const MODE_DEFAULTS = {
            radius:   { mi: 100, km: 160 },
            hours:    { mi: 4,   km: 4   },   // hours: unit-independent
            distance: { mi: 150, km: 240 }
        };
        const MODE_HINTS = {
            radius: 'How far from your location to look for parks (as the crow flies).',
            hours: 'Total time budget per park: round-trip driving at ~40 mph plus your activation stop.',
            distance: 'Maximum round-trip driving distance per park.'
        };
        const unitToggle = document.querySelector('.unit-toggle');
        const activationGroup = document.getElementById('activationGroup');

        function currentMode() {
            return document.querySelector('input[name="mode"]:checked').value;
        }
        function currentUnit() {
            return document.querySelector('input[name="unit"]:checked').value;
        }
        function modeLabel(mode) {
            return { radius: 'radius',
                     hours: 'time budget',
                     distance: 'trip distance' }[mode] || 'constraint';
        }
        function refreshModeUI() {
            const mode = currentMode();
            const unit = currentUnit();
            document.querySelectorAll('.mode-option').forEach(opt => {
                opt.classList.toggle('selected',
                    opt.querySelector('input').checked);
            });
            document.querySelectorAll('.unit-option').forEach(opt => {
                opt.classList.toggle('selected',
                    opt.querySelector('input').checked);
            });
            // Hours are unit-independent: grey out the unit toggle.
            const isHours = mode === 'hours';
            unitToggle.classList.toggle('disabled', isHours);
            unitToggle.title = isHours
                ? 'Not applicable: driving time is measured in hours, not distance units.'
                : '';
            // "Hours per park" only matters for the time-budget mode.
            activationGroup.hidden = !isHours;
            const valueInput = document.getElementById('value');
            valueInput.value = MODE_DEFAULTS[mode][unit];
            valueInput.min = mode === 'hours' ? '0.5' : '1';
            valueInput.step = mode === 'hours' ? '0.5' : 'any';
            document.getElementById('modeHint').textContent = MODE_HINTS[mode];
        }
        document.querySelectorAll('input[name="mode"], input[name="unit"]')
            .forEach(el => el.addEventListener('change', refreshModeUI));
        refreshModeUI();

        function fmtDistance(miles) {
            if (currentUnit() === 'km') {
                return (miles * 1.609344).toFixed(1) + ' km';
            }
            return miles.toFixed(1) + ' mi';
        }

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
            .then(response => response.json()
                .catch(() => ({}))
                .then(body => ({ status: response.status, body: body })))
            .then(({ status, body }) => {
                const resultCity = document.getElementById('resultCity');
                const resultContent = document.getElementById('resultContent');
                const mapsLink = document.getElementById('mapsLink');

                if (body.error) {
                    // Show the server's actual error message, not a
                    // generic "network error" (fixes misleading 400s
                    // from bad locations or rejected constraints).
                    resultCity.textContent = data.location || data.city;
                    resultContent.innerHTML = `<div class="error">${esc(body.error)}</div>`;
                    resultDiv.style.display = 'block';
                } else if (status !== 200) {
                    resultCity.textContent = data.location || data.city;
                    resultContent.innerHTML = `<div class="error">Server error (HTTP ${status}). Please try again.</div>`;
                    resultDiv.style.display = 'block';
                } else if (!body.parks || body.parks.length === 0) {
                    // Nothing matched — friendly guidance instead of a
                    // blank results box.
                    resultCity.textContent = data.location || data.city;
                    resultContent.innerHTML = `<div class="error">No parks fit your criteria near ${esc(data.location || data.city)}. Try a larger ${esc(modeLabel(currentMode()))}.</div>`;
                    resultDiv.style.display = 'block';
                } else {
                    resultCity.textContent = data.location || data.city;
                    let parksHTML = '<div class="park-list">';
                    body.parks.forEach((park, index) => {
                        parksHTML += `
                            <div class="park-item">
                                <div class="park-info">
                                    <span class="park-number-marker">${index + 1}</span>
                                    <span class="park-name">${esc(park.name)}</span>
                                    <br>
                                    <span class="park-reference">${esc(park.reference)}</span>
                                </div>
                                <div class="park-distance">${fmtDistance(park.distance)}</div>
                            </div>
                        `;
                    });
                    parksHTML += '</div>';

                    resultContent.innerHTML = parksHTML;
                    mapsLink.href = body.googleMapsUrl;
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

        // ---- v2.0.0: Road Trip tab (point-to-point, parks along route) ----
        let roadState = { origin: '', destination: '', parks: [] };
        const MAX_STOPS = 10;   // Google Maps waypoint limit

        function switchTab(which) {
            const isHome = which === 'home';
            document.getElementById('panelHome').hidden = !isHome;
            document.getElementById('panelRoad').hidden = isHome;
            document.getElementById('tabHome').classList
                .toggle('selected', isHome);
            document.getElementById('tabRoad').classList
                .toggle('selected', !isHome);
            document.getElementById('tabHome')
                .setAttribute('aria-selected', String(isHome));
            document.getElementById('tabRoad')
                .setAttribute('aria-selected', String(!isHome));
        }

        function roadUnit() {
            return document.querySelector(
                'input[name="road_unit"]:checked').value;
        }
        function fmtRoadDist(miles) {
            if (roadUnit() === 'km') {
                return (miles * 1.609344).toFixed(1) + ' km';
            }
            return miles.toFixed(1) + ' mi';
        }

        document.getElementById('roadForm').addEventListener('submit',
            function(e) {
            e.preventDefault();
            const resultDiv = document.getElementById('roadResult');
            const content = document.getElementById('roadContent');
            content.innerHTML = '';
            resultDiv.style.display = 'none';

            const formData = new FormData(this);
            const data = {};
            for (let [key, value] of formData.entries()) {
                if (value.trim() !== '') data[key] = value;
            }
            // Rename road_unit -> unit for the API.
            if (data.road_unit) { data.unit = data.road_unit; }
            delete data.road_unit;

            const submitButton = this.querySelector('button');
            const originalText = submitButton.textContent;
            submitButton.textContent = 'Mapping route...';
            submitButton.disabled = true;

            fetch('/road_trip', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            })
            .then(response => response.json()
                .catch(() => ({}))
                .then(body => ({ status: response.status, body: body })))
            .then(({ status, body }) => {
                const title = document.getElementById('roadResultTitle');
                const summary = document.getElementById('roadSummary');
                const mapsLink = document.getElementById('roadMapsLink');
                const selBar = document.getElementById('roadSelectionBar');
                mapsLink.hidden = true;
                selBar.hidden = true;
                if (body.error) {
                    title.textContent = 'Road trip';
                    summary.textContent = '';
                    content.innerHTML =
                        `<div class="error">${esc(body.error)}</div>`;
                    resultDiv.style.display = 'block';
                } else if (!body.parks || body.parks.length === 0) {
                    title.textContent =
                        `${esc(body.origin)} → ${esc(body.destination)}`;
                    summary.textContent =
                        `Route: ${fmtRoadDist(body.routeDistanceMiles)} · ` +
                        `~${body.routeDurationHours.toFixed(1)} h driving. ` +
                        `No parks found within ${fmtRoadDist(body.corridorMiles)} ` +
                        `of the road. Try a wider corridor.`;
                    resultDiv.style.display = 'block';
                } else {
                    roadState = {
                        origin: body.origin,
                        destination: body.destination,
                        parks: body.parks,
                    };
                    title.textContent =
                        `${esc(body.origin)} → ${esc(body.destination)}`;
                    summary.textContent =
                        `Route: ${fmtRoadDist(body.routeDistanceMiles)} · ` +
                        `~${body.routeDurationHours.toFixed(1)} h driving · ` +
                        `${body.parkCount} park(s) found within ` +
                        `${fmtRoadDist(body.corridorMiles)} of the road. ` +
                        `Tick the ones you want as stops (max ${MAX_STOPS}).`;
                    let html = '<div class="park-list">';
                    body.parks.forEach((park, index) => {
                        html += `
                            <div class="park-item">
                                <label class="park-select">
                                    <input type="checkbox" class="park-check"
                                           data-index="${index}"
                                           onchange="updateSelectionCount()">
                                </label>
                                <div class="park-info">
                                    <span class="park-name">${esc(park.name)}</span>
                                    <br>
                                    <span class="park-reference">${esc(park.reference)}</span>
                                    &nbsp;·&nbsp;
                                    <a href="${esc(park.potaUrl)}"
                                       target="_blank"
                                       rel="noopener noreferrer">POTA page</a>
                                </div>
                                <div class="park-distance">${fmtRoadDist(park.off_route_miles)} off route</div>
                            </div>
                        `;
                    });
                    html += '</div>';
                    content.innerHTML = html;
                    selBar.hidden = false;
                    updateSelectionCount();
                    resultDiv.style.display = 'block';
                }
            })
            .catch(error => {
                content.innerHTML =
                    `<div class="error">Network error: ${esc(error.message)}</div>`;
                resultDiv.style.display = 'block';
            })
            .finally(() => {
                submitButton.textContent = originalText;
                submitButton.disabled = false;
            });
        });

        function selectedParks() {
            const picked = [];
            document.querySelectorAll('.park-check:checked')
                .forEach(cb => {
                    const idx = parseInt(cb.dataset.index, 10);
                    if (!isNaN(idx) && roadState.parks[idx]) {
                        picked.push(roadState.parks[idx]);
                    }
                });
            return picked;
        }

        function updateSelectionCount() {
            const n = selectedParks().length;
            const count = document.getElementById('selectionCount');
            const btn = document.getElementById('buildRouteBtn');
            if (n > MAX_STOPS) {
                count.textContent =
                    `${n} parks selected — too many! Google Maps allows ` +
                    `a maximum of ${MAX_STOPS} stops. Untick ` +
                    `${n - MAX_STOPS} more.`;
                btn.disabled = true;
            } else if (n === 0) {
                count.textContent = 'No parks selected yet.';
                btn.disabled = true;
            } else {
                count.textContent =
                    `${n} of ${roadState.parks.length} parks selected.`;
                btn.disabled = false;
            }
        }

        function buildSelectedRoute() {
            const picked = selectedParks();
            if (picked.length === 0 || picked.length > MAX_STOPS) return;
            const waypoints = picked.map(p => `${p.latitude},${p.longitude}`);
            const url = 'https://www.google.com/maps/dir/?api=1'
                + '&origin=' + encodeURIComponent(roadState.origin)
                + '&destination=' + encodeURIComponent(roadState.destination)
                + '&waypoints=' + encodeURIComponent(waypoints.join('|'));
            const mapsLink = document.getElementById('roadMapsLink');
            mapsLink.href = url;
            mapsLink.hidden = false;
            mapsLink.textContent =
                `View route on Google Maps (${picked.length} stop` +
                `${picked.length === 1 ? '' : 's'})`;
            mapsLink.focus();
        }
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

        radius_value, hours_value, miles_value, err = resolve_constraint(data)
        if err:
            return jsonify({'error': err}), 400
        activation_hours = data.get("_activation_hours", ACTIVATION_HOURS)

        if radius_value is None and hours_value is None and miles_value is None:
            return jsonify({'error': 'Please provide a trip constraint '\
                                    '(radius, driving hours, or trip '\
                                    'distance) within the allowed limits.'}), 400
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
            activation_hours=activation_hours,
        )

        # Build a multi-park route that fits the budget (if any budget given).
        if hours_value or miles_value:
            optimized = generate_optimized_trip(
                nearby_parks, city_coords,
                max_hours=hours_value, max_miles=miles_value,
                activation_hours=activation_hours)
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


@app.route('/road_trip', methods=['POST'])
def road_trip():
    """Point-to-point trip: find POTA parks along the driving route.

    Input JSON:
      origin       — start city/place (required)
      destination  — end city/place (required)
      corridor     — miles off-route a park may sit (default 25, max 100)
      unit         — 'mi' or 'km' for corridor + display
    """
    try:
        client_ip = (request.headers.get('X-Forwarded-For', '')
                     .split(',')[0].strip() or request.remote_addr or 'unknown')
        if not _plan_trip_limiter.allow(client_ip):
            logger.warning("Rate limit exceeded for %s", client_ip)
            return jsonify({'error': 'Too many requests. Please slow down.'}), 429

        data = request.get_json(silent=True) or {}
        for field in ('origin', 'destination'):
            if len(str(data.get(field) or '')) > MAX_LOCATION_LEN:
                return jsonify({'error': f'{field.capitalize()} too long '
                                        f'(max {MAX_LOCATION_LEN} chars).'}), 400
        origin = sanitize_location(data.get('origin'))
        destination = sanitize_location(data.get('destination'))
        if not origin or not destination:
            return jsonify({'error': 'Please provide both an origin and a '
                                    'destination (e.g. "Dallas, TX" and '
                                    '"Denver, CO").'}), 400

        unit = (data.get('unit') or 'mi').strip().lower()
        if unit not in ("mi", "km"):
            return jsonify({'error': "Unknown unit (use 'mi' or 'km')."}), 400
        corridor = parse_positive_float(
            to_miles_arg(data.get('corridor'), unit), MAX_CORRIDOR_MILES)
        if corridor is None:
            corridor = DEFAULT_CORRIDOR_MILES

        parks_df = load_parks_from_cache()
        if parks_df.empty:
            return jsonify({'error': 'Could not load park data. '
                                    'Please try again later.'}), 500

        origin_coords = geocode_city(origin)
        if not origin_coords:
            return jsonify({'error': f'Could not find origin "{origin}". '
                                    'Please check the place name.'}), 400
        dest_coords = geocode_city(destination)
        if not dest_coords:
            return jsonify({'error': f'Could not find destination '
                                    f'"{destination}". Please check the '
                                    'place name.'}), 400

        route = fetch_driving_route(origin_coords, dest_coords)
        if route is None:
            return jsonify({'error': 'Could not get a driving route between '
                                    'those places. Please try again.'}), 502
        if route['distance_miles'] > MAX_ROAD_TRIP_MILES:
            return jsonify({'error': f'Trip too long (max '
                                    f'{MAX_ROAD_TRIP_MILES:g} mi).'}), 400

        parks = parks_along_route(parks_df, route['coords'],
                                 corridor_miles=corridor)
        parks_data = [{
            'name': p.get('name', 'Unnamed Park'),
            'reference': p.get('reference', 'Unknown'),
            'off_route_miles': round(p['off_route_miles'], 1),
            'progress': round(p['progress'], 3),
            'latitude': round(p['latitude'], 6),
            'longitude': round(p['longitude'], 6),
            # Deterministic POTA park page (contains the park's website,
            # activator log, and details). No preprocessing needed.
            'potaUrl': ("https://pota.app/#/park/"
                       + str(p.get('reference', ''))),
        } for p in parks[:ROAD_TRIP_CANDIDATES]]

        response_data = {
            'origin': origin,
            'destination': destination,
            'routeDistanceMiles': round(route['distance_miles'], 1),
            'routeDurationHours': round(route['duration_hours'], 1),
            'corridorMiles': corridor,
            'parkCount': len(parks_data),
            'parks': parks_data,
            'googleMapsUrl': generate_google_maps_url_point_to_point(
                origin, destination, parks),
        }
        logger.info("Road trip %s -> %s: %d parks along %.0f mi route",
                    origin, destination, len(parks_data),
                    route['distance_miles'])
        return jsonify(response_data)
    except Exception as e:
        logger.exception("Road trip error: %s", e)
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

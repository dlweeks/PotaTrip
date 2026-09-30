"""Pytest suite for the POTA Trip Planner.

SPDX-License-Identifier: CDDL-1.1
Copyright (c) 2026 Don L. Weeks, N5SKT. See LICENSE (CDDL 1.1) for terms.

Runs against the real cached POTA CSV when available (fast, no network);
falls back to synthetic frames otherwise. Geocoding is monkeypatched so
tests never hit Nominatim.
"""
import math
import os
import time

import pandas as pd
import pytest

import app as appmod


# ---------------------------------------------------------------- fixtures
@pytest.fixture
def synthetic_df():
    """Small park frame around Eustace, TX (29.57, -96.56)."""
    home = (29.57, -96.56)
    rows = [
        # reference, name, active, lat, lon  (approx offsets)
        ("W7D", "Close Park", 1, 29.60, -96.60),          # ~4 mi
        ("K5P", "Mid Park", 1, 29.80, -96.40),            # ~21 mi
        ("N5Q", "Far Park", 1, 30.50, -97.00),            # ~72 mi
        ("W0X", "Dead Park", 0, 29.61, -96.57),           # inactive, ~1 mi
        ("BAD1", "No Coords Park", 1, None, None),         # NaN coords
    ]
    return pd.DataFrame(rows, columns=["reference", "name", "active",
                                      "latitude", "longitude"])


@pytest.fixture
def client(monkeypatch):
    """Flask test client with geocoding stubbed to Eustace, TX."""
    monkeypatch.setattr(appmod, "geocode_city",
                       lambda city, state=None, country=None: (29.57, -96.56))
    # Generous limiter so the suite doesn't trip the production cap;
    # rate-limit tests install their own tiny limiter.
    monkeypatch.setattr(appmod, "_plan_trip_limiter",
                       appmod._RateLimiter(10000, 60.0))
    appmod.app.config["TESTING"] = True
    return appmod.app.test_client()


@pytest.fixture
def real_df_or_skip():
    path = appmod.CACHE_FILE
    if not os.path.exists(path):
        pytest.skip("no cached POTA CSV")
    df = pd.read_csv(path)
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    return df


# ---------------------------------------------------------------- validation
class TestParsePositiveFloat:
    @pytest.mark.parametrize("raw,expected", [
        ("4", 4.0), (4, 4.0), (0.5, 0.5), (None, None), ("", None),
        ("abc", None), (0, None), ("0", None), (-3, None),
        (float("nan"), None),
    ])
    def test_parsing(self, raw, expected):
        assert appmod.parse_positive_float(raw) == expected


# ---------------------------------------------------------------- active filter
class TestActiveFilter:
    def test_inactive_parks_excluded(self, synthetic_df):
        filtered = appmod._filter_active(synthetic_df)
        assert "Dead Park" not in filtered["name"].values
        assert len(filtered) == 4

    def test_real_cache_filters_inactive(self, real_df_or_skip):
        filtered = appmod._filter_active(real_df_or_skip)
        assert (filtered["active"] == 1).all()
        assert len(filtered) < len(real_df_or_skip)


# ---------------------------------------------------------------- find_nearby
class TestFindNearbyParks:
    def test_radius_only(self, synthetic_df):
        parks = appmod.find_nearby_parks(synthetic_df, (29.57, -96.56),
                                        max_distance_miles=30)
        refs = {p["reference"] for p in parks}
        assert "W7D" in refs and "K5P" in refs
        assert "N5Q" not in refs          # 72 mi away
        assert "W0X" not in refs          # inactive
        assert "BAD1" not in refs         # NaN coords

    def test_hours_includes_drive_home(self, synthetic_df):
        # Mid Park ~21 mi one-way: 42 mi round trip @40mph = 1.05h + 2h = 3.05h
        parks_3h = appmod.find_nearby_parks(synthetic_df, (29.57, -96.56),
                                           max_hours=3.0)
        assert all(p["distance_miles"] < 20 for p in parks_3h)
        parks_4h = appmod.find_nearby_parks(synthetic_df, (29.57, -96.56),
                                           max_hours=4.0)
        assert any(p["reference"] == "K5P" for p in parks_4h)

    def test_miles_is_round_trip(self, synthetic_df):
        # 40-mile trip budget => one-way <= 20 mi
        parks = appmod.find_nearby_parks(synthetic_df, (29.57, -96.56),
                                        max_miles=40)
        assert all(2 * p["distance_miles"] <= 40 for p in parks)

    def test_constraints_combine_as_funnel(self, synthetic_df):
        # radius 100 + hours 3.05 => only parks within the hours budget
        parks = appmod.find_nearby_parks(synthetic_df, (29.57, -96.56),
                                        max_distance_miles=100,
                                        max_hours=3.05)
        assert all(appmod.trip_hours_for_park(p["distance_miles"]) <= 3.05
                   for p in parks)
        assert "W7D" in {p["reference"] for p in parks}

    def test_sorted_nearest_first(self, synthetic_df):
        parks = appmod.find_nearby_parks(synthetic_df, (29.57, -96.56),
                                        max_distance_miles=100)
        dists = [p["distance_miles"] for p in parks]
        assert dists == sorted(dists)

    def test_empty_frame(self):
        assert appmod.find_nearby_parks(pd.DataFrame(), (0, 0),
                                       max_distance_miles=10) == []


# ---------------------------------------------------------------- optimizer
class TestGenerateOptimizedTrip:
    def test_budget_includes_return_home(self, synthetic_df):
        parks = appmod.find_nearby_parks(synthetic_df, (29.57, -96.56),
                                        max_distance_miles=100)
        # 4 hours: close(4mi)+mid(21mi) chain + return home must fit
        trip = appmod.generate_optimized_trip(parks, (29.57, -96.56),
                                            max_hours=4.0)
        total = 0.0
        current = (29.57, -96.56)
        for p in trip:
            coords = appmod._park_coords(p)
            total += appmod.geodesic(current, coords).miles / appmod.AVG_SPEED_MPH
            total += appmod.ACTIVATION_HOURS
            current = coords
        total += appmod.geodesic(current, (29.57, -96.56)).miles / appmod.AVG_SPEED_MPH
        assert total <= 4.0 + 1e-9

    def test_miles_budget_route_not_double_counted(self, synthetic_df):
        parks = appmod.find_nearby_parks(synthetic_df, (29.57, -96.56),
                                        max_distance_miles=100)
        trip = appmod.generate_optimized_trip(parks, (29.57, -96.56),
                                            max_miles=50)
        route = 0.0
        current = (29.57, -96.56)
        for p in trip:
            coords = appmod._park_coords(p)
            route += appmod.geodesic(current, coords).miles
            current = coords
        route += appmod.geodesic(current, (29.57, -96.56)).miles
        assert route <= 50 + 1e-9

    def test_no_budget_returns_all(self, synthetic_df):
        parks = appmod.find_nearby_parks(synthetic_df, (29.57, -96.56),
                                        max_distance_miles=100)
        assert len(appmod.generate_optimized_trip(parks, (29.57, -96.56))) == \
            len(parks)

    def test_empty_input(self):
        assert appmod.generate_optimized_trip([], (0, 0), max_hours=4) == []


# ---------------------------------------------------------------- maps URL
class TestMapsUrl:
    def test_numbered_waypoints(self):
        parks = [{"latitude": 29.6, "longitude": -96.6},
                {"latitude": 29.8, "longitude": -96.4}]
        url = appmod.generate_google_maps_url_with_markers("Eustace, TX", parks)
        assert "api=1" in url
        assert "origin=Eustace%2C+TX" in url or "origin=Eustace" in url
        assert "waypoints=29.6,-96.6|29.8,-96.4" in url
        assert url.count("destination") == 1

    def test_waypoint_cap(self):
        parks = [{"latitude": 29 + i * 0.01, "longitude": -96.5}
                 for i in range(1, 20)]
        url = appmod.generate_google_maps_url_with_markers("X", parks)
        n = len(url.split("waypoints=")[1].split("&")[0].split("|"))
        assert n == appmod.MAX_MAP_WAYPOINTS


# ---------------------------------------------------------------- HTTP layer
class TestPlanTripEndpoint:
    def test_missing_city(self, client):
        r = client.post("/plan_trip", json={})
        assert r.status_code == 400

    def test_freeform_location_accepted(self, client, monkeypatch,
                                      synthetic_df):
        monkeypatch.setattr(appmod, "load_parks_from_cache",
                           lambda: synthetic_df)
        r = client.post("/plan_trip",
                       json={"location": "Eustace, TX", "radius": "50"})
        assert r.status_code == 200
        assert r.get_json()["location"] == "Eustace, TX"

    def test_freeform_international_accepted(self, client, monkeypatch,
                                           synthetic_df):
        monkeypatch.setattr(appmod, "load_parks_from_cache",
                           lambda: synthetic_df)
        r = client.post("/plan_trip",
                       json={"location": "Melbourne, Australia",
                            "radius": "50"})
        assert r.status_code == 200
        assert r.get_json()["location"] == "Melbourne, Australia"

    def test_freeform_passed_to_geocoder_verbatim(self, client, monkeypatch,
                                               synthetic_df):
        seen = {}

        def spy(location, *a, **k):
            seen["arg"] = location
            return (29.57, -96.56)

        monkeypatch.setattr(appmod, "geocode_city", spy)
        monkeypatch.setattr(appmod, "load_parks_from_cache",
                           lambda: synthetic_df)
        r = client.post("/plan_trip",
                       json={"location": "Vancouver, BC, Canada",
                            "radius": "50"})
        assert r.status_code == 200
        assert seen["arg"] == "Vancouver, BC, Canada"

    def test_legacy_city_state_still_works(self, client, monkeypatch,
                                         synthetic_df):
        seen = {}

        def spy(location, *a, **k):
            seen["arg"] = location
            return (29.57, -96.56)

        monkeypatch.setattr(appmod, "geocode_city", spy)
        monkeypatch.setattr(appmod, "load_parks_from_cache",
                           lambda: synthetic_df)
        r = client.post("/plan_trip",
                       json={"city": "Eustace", "state": "US-TX",
                            "radius": "50"})
        assert r.status_code == 200
        # Legacy US-TX code must be normalized into the location string.
        assert seen["arg"] == "Eustace, Texas, USA"

    def test_legacy_city_only_works(self, client, monkeypatch, synthetic_df):
        monkeypatch.setattr(appmod, "load_parks_from_cache",
                           lambda: synthetic_df)
        r = client.post("/plan_trip",
                       json={"city": "Eustace", "radius": "50"})
        assert r.status_code == 200
        assert r.get_json()["city"] == "Eustace"

    def test_no_positive_constraints(self, client):
        r = client.post("/plan_trip", json={"city": "Eustace", "hours": "0"})
        assert r.status_code == 400

    def test_radius_default_applies_with_hours(self, client, monkeypatch,
                                             synthetic_df):
        monkeypatch.setattr(appmod, "load_parks_from_cache",
                           lambda: synthetic_df)
        r = client.post("/plan_trip", json={"city": "Eustace", "state": "US-TX",
                                          "hours": "4"})
        assert r.status_code == 200
        body = r.get_json()
        assert body["parkCount"] >= 1
        assert all(p["distance"] <= appmod.DEFAULT_RADIUS_MILES
                   for p in body["parks"])

    def test_hours_constraint_limits_parks(self, client, monkeypatch,
                                         synthetic_df):
        monkeypatch.setattr(appmod, "load_parks_from_cache",
                           lambda: synthetic_df)
        r = client.post("/plan_trip", json={"city": "Eustace", "hours": "3.0"})
        body = r.get_json()
        assert all(p["distance"] < 20 for p in body["parks"])

    def test_inactive_never_returned(self, client, monkeypatch, synthetic_df):
        monkeypatch.setattr(appmod, "load_parks_from_cache",
                           lambda: synthetic_df)
        r = client.post("/plan_trip", json={"city": "Eustace", "radius": "500"})
        names = [p["name"] for p in r.get_json()["parks"]]
        assert "Dead Park" not in names
        assert "No Coords Park" not in names

    def test_geocode_failure_400(self, client, monkeypatch):
        monkeypatch.setattr(appmod, "geocode_city",
                           lambda *a, **k: None)
        monkeypatch.setattr(appmod, "load_parks_from_cache",
                           lambda: pd.DataFrame({"reference": ["x"],
                                                "active": [1],
                                                "latitude": [1.0],
                                                "longitude": [1.0]}))
        r = client.post("/plan_trip", json={"city": "Nowhereville"})
        assert r.status_code == 400

    def test_maps_url_present(self, client, monkeypatch, synthetic_df):
        monkeypatch.setattr(appmod, "load_parks_from_cache",
                           lambda: synthetic_df)
        r = client.post("/plan_trip", json={"city": "Eustace", "radius": "50"})
        assert "google.com/maps" in r.get_json()["googleMapsUrl"]


# ------------------------------------------------- geocode settlement guard
_REAL_GEOCODE = appmod.geocode_city  # captured before fixtures stub it out


class FakeLoc:
    def __init__(self, lat, lon, addresstype, display):
        self.latitude = lat
        self.longitude = lon
        self.address = display
        self.raw = {"addresstype": addresstype, "display_name": display}


class FakeNominatim:
    """Returns canned results keyed by the query string."""
    responses = {}

    def __init__(self, user_agent=None, **kw):
        pass

    def geocode(self, query, exactly_one=True):
        return list(self.responses.get(query, []))


class TestGeocodeSettlementGuard:
    """Regression: 'Manta, TX' matched a residential area in San Antonio.

    Only settlement/admin-area results inside the requested state should
    be accepted; roads, POIs and out-of-state matches must return None.
    """

    @pytest.fixture(autouse=True)
    def clear_cache(self, monkeypatch):
        monkeypatch.setattr(appmod, "_geocode_cache", {})
        monkeypatch.setattr(appmod, "Nominatim", FakeNominatim)

    def test_residential_match_rejected(self):
        FakeNominatim.responses = {
            "Manta, TX": [FakeLoc(29.52, -98.59, "residential",
                                  "Villa Manta, San Antonio, Texas")],
        }
        assert appmod.geocode_city("Manta, TX") is None

    def test_road_match_rejected(self):
        FakeNominatim.responses = {
            "Manta, TX": [FakeLoc(32.7, -97.5, "road",
                                  "Manta Street, White Settlement, Texas")],
        }
        assert appmod.geocode_city("Manta, TX") is None

    def test_city_match_accepted(self):
        FakeNominatim.responses = {
            "Eustace, TX": [FakeLoc(32.307, -96.006, "village",
                                   "Eustace, Henderson County, Texas")],
        }
        assert appmod.geocode_city("Eustace, TX") == (32.307, -96.006)

    def test_city_only_retry_must_stay_in_state(self):
        # Full query fails; bare-city retry lands in Italy -> rejected.
        FakeNominatim.responses = {
            "Manta, Texas": [],
            "Manta": [FakeLoc(44.61, 7.48, "town",
                             "Manta, Cuneo, Piemonte, Italia")],
        }
        assert appmod.geocode_city("Manta", "TX") is None

    def test_city_only_retry_in_state_accepted(self):
        FakeNominatim.responses = {
            "Kermit, Texas": [],
            "Kermit": [FakeLoc(31.85, -103.09, "city",
                               "Kermit, Glasscock County, Texas")],
        }
        assert appmod.geocode_city("Kermit", "TX") == (31.85, -103.09)

    def test_no_state_no_filter(self):
        # Without a state, any settlement match is fine (worldwide mode).
        FakeNominatim.responses = {
            "Manta": [FakeLoc(44.61, 7.48, "town",
                             "Manta, Cuneo, Piemonte, Italia")],
        }
        assert appmod.geocode_city("Manta") == (44.61, 7.48)

    def test_full_api_rejects_residential_end_to_end(self, client, monkeypatch):
        monkeypatch.setattr(appmod, "geocode_city", _REAL_GEOCODE)
        monkeypatch.setattr(appmod, "_geocode_cache", {})
        monkeypatch.setattr(appmod, "Nominatim", FakeNominatim)
        FakeNominatim.responses = {
            "Manta, TX": [FakeLoc(29.52, -98.59, "residential",
                                 "Villa Manta, San Antonio, Texas")],
        }
        r = client.post("/plan_trip",
                       json={"location": "Manta, TX", "radius": "50"})
        assert r.status_code == 400


# ------------------------------------------------------- security hardening
class TestSecurityHardening:
    """v1.7.0 hardening: caps, sanitizer, rate limit, headers."""

    def test_radius_over_max_rejected(self, client):
        r = client.post("/plan_trip",
                       json={"location": "Dallas, TX", "radius": "25000"})
        assert r.status_code == 400

    def test_hours_over_max_rejected(self, client):
        r = client.post("/plan_trip",
                       json={"location": "Dallas, TX", "hours": "100000"})
        assert r.status_code == 400

    def test_miles_over_max_rejected(self, client):
        r = client.post("/plan_trip",
                       json={"location": "Dallas, TX", "miles": "999999"})
        assert r.status_code == 400

    def test_infinity_rejected(self):
        assert appmod.parse_positive_float("Infinity") is None
        assert appmod.parse_positive_float(float("inf")) is None

    def test_parse_respects_max(self):
        assert appmod.parse_positive_float("100", 500) == 100.0
        assert appmod.parse_positive_float("600", 500) is None

    def test_sanitize_strips_control_chars(self):
        out = appmod.sanitize_location("Dallas\x00,\r\n TX\x1b[31m")
        assert "\x00" not in out and "\r" not in out and "\x1b" not in out
        assert "Dallas" in out

    def test_sanitize_caps_length(self):
        out = appmod.sanitize_location("A" * 5000)
        assert len(out) == appmod.MAX_LOCATION_LEN

    def test_oversized_location_rejected(self, client):
        r = client.post("/plan_trip",
                       json={"location": "X" * 5000, "radius": "50"})
        assert r.status_code == 400

    def test_rate_limit_429(self, client, monkeypatch):
        monkeypatch.setattr(appmod, "_plan_trip_limiter",
                           appmod._RateLimiter(3, 60.0))
        codes = [client.post("/plan_trip",
                            json={"location": "Dallas, TX",
                                  "radius": "50"}).status_code
                 for _ in range(5)]
        assert codes[:3] == [200, 200, 200]
        assert all(c == 429 for c in codes[3:])

    def test_rate_limiter_windows_expire(self):
        rl = appmod._RateLimiter(2, 0.2)
        assert rl.allow("ip") and rl.allow("ip") and not rl.allow("ip")
        time.sleep(0.25)
        assert rl.allow("ip")

    def test_lru_cache_evicts_oldest(self):
        c = appmod._LRUGeocodeCache(3)
        c.set("a", 1); c.set("b", 2); c.set("c", 3)
        c.get("a")                      # touch 'a' so 'b' is oldest
        c.set("d", 4)
        assert "b" not in c and "a" in c and "d" in c
        assert len(c) == 3

    def test_security_headers_present(self, client):
        r = client.get("/")
        assert r.headers["X-Content-Type-Options"] == "nosniff"
        assert r.headers["X-Frame-Options"] == "DENY"
        csp = r.headers["Content-Security-Policy"]
        assert "frame-ancestors 'none'" in csp
        assert "default-src 'self'" in csp

    def test_health_no_path_disclosure(self, client):
        r = client.get("/health")
        assert "cache_file" not in r.get_json()


# ------------------------------------------------- v1.8.0 modes and units
class TestConstraintModes:
    def test_radius_mode_miles(self):
        r, h, m, err = appmod.resolve_constraint(
            {"mode": "radius", "value": "50", "unit": "mi"})
        assert err is None and r == 50.0 and h is None and m is None

    def test_radius_mode_km_converts(self):
        r, h, m, err = appmod.resolve_constraint(
            {"mode": "radius", "value": "160", "unit": "km"})
        assert err is None
        assert abs(r - 160 * appmod.KM_PER_MILE) < 1e-6

    def test_radius_km_over_cap_rejected(self):
        # 1000 km = 621 mi > 500 mi cap
        r, h, m, err = appmod.resolve_constraint(
            {"mode": "radius", "value": "1000", "unit": "km"})
        assert r is None and err is not None

    def test_hours_mode(self):
        r, h, m, err = appmod.resolve_constraint(
            {"mode": "hours", "value": "6"})
        assert err is None and h == 6.0 and r is None and m is None

    def test_hours_over_cap_rejected(self):
        r, h, m, err = appmod.resolve_constraint(
            {"mode": "hours", "value": "100"})
        assert h is None and err is not None

    def test_distance_mode_km(self):
        r, h, m, err = appmod.resolve_constraint(
            {"mode": "distance", "value": "300", "unit": "km"})
        assert err is None and m is not None
        assert abs(m - 300 * appmod.KM_PER_MILE) < 1e-6

    def test_unknown_mode_rejected(self):
        r, h, m, err = appmod.resolve_constraint(
            {"mode": "vibes", "value": "5"})
        assert err is not None

    def test_unknown_unit_rejected(self):
        r, h, m, err = appmod.resolve_constraint(
            {"mode": "radius", "value": "5", "unit": "furlongs"})
        assert err is not None

    def test_missing_value_rejected(self):
        r, h, m, err = appmod.resolve_constraint({"mode": "radius"})
        assert err is not None

    def test_legacy_fields_still_work(self):
        r, h, m, err = appmod.resolve_constraint(
            {"radius": "30", "hours": "5"})
        assert err is None and r == 30.0 and h == 5.0 and m is None

    def test_legacy_km_unit_applies_to_radius_and_miles(self):
        r, h, m, err = appmod.resolve_constraint(
            {"radius": "160", "miles": "320", "unit": "km"})
        assert err is None
        assert abs(r - 160 * appmod.KM_PER_MILE) < 1e-6
        assert abs(m - 320 * appmod.KM_PER_MILE) < 1e-6

    def test_to_miles_passthrough(self):
        assert appmod.to_miles(10, "mi") == 10
        assert abs(appmod.to_miles(10, "km") - 16.09344) < 1e-6


class TestPlanTripNewAPI:
    def test_radius_km_endpoint(self, client):
        r = client.post("/plan_trip",
                       json={"location": "Manta, TX", "mode": "radius",
                             "value": "80", "unit": "km"})
        assert r.status_code == 200

    def test_hours_mode_endpoint(self, client):
        r = client.post("/plan_trip",
                       json={"location": "Manta, TX", "mode": "hours",
                             "value": "5"})
        assert r.status_code == 200

    def test_bad_mode_400(self, client):
        r = client.post("/plan_trip",
                       json={"location": "Manta, TX", "mode": "nope",
                             "value": "5"})
        assert r.status_code == 400

    def test_no_constraint_400(self, client):
        r = client.post("/plan_trip", json={"location": "Manta, TX"})
        assert r.status_code == 400


# ------------------------------------------------- v1.8.1 error UX
class TestEmptyResultsAndErrors:
    def test_empty_results_return_200_with_empty_list(self, client, monkeypatch):
        # Valid location, valid constraint, but no parks nearby:
        # backend must return 200 + parks: [] (frontend shows the
        # friendly "no parks fit" message, not an error).
        monkeypatch.setattr(appmod, "find_nearby_parks",
                          lambda *a, **k: [])
        monkeypatch.setattr(appmod, "generate_optimized_trip",
                          lambda *a, **k: None)
        r = client.post("/plan_trip",
                      json={"location": "Somewhere, TX", "mode": "hours",
                            "value": "1"})
        assert r.status_code == 200
        body = r.get_json()
        assert body["parks"] == []
        assert body["parkCount"] == 0

    def test_ungeocodable_location_returns_error_json_400(self, client,
                                                       monkeypatch):
        monkeypatch.setattr(appmod, "geocode_city",
                           lambda city, state=None, country=None: None)
        r = client.post("/plan_trip",
                       json={"location": "Fairbanks Alask",
                            "mode": "hours", "value": "4"})
        assert r.status_code == 400
        # The JSON error body must exist so the frontend can display it
        # instead of a generic "network error".
        assert "error" in r.get_json()

    def test_out_of_range_coords_rejected(self):
        # Upstream POTA CSV has rows with lat > 90 (e.g. CA-2395).
        # They must be skipped, not crash geopy with ValueError.
        assert appmod._park_coords({"latitude": 92.595,
                                   "longitude": -57.056}) is None
        assert appmod._park_coords({"latitude": 121.497,
                                   "longitude": 14.5633}) is None
        assert appmod._park_coords({"latitude": 29.57,
                                   "longitude": -181.0}) is None
        assert appmod._park_coords({"latitude": 29.57,
                                   "longitude": -96.56}) == (29.57, -96.56)

    def test_bad_csv_rows_do_not_crash_find_nearby(self, synthetic_df):
        bad = synthetic_df.copy()
        bad.loc[len(bad)] = ("CA-2395", "Broken Park", 1, 92.595, -57.056)
        parks = appmod.find_nearby_parks(bad, (21.31, -157.86),
                                        max_distance_miles=100)
        assert all(p["reference"] != "CA-2395" for p in parks)

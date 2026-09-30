# POTA Trip Planner

A web application for planning ham radio park visiting trips using the POTA (Parks on the Air) database.

## Features

- **Web Interface**: Easy-to-use form with input boxes for all parameters
- **Active Parks Only**: Deactivated POTA parks are filtered out at load time
- **Combining Constraints** (applied as a funnel, all at once):
  - Radius (miles) — straight-line distance from the city (default 100)
  - Maximum Hours — round-trip driving time + 2h activation per park
  - Maximum Trip Miles — round-trip mileage per park
- **Multi-Park Route Optimization**: greedy nearest-neighbour selection that
  keeps the whole route (including the drive home) inside the time/miles budget
- **Automatic CSV Caching**: database refreshes when older than 7 days;
  downloads are atomic and lock-guarded
- **Google Maps Integration**: directions URL with the city as origin/destination
  and parks as numbered waypoints
- **Input Validation**: empty/zero/negative/non-numeric constraints are rejected
  cleanly (no float-conversion crashes)

## Project Structure

- `app.py` — main web application (UI is embedded in the Flask template)
- `test_app.py` — pytest suite (31 tests)
- `tests/` — legacy ad-hoc debug scripts (kept for reference; superseded by `test_app.py`)
- `docs/` — documentation

## Installation

1. Install required packages:
   ```bash
   pip3 install -r requirements.txt
   pip3 install pytest   # for tests
   ```

2. Run the application:
   ```bash
   python3 app.py
   ```

3. Visit `http://127.0.0.1:5001` in your web browser

### Configuration (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `POTA_HOST` | `127.0.0.1` | Bind address (set explicitly to expose on the network) |
| `POTA_PORT` | `5001` | Port |
| `POTA_DEBUG` | `0` | Set `1` to enable Werkzeug debugger (local dev only — RCE risk) |
| `POTA_CACHE_FILE` | `/tmp/pota_parks_cache.csv` | Park database cache |
| `POTA_LOG_FILE` | `/tmp/pota_trip_log.txt` | Log file |
| `POTA_GEOCODE_UA` | `PotaTripPlanner/2.0 (...)` | Nominatim user agent (set your callsign/email if publishing) |

### Debian package (system-wide install)

`make deb` builds a `.deb` into `dist/`; `make install` builds and installs it.
The package puts the app in `/opt/potatrip` with a self-contained python3
venv, installs the launcher `/usr/local/bin/potatrip`, and installs, enables
and starts the systemd service `potatrip` (binds `0.0.0.0:5001` by default).

For changing ports/bind address, firewall port guidance, and reverse-proxy
setup, see **[docs/systemd-deployment.md](docs/systemd-deployment.md)**.

## Usage

1. Enter a city name (e.g., "Eustace")
2. Select a state/province (US-XX / CA-XX codes are expanded to full names for geocoding)
3. Set radius and optionally hours and/or trip miles
4. Click "Plan My Trip"

## Trip Planning Math

- `AVG_SPEED_MPH = 40` — assumed average driving speed
- `ACTIVATION_HOURS = 2` — time at each park
- Hours budget for a single park: `2 * one_way_miles / 40 + 2` (round trip + activation)
- Miles budget for a single park: `2 * one_way_miles`
- Multi-park routes track the current position and always include the return leg
  from the last park to the starting city in the budget check.
- Parks that don't fit the budget are skipped, not a hard stop.

## Testing

```bash
python3 -m pytest test_app.py -q
```

Covers: constraint parsing (incl. zero/NaN edge cases), inactive-park filtering,
radius/hours/miles funnel logic, round-trip math, optimizer budget including
drive-home, waypoint caps, and the HTTP endpoint (400s, defaults, geocode failure).
Tests run offline against the cached CSV or synthetic frames; geocoding is stubbed.

## Error Handling

- Invalid/zero/negative constraints → 400 with a clear message
- City not found → 400
- Park data unavailable (download fails, no cache) → 500
- Nominatim failures are logged; geocode results are cached per session

## Requirements

- Flask
- pandas
- geopy
- requests
- pytest (tests only)

## License

Copyright (c) 2026 Don L. Weeks. All Rights Reserved.

This Source Code Form is subject to the terms of the Common Development and
Distribution License, Version 1.1 (the "License" / CDDL-1.1). You may not use
this file except in compliance with the License. A copy of the license is in the
LICENSE file, or at https://spdx.org/licenses/CDDL-1.1.txt

Note: CDDL 2.0 was checked against SPDX/Open Source Initiative registries and is
not a registered identifier; CDDL 1.1 is the canonical current CDDL release.

## Version History

See the VERSION HISTORY block at the top of app.py (APP_VERSION constant).

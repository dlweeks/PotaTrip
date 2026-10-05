# Installing POTATrip on a Raspberry Pi

The `potatrip_2.0.1_all.deb` release package works on **any architecture** —
it ships no pre-built binaries. The Python virtual environment is created
**on your Pi at install time** using the system `python3`, so the same
`.deb` runs on Raspberry Pi OS (arm64 or 32-bit), x86_64 Debian/Ubuntu, etc.

Tested target: Raspberry Pi OS 64-bit (Bookworm).

## 1. Prerequisites

```bash
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip
```

## 2. Install the package

Download the `.deb` from the
[GitHub releases page](https://github.com/dlweeks/PotaTrip/releases) and install:

```bash
wget https://github.com/dlweeks/PotaTrip/releases/download/v2.0.1/potatrip_2.0.1_all.deb
sudo dpkg -i potatrip_2.0.1_all.deb
```

What happens during install:

| Path | Purpose |
|---|---|
| `/opt/PotaTrip/` | App files (`app.py`, `index.html`, `requirements.txt`, LICENSE) |
| `/opt/PotaTrip/.venv/` | Python venv **built on your machine** (flask, pandas, geopy, requests) |
| `/usr/local/bin/potatrip` | Launcher |
| `/lib/systemd/system/potatrip.service` | systemd unit (enabled + started automatically) |
| `/var/lib/potatrip/` | Writable state: park CSV cache + log (owned by user `potatrip`) |

The first install downloads the Python dependencies from PyPI — a few
minutes on a Pi 3, under a minute on a Pi 4/5 with good network.

## 3. Verify

```bash
systemctl status potatrip
curl -s http://127.0.0.1:5001/health
# {"cache_valid":true,"status":"ok","version":"2.0.1"}
```

Open `http://<your-pi-ip>:5001` from any device on your LAN.

## 4. Configuration

The service reads these environment variables (set in the unit file;
override with `sudo systemctl edit potatrip` — a drop-in survives upgrades,
editing the unit file itself does not):

| Variable | Default (unit) | Meaning |
|---|---|---|
| `POTA_HOST` | `0.0.0.0` | Bind address |
| `POTA_PORT` | `5001` | TCP port |
| `POTA_CACHE_FILE` | `/var/lib/potatrip/all_parks_ext.csv` | Park database cache |
| `POTA_LOG_FILE` | `/var/lib/potatrip/pota_trip_log.txt` | Trip log |
| `POTA_OSRM_URL` | public OSRM server | Routing engine for Road Trip |
| `POTA_GEOCODE_UA` | generic | User-Agent for Nominatim geocoding |

If you publish the app beyond your LAN, set `POTA_GEOCODE_UA` to include
your callsign or email — Nominatim's usage policy expects a contact for
non-local traffic.

## 5. Upgrading

```bash
wget <new-version .deb URL>
sudo dpkg -i potatrip_<new>_all.deb
```

The service stops before files are replaced and restarts after. The venv
is reused and its packages refreshed.

## 6. Uninstalling

```bash
sudo dpkg -r potatrip        # remove (keeps /var/lib/potatrip state)
sudo dpkg -P potatrip        # purge (removes state, .venv, service user)
```

## 7. Routing the Pi through a VPN (e.g. 44.net via a GL.iNet router)

A common ham-radio setup: the Pi never touches the open internet directly —
all its traffic exits through a WireGuard VPN on a router.

1. On the GL.iNet router: **VPN → WireGuard Client → Add** and import your
   provider's client config (`.conf` or `.zip`).
2. Set the client's **Allowed IPs to `0.0.0.0/0`** — this makes the tunnel
   the default route for everything on the LAN.
3. Set **PersistentKeepalive to 25 s** — NAT gateways drop idle UDP
   mappings faster than the WireGuard handshake interval; without this the
   tunnel silently goes unreachable between requests.
4. Connect the Pi to the router's LAN and enable the client.
5. Verify from the Pi:

   ```bash
   curl -s https://ifconfig.me
   ```

   The answer should be the VPN-assigned IP, not your ISP's.

Notes for this topology:

- POTATrip fetches its park CSV from `pota.app` and routes from OSRM —
  both over HTTPS/HTTP outbound, which now egress from the VPN exit IP.
  Confirm your VPN plan allows general outbound traffic.
- Nothing needs port-forwarding for normal use. If you later want the app
  reachable from outside, add an explicit port-forward on the router's WAN
  side — never blanket-forward the VPN zone to the LAN.
- When something breaks, check the tunnel first (`wg show` or the router's
  VPN status page) — in this topology outages are almost always the VPN,
  not the app.

For publishing the app itself on a public 44Net address through this
topology (UCI port-forward, testing, troubleshooting), see
**[44NET-HOSTING.md](44NET-HOSTING.md)**.

## Building the package yourself

```bash
git clone https://github.com/dlweeks/PotaTrip
cd PotaTrip
make deb        # -> dist/potatrip_<version>_all.deb
```

Requires only `dpkg-deb` + `fakeroot` (stock Debian tooling). The build
tree contains no venv — it is created on the install target by `postinst`.

## License

CDDL-1.1 — see `LICENSE`. Copyright (c) N5SKT.

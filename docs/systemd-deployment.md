# Running POTA Trip Planner as a systemd Service

The Debian package installs and enables `potatrip.service`. This document covers
how the service is configured, how to run it on a different port or bind
address, and which firewall ports to open.

## Default configuration

The unit file lives at `/lib/systemd/system/potatrip.service` and runs:

```
/opt/potatrip/venv/bin/python /opt/potatrip/app.py
```

via the launcher `/usr/local/bin/potatrip`, as the dedicated system user
`potatrip` (nologin shell, no home outside the state dir).

Default environment set by the unit:

| Variable           | Default                          | Meaning                                        |
|--------------------|----------------------------------|------------------------------------------------|
| `POTA_HOST`        | `0.0.0.0`                        | Bind address — **globally reachable** by default |
| `POTA_PORT`        | `5001`                           | TCP port the web app listens on                 |
| `POTA_DEBUG`       | `0`                              | Never enable on a public bind (Werkzeug RCE)    |
| `POTA_CACHE_FILE`  | `/var/lib/potatrip/all_parks_ext.csv` | POTA park database cache                 |
| `POTA_LOG_FILE`    | `/var/lib/potatrip/pota_trip_log.txt` | Application log                          |

The app binds `0.0.0.0:5001` out of the box, i.e. it listens on **all
interfaces** (LAN and, if this host is internet-facing, the public internet).

## Changing the port (or bind address)

Do **not** edit `/lib/systemd/system/potatrip.service` directly — it is owned
by the package and will be overwritten on the next install. Use a systemd
drop-in override instead:

```bash
sudo systemctl edit potatrip
```

This opens an editor for `/etc/systemd/system/potatrip.service.d/override.conf`.
Because the base unit uses `Environment=` lines (which *merge*, not replace),
re-declare the variable you want to change:

```ini
[Service]
# Run on port 8080 instead of 5001
Environment=POTA_PORT=8080

# Optional: restrict to localhost only
# Environment=POTA_HOST=127.0.0.1
```

Then reload and restart:

```bash
sudo systemctl daemon-reload
sudo systemctl restart potatrip
```

Verify the new bind:

```bash
ss -tlnp | grep potatrip
# or
curl -s http://localhost:8080/health
```

Notes:

- Ports below 1024 (privileged ports) will **not** work as-is: the service runs
  as the unprivileged user `potatrip`. Either keep a high port and reverse-proxy
  (recommended — see below), or add to your override:

  ```ini
  [Service]
  AmbientCapabilities=CAP_NET_BIND_SERVICE
  ```

- To revert everything, delete the override:

  ```bash
  sudo rm -rf /etc/systemd/system/potatrip.service.d
  sudo systemctl daemon-reload
  sudo systemctl restart potatrip
  ```

- The override survives package upgrades, which is the intended behavior.

## Firewall: which ports to open

The application uses exactly **one inbound port** — the one it listens on
(default TCP 5001). Everything else is outbound.

### Inbound (open on the firewall)

| Port          | Protocol | Direction | Required for                                   |
|---------------|----------|-----------|------------------------------------------------|
| `5001/tcp`    | TCP      | inbound   | Default web UI / API access                    |
| *(your port)* | TCP      | inbound   | Only if you changed `POTA_PORT` via drop-in    |

Open **only** the single port you actually serve. Do not open a range.
No UDP is required.

### Outbound (must be allowed for the app to function)

These are client connections *from* the host — a tightly closed firewall that
blocks outbound will break the app unless these are permitted:

| Port   | Protocol | Used for                                          |
|--------|----------|---------------------------------------------------|
| 443/tcp | HTTPS   | Downloading the POTA park database (`pota.app`), Nominatim geocoding (`nominatim.openstreetmap.org`) |
| 53/udp + 53/tcp | DNS | Resolving those hostnames (if DNS isn't local-cached) |

### Examples

**ufw** (typical Ubuntu desktop/server firewall):

```bash
# Allow the app port from your LAN only (recommended)
sudo ufw allow from 192.168.1.0/24 to any port 5001 proto tcp

# Or from anywhere (only if you intend public exposure)
sudo ufw allow 5001/tcp

# Outbound is allowed by default in ufw; if you've denied outbound:
sudo ufw allow out 443/tcp
sudo ufw allow out 53
```

**firewalld** (RHEL/Fedora-style):

```bash
sudo firewall-cmd --permanent --add-port=5001/tcp
# restrict to LAN zone instead of public if possible:
# sudo firewall-cmd --permanent --zone=internal --add-port=5001/tcp
sudo firewall-cmd --reload
```

**nftables/iptables** (hand-rolled tight policy):

```bash
# Inbound: only the app port, established/related return traffic
iptables -A INPUT -p tcp --dport 5001 -m conntrack --ctstate NEW -j ACCEPT
iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
# Outbound: HTTPS + DNS for the service user
iptables -A OUTPUT -o eth0 -p tcp --dport 443 -j ACCEPT
iptables -A OUTPUT -o eth0 -p udp --dport 53 -j ACCEPT
iptables -A OUTPUT -o eth0 -p tcp --dport 53 -j ACCEPT
```

If you change the port via the drop-in, update the firewall rule to match —
the firewall knows nothing about `POTA_PORT`.

## Cloud / VPS security note

The Flask/Werkzeug server in this app is fine for personal and LAN use, but for
anything exposed to the public internet put it behind a reverse proxy with TLS:

```
internet → nginx :443 (TLS, basic auth optional) → 127.0.0.1:5001 (app)
```

In that setup:
- Set `POTA_HOST=127.0.0.1` in the drop-in (app listens locally only).
- Open **443/tcp** inbound; keep 5001 closed to the outside.
- nginx `proxy_pass http://127.0.0.1:5001;`

Minimal nginx example:

```nginx
server {
    listen 443 ssl;
    server_name trips.example.net;
    ssl_certificate     /etc/letsencrypt/live/trips.example.net/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/trips.example.net/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Useful service commands

```bash
sudo systemctl status potatrip        # state + recent log lines
sudo systemctl restart potatrip      # after config changes
sudo systemctl stop potatrip         # stop (stays enabled)
sudo systemctl disable potatrip      # don't start at boot
journalctl -u potatrip -f            # follow service logs
tail -f /var/lib/potatrip/pota_trip_log.txt   # app's own log file
```

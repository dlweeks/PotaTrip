# Hosting PotaTrip from Anywhere: 44net + GL.iNet WireGuard + Raspberry Pi

This document describes a self-hosted deployment that works from **any ISP,
anywhere** — including CGNAT'd connections with no public IP, no port
forwarding at the ISP, and no cooperation whatsoever from the upstream
network operator.

The same topology already runs the station's AllStar node successfully;
PotaTrip hangs off it the same way.

## Why this design

Most "self-host at home" guides assume you have a public IPv4 and can open
ports on your router. CGNAT takes both away. The usual workarounds
(cloud VPS relay, commercial tunnel services) add a monthly bill and a
third party in the middle of your traffic path.

44net solves it differently: you rent a **real IPv4 address** that lives
on 44net's network, and reach it through a **WireGuard tunnel your
equipment dials outbound**. CGNAT can't block it because the tunnel is
just another outbound UDP session — exactly like browsing a website.

Key properties:

- **Works behind any CGNAT**, any ISP, any modem-in-bridge mode. Nothing
  is required from the ISP beyond outbound UDP.
- **Nothing listens inbound on the WAN side.** Ever. The attack surface
  facing the ISP is zero.
- **Self-healing through CGNAT mapping churn.** WireGuard handshakes
  re-establish the NAT mapping automatically; `PersistentKeepalive`
  covers aggressive gateways.
- **Portable.** The whole stack — router config, Pi image, this repo —
  moves to a new house, a new ISP, a new country, a field site with a
  LTE router, by unplugging and replugging. The 44net address follows
  the tunnels, not the location.
- **No cloud dependency between you and your station.** The path is
  44net edge → your tunnel → your hardware.

## Topology

```
                     internet
                        │
              44net public IPv4 :443 (or :80)
                        │
          ┌─────────────┴─────────────┐
          │   44net edge / TLS term   │
          └─────────────┬─────────────┘
                        │  WireGuard (dialled OUT from home)
                        │  tunnel #2: potatrip
   ═══════════════ CGNAT boundary ═══════════════
                        │
          ┌─────────────┴─────────────┐
          │        GL.iNet router     │
          │  wg client #1 → AllStar   │
          │  wg client #2 → PotaTrip  │
          │  firewall zone: vpn       │
          │  port fwd: vpn:443 →     │
          │            pi:5001       │
          └─────────────┬─────────────┘
                        │  LAN (192.168.x.x)
              ┌─────────┴─────────┐
              │  Raspberry Pi 4   │
              │  potatrip.service │
              │  0.0.0.0:5001   │
              └───────────────────┘
```

The GL.iNet router terminates both WireGuard tunnels and owns the network
identity. The Pi is just a LAN host. The AllStar node and PotaTrip are
independent services behind independent tunnels.

## Why the router owns the tunnel (not the Pi)

- **Service vs. reachability separation.** Reimage, replace, or repurpose
  the Pi whenever you like — the tunnels and the public address don't
  move. If the Pi is down, the tunnel is still up and the router can
  serve a "node offline" page or simply drop the forward.
- **One crypto/firewall boundary.** WG handshakes, keepalives, and zone
  policy are configured once on the router, not per-host.
- **Proven pattern.** This is exactly how the AllStar node has been
  reachable 24/7 behind CGNAT. PotaTrip is a second tenant on the same
  pattern.
- **The Pi stays boring.** Boring is good: it runs one Flask app under
  systemd and knows nothing about how traffic reaches it.

## Setup checklist

### 1. GL.iNet router — WireGuard clients

In the GL.iNet admin (VPN → WireGuard Client), configure two clients:

| Setting | Value |
|---|---|
| VPN provider | Custom (44net) |
| Endpoint | 44net server hostname/IP + UDP port from your 44net config |
| Public key / private key / preshared key | from 44net peer configs |
| Allowed IPs (client side) | the 44net-routed prefixes only — **not** `0.0.0.0/0` |
| Persistent keepalive | **25 s** (both tunnels) |

Keepalive matters: CGNAT gateways expire idle UDP mappings; 25 s keeps
the mapping warm between handshakes.

### 2. Firewall zones

Each WG client should sit in its own zone (GL.iNet does this automatically
per VPN client — verify under Network → Firewall). Zone policy:

- Input: allow (the tunnel endpoint must accept handshakes and forwarded
  traffic destined for the forward below)
- Forward from `vpn` zone to LAN: allow **only** via the explicit port
  forward; do not enable blanket vpn→LAN forwarding.

### 3. Port forward (redirect)

Router → Network → Port Forward, with the **VPN interface as the source
zone**:

| Public (44net side) | Protocol | Internal |
|---|---|---|
| 443 | TCP | Pi LAN IP : 5001 |

(Second tunnel: 443 → AllStar host, same pattern, different tunnel.)

If 44net terminates TLS and forwards plain HTTP, this redirect lands
directly on Flask — no proxy needed on the Pi. If you want end-to-end
TLS, see the reverse-proxy note in
[systemd-deployment.md](systemd-deployment.md) and put Caddy/nginx on
the Pi with a DNS-01 certificate.

### 4. The Pi

Install per the main README (`make install` on the Pi — build natively,
see the arch note there). Bind config:

```
POTA_HOST=0.0.0.0     # fine: the Pi is on a private LAN behind the router
POTA_PORT=5001
```

No WireGuard on the Pi. No public exposure. The router's DNAT is the
only ingress path.

### 5. Outbound routing sanity check

With multiple WG clients on one router, verify the **default route**
policy explicitly:

- LAN internet egress: decide which interface (plain WAN is usually
  right; a WG tunnel as default egress makes your home browse from
  44net's address).
- PotaTrip's own outbound (pota.app CSV download, Nominatim geocoding)
  works over any egress; it does **not** need to come from the 44net
  address.
- Each WG client's `Allowed IPs` must list only the prefixes 44net
  routes for you — never `0.0.0.0/0` on a service tunnel.

## Firewall summary (the whole system)

| Boundary | Inbound | Outbound |
|---|---|---|
| ISP/CGNAT side of router | **none** | UDP → 44net WG endpoints; 443/80 + 53 as normal internet |
| Router vpn zone → LAN | only the explicit 443→5001 redirect | — |
| Router LAN | wide open (private) | per above |
| Pi | reachable only from LAN + redirected tunnel traffic | 443 (pota.app, geocoding), 53 (DNS) |

The tight-closed-host answer from the systemd doc collapses to: **zero
open inbound ports on the WAN interface.** CGNAT plus the outbound-only
tunnel does the work.

## Portability notes

This is the "it works anywhere" feature list:

- **New house, new ISP:** unplug router + Pi, replug. Re-enter nothing
  unless the ISP assigns different WAN settings. Tunnels redial; the
  44net address is unchanged.
- **Field day / portable:** a GL.iNet travel router on LTE + the Pi (or
  just the Pi with WG-on-Pi as a fallback) gets the same public address
  anywhere there's cellular signal.
- **Service swap:** replacing the Pi with any host at the same LAN IP
  keeps the published service alive with zero tunnel changes.
- **Multiple services:** each additional published service = one more
  WG client + one more port forward. AllStar and PotaTrip coexist this
  way today.

## Operational notes

- **Set your callsign in the geocoder UA.** Once published on a real
  address, set `POTA_GEOCODE_UA` (systemd drop-in) to your callsign +
  email per Nominatim's usage policy.
- **Watch the tunnel, not the app.** In practice the failure mode of
  this architecture is a WG tunnel that stopped redialling, not the
  Flask app. GL.iNet's VPN status page, or `wg show` on the router, is
  the first place to look when the service is "down."
- **44net plan details to confirm:** TLS termination model (edge vs.
  passthrough), allowed ports, and whether proxy protocol is available
  (lets the app/proxy see real client IPs instead of the tunnel peer).
- **Keep the Pi off the default route to the vpn zones** except through
  the explicit forward — same rule that keeps the AllStar node sane.

## Related documents

- [systemd-deployment.md](systemd-deployment.md) — service config,
  ports, drop-ins, reverse-proxy example
- [README.md](../README.md) — install, env vars, usage

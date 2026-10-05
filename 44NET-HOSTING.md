# Hosting POTATrip on 44Net (GL.iNet + Raspberry Pi)

This guide describes how to publish POTATrip to the internet using a
**44Net Connect** WireGuard tunnel terminated on a **GL.iNet (OpenWrt)**
router, with the app running on a Raspberry Pi behind it.

The result: your app is reachable at a real, globally routable amateur-radio
IPv4 address (`http://44.x.y.z:5001`) from anywhere — no port forwarding
on your ISP modem, no CGNAT problems, no cloud hosting. Your home network
exposes **zero** inbound ports to your ISP.

```
Internet / 44Net
      │  inbound to 44.x.y.z:5001
      ▼
44Net POP ──(WireGuard, initiated outbound from your router)──▶ GL.iNet router
                                        │  UCI DNAT redirect (persistent)
                                        ▼
                              Pi 192.168.8.x:5001  (potatrip.service)
```

**Why this topology:** the WireGuard tunnel is *initiated outward* from the
router, so nothing needs to be opened on your ISP-facing connection. The
44Net POP routes inbound traffic for your assigned address back down the
tunnel. The router's firewall then forwards exactly one port to exactly
one host. Replacing or reimaging the Pi never touches the tunnel or the
published address.

---

## Prerequisites

| Item | Notes |
|---|---|
| Valid amateur radio licence | 44Net is reserved for licensed hams; you register with your callsign |
| 44Net Connect account | Free, self-service at <https://connect.44net.cloud> |
| GL.iNet router (or any OpenWrt 21+ box) | Tested on the **GL.iNet Beryl AX (GL-MT3600BE)** — [available on Amazon](https://link.amazon/B0ijjgGGp); any model with WireGuard Client support works |
| Raspberry Pi (3/4/5) | Running Raspberry Pi OS Bookworm, wired (Ethernet) to the router |
| POTATrip `.deb` | From the [releases page](https://github.com/dlweeks/PotaTrip/releases) — see [PI-INSTALL.md](PI-INSTALL.md) |

---

## Step 1 — Obtain a 44Net Connect tunnel

Obtaining the tunnel itself is **beyond the scope of this document** —
sign-up, callsign validation, POP selection, and the client configuration
are covered by ARDC's own materials at
<https://connect.44net.cloud> and the ARDC 44Net community
(<https://ardc.groups.io/g/44net>).

What you need to walk away with before continuing:

- your assigned **44.x.y.z** address (write it down — this is your
  published address)
- the **wg-quick style client configuration** (`.conf`) for the tunnel

> ⚠️ The client config contains your **private key** and **preshared key**.
> Treat it like a password: never commit it to a repository, never paste it
> into chats or forums.

---

## Step 2 — Load the tunnel into the GL.iNet router

1. Log into the GL.iNet admin UI (default `http://192.168.8.1`).
2. **VPN → WireGuard Client → Add WireGuard Client.**
3. Import the 44Net Connect client config (paste or upload the `.conf`).
4. Confirm the settings that matter:
   - **Allowed IPs: `0.0.0.0/0`** — full-tunnel mode. This makes the VPN
     the default route for everything behind the router, which is what
     gives you the clean 44Net outbound identity *and* keeps the return
     path for inbound connections correct.
   - **Persistent Keepalive: 20–25 s** — mandatory. NAT gateways drop idle
     UDP mappings faster than the WireGuard handshake interval; without
     keepalive the tunnel goes silently unreachable between requests.
5. **Enable** the client. Verify:
   - the UI shows **connected**
   - from any device behind the router: `curl -s https://ifconfig.me`
     returns your assigned `44.x.y.z` address.

On the router's command line (SSH as root) the equivalent checks:

```bash
wg show
# interface: wgclient1
#   peer ... endpoint: <pop-ip>:<port>
#     allowed ips: 0.0.0.0/0, ::/0
#     latest handshake: N seconds ago     ← must be recent
#     persistent keepalive: every 20 seconds
```

> Note the WireGuard **interface name** shown (`wgclient1` on GL.iNet
> firmware for the first VPN client). You need it for Step 4.

---

## Step 3 — Install POTATrip on the Pi

Follow [PI-INSTALL.md](PI-INSTALL.md). In short:

```bash
sudo apt-get update && sudo apt-get install -y python3-venv python3-pip
wget https://github.com/dlweeks/PotaTrip/releases/download/v2.0.0/potatrip_2.0.0_all.deb
sudo dpkg -i potatrip_2.0.0_all.deb
systemctl status potatrip
curl -s http://127.0.0.1:5001/health
# {"cache_valid":true,"status":"ok","version":"2.0.1"}
```

The package builds the Python venv on the Pi at install time — the same
`.deb` works on any architecture.

**Wired only.** Connect the Pi to the GL.iNet by Ethernet. If the Pi also
joins a Wi-Fi network, it gains a second default route and a second IP on
a different subnet — a fail-open path where the Pi's traffic silently
leaves via Wi-Fi (un-VPN'd) if the wired link drops. Disable Wi-Fi on the Pi:

```bash
sudo nmcli radio wifi off        # NetworkManager (Bookworm desktop)
# or, dhcpcd lite image:
sudo ip link set wlan0 down
echo "denyinterfaces wlan0" | sudo tee -a /etc/dhcpcd.conf
sudo systemctl restart dhcpcd
```

Verify the Pi has exactly one IPv4 address and one default route:

```bash
ip -4 addr show    # only eth0, e.g. 192.168.8.x
ip route           # single: default via 192.168.8.1
```

**Pin the Pi's DHCP lease** on the GL.iNet (Network → DHCP → static lease
for the Pi's MAC address). The port-forward in Step 4 points at this
address; if the lease drifts, the published service breaks silently.

---

## Step 4 — Publish port 5001 through the tunnel (UCI redirect)

The tunnel terminates on the **router**, so inbound connections to your
44 address arrive at the router and must be redirected to the Pi. Use
OpenWrt's UCI — **not** raw `iptables` commands, which are wiped whenever
the firewall service reloads.

SSH into the GL.iNet as root:

```bash
uci add firewall redirect
uci set firewall.@redirect[-1].src='wgclient1'
uci set firewall.@redirect[-1].src_dport='5001'
uci set firewall.@redirect[-1].proto='tcp'
uci set firewall.@redirect[-1].target='DNAT'
uci set firewall.@redirect[-1].dest_ip='192.168.8.x'    # the Pi's address
uci set firewall.@redirect[-1].dest_port='5001'
uci commit firewall
/etc/init.d/firewall restart
```

This single redirect:
- DNATs inbound `44.x.y.z:5001` → `192.168.8.x:5001`
- automatically opens the matching hole in the firewall's FORWARD chain
  (fw3 accepts `ctstate DNAT` traffic from the source zone)
- **persists across reboots** — no `/etc/rc.local` hacks

Verify the rule is live and counting:

```bash
iptables -t nat -L zone_wgclient1_prerouting -n -v
# ... DNAT tcp dpt:5001 to:192.168.8.x:5001   ← packets should increment
```

> The zone name `wgclient1` matches the GL.iNet's first WireGuard client.
> Confirm yours with:
> `uci show firewall | grep -B1 -A3 "name='wgclient1'"`

---

## Step 5 — Test from outside your network

From any network **not** behind your router (phone on cellular, a VPS, a
friend):

```bash
curl.exe --max-time 8 http://44.x.y.z:5001/health     # Windows
curl  --max-time 8 http://44.x.y.z:5001/health        # Linux/macOS
# {"cache_valid":true,"status":"ok","version":"2.0.1"}
```

Then open `http://44.x.y.z:5001` in a browser and plan a trip.

---

## Troubleshooting (in the order that actually localizes faults)

**1. `ip route get <dest_ip>` on the router — run this BEFORE writing the
redirect.** If it answers `local ... dev lo`, the destination address
belongs to the router itself, not the Pi. DNATing to it produces an
instant RST from the router's TCP stack and looks exactly like "the VPN
is broken." This bites hardest when your main LAN and the GL.iNet LAN use
the **same subnet** (e.g. both `192.168.0.0/24`) and the Pi has addresses
on more than one network. Always take the target address from
`ip -4 addr show` **on the Pi**, using the interface that faces the
router.

**2. `wg show` handshake.** Recent handshake = tunnel healthy. If the
handshake is stale, the tunnel is down — check the client config and the
POP status before touching firewall rules.

**3. tcpdump on the tunnel interface:**
```bash
tcpdump -i wgclient1 -n 'tcp port 5001'
```
- **SYN arrives, instant (<1 ms) RST from your 44 address** → the DNAT
  rule isn't matching, or points at the router (see #1).
- **SYN arrives, RST after a LAN round-trip, DNAT counter moved** → the
  packet reached the Pi and the Pi refused it — check the service is
  bound to `0.0.0.0` (`ss -tlnp | grep 5001`), not `127.0.0.1`.
- **No SYN at all** → the POP isn't routing inbound to your tunnel.
  Check the tunnel record in the 44Net Connect dashboard shows your
  address assigned to this tunnel; if correct, ask on the ARDC 44Net
  group — it's a POP-side route.

**4. Raw iptables inserts not working?** GL.iNet's fw3 owns the chains
(`!fw3` comments). Anything added with raw `iptables -I` is flushed on
the next firewall reload. Always use `uci add firewall redirect`.

**5. Out from the Pi works but published service doesn't** → almost always
the redirect (Step 4), not the tunnel. In this topology, outages are the
VPN or the redirect; check `wg show` and the DNAT counter first.

---

## Security notes

You are now running a service on a **public IP with no NAT safety net**.

- **Forward only what you need.** One redirect, one port. Never blanket
  forward the VPN zone to the LAN.
- POTATrip ships with rate limiting, CSP/nosniff/DENY headers, input
  sanitization, and constraint caps (v1.7.0+). It is still a Flask/Werkzeug
  server — keep `POTA_DEBUG=0` (the package default) and keep the package
  updated.
- Set `POTA_GEOCODE_UA` to include your callsign or email
  (`sudo systemctl edit potatrip`) — Nominatim's usage policy expects a
  contact for published deployments.
- Expect scanner noise within hours of publishing. Watch
  `journalctl -u potatrip` occasionally; the rate limiter absorbs the
  casual stuff. If it gets heavy, restrict the redirect to known source
  ranges or put nginx in front.
- The tunnel config holds private keys — store it safely, never commit it.
- Consider HTTPS if you'll submit anything sensitive; with a 44Net
  address you can run a reverse proxy with a self-signed or
  acme.sh-issued cert on the router.

---

## Persistence checklist

| Component | Persists via |
|---|---|
| App + venv + service | `.deb` postinst → systemd unit, enabled |
| WireGuard tunnel | GL.iNet VPN client config |
| Port forward | UCI `firewall.@redirect[0]` |
| Pi address | **Pin the DHCP lease** — do this |
| Pi Wi-Fi disabled | NetworkManager radio state / dhcpcd denyinterfaces |

Reboot the router and the Pi once after setup and re-run the Step 5 test —
a config that survives a reboot is a config you can trust.

73 and happy activating! — N5SKT

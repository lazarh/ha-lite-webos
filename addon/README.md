# HA Lite — Home Assistant add-on

A high-contrast, remote-first Home Assistant dashboard for LG webOS 3.x TVs.
This add-on serves the dashboard and proxies the Home Assistant API, so there
is nothing to copy into `config/www` and no CORS configuration.

## Configuration

The **token** is set in the add-on options (masked). Everything else is edited
on the configuration page:

- Home Assistant -> Settings -> Add-ons -> HA Lite -> **Open Web UI**, or
- `http://<your-ha-host>:8099/?config=1`

There you can:

- **search** entities and tick real ones from the live Home Assistant list
  (no typing exact entity IDs, invalid ones cannot be picked);
- set the **title**;
- pick a **theme**: Amber, Blue, Emerald or Rose;
- pick a **layout**: auto-fit, large or small;
- set the **chart window** (hours) and **refresh interval** (seconds).

The configuration is stored in `/data/ha-lite.json` and survives updates.

## Open it

```
http://<your-ha-host>:8099/
```

The token and tile list come from the add-on; there is no on-TV setup.

## Keys

| Key | Action |
|---|---|
| D-pad | Move focus |
| OK | Toggle the focused switch/light |
| GREEN | Force an immediate refresh |
| BLUE | Configuration hint (the config page is browser-based) |

## Put it on the TV

Install the HA Lite launcher (sideload) and point it at the add-on URL:

```sh
LAUNCH_URL="http://<your-ha-host>:8099/" ./package.sh
ares-install --device tv dist/com.halite.dashboard_0.6.2_all.ipk
ares-launch --device tv com.halite.dashboard
```

The dashboard speaks to the add-on on the same origin; the add-on forwards
REST and WebSocket traffic to Home Assistant.

## Notes

- Keep the token in the add-on options; it is never stored on the TV.
- `https://` with a self-signed certificate is not trusted by webOS 3.x; use
  `http://` on the LAN.
- The add-on port is `8099` by default.

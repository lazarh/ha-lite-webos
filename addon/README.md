# HA Lite — Home Assistant add-on

A high-contrast, remote-first Home Assistant dashboard for LG webOS 3.x TVs.
This add-on serves the dashboard and proxies the Home Assistant API, so there
is nothing to copy into `config/www` and no CORS configuration.

## Configuration

| Option | Description |
|---|---|
| `token` | A long-lived Home Assistant access token (Profile → Security → Long-lived access tokens). |
| `entities` | The entity IDs to show on the TV, in order. Switches/lights/`input_boolean` are tappable; sensors show values and 24 h charts. |
| `title` | Dashboard title (default `HA Lite`). |
| `chart_hours` | History window for sensor sparklines, in hours (default `24`). |
| `refresh_seconds` | REST polling fallback interval (default `10`). |

Up to 12 tiles are shown.

## Open it

After starting the add-on, open:

```
http://<your-ha-host>:8099/
```

The token and tile list come from the add-on options; there is no on-TV setup.

## Put it on the TV

Install the HA Lite launcher (sideload) and point it at the add-on URL. From
the main repository:

```sh
LAUNCH_URL="http://<your-ha-host>:8099/" ./package.sh
ares-install --device tv dist/com.halite.dashboard_0.5.1_all.ipk
ares-launch --device tv com.halite.dashboard
```

The dashboard speaks to the add-on on the same origin; the add-on forwards
REST and WebSocket traffic to Home Assistant.

## Notes

- Keep the token in the add-on options; it is never stored on the TV.
- `https://` with a self-signed certificate is not trusted by webOS 3.x; use
  `http://` on the LAN.
- The add-on port is `8099` by default.

# HA Lite for webOS 3.x

A minimal, sideloadable Home Assistant dashboard for older LG smart TVs
(webOS 3.x, Chromium 38). Configure it entirely from the TV remote, then watch
switches and sensors with a high-contrast 10-foot UI. Live state changes arrive
over the Home Assistant WebSocket API.

## Architecture: same-origin on Home Assistant

Home Assistant's browser security policy blocks cross-origin API calls by
default (its `cors_allowed_origins` defaults to `cast.home-assistant.io` only).
Instead of weakening that, the app is served **by Home Assistant itself**:

- the app lives in `config/www/halite/`, so it is served at
  `/local/halite/index.html` on the same origin as `/api/` and `/api/websocket`;
- REST and WebSocket calls are therefore same-origin, with no CORS and no extra
  server configuration;
- the sideloaded webOS app is only a tiny **launcher** that opens that URL, so
  the dashboard still appears in the TV's launcher.

```
launcher/   webOS package installed on the TV (appinfo.json + redirect page)
webapp/     the real app; copy into Home Assistant's config/www/halite/
test/       same-origin mock Home Assistant (REST + WS) + smoke test
```

The token is stored in the TV's `localStorage`, never in a served file (served
files under `/local/` are public).

## Features

- Toggle tiles for `switch`, `light`, `input_boolean` (via `homeassistant.toggle`)
- Sensor tiles for `sensor` and `binary_sensor`: device-class SVG icon, large
  value + unit, and a 24-hour Canvas sparkline
- **WebSocket live updates** (`state_changed`), with a 10 s REST poll fallback
- D-pad configuration: URL (defaults to the page origin), token via a custom
  on-screen keyboard, and a two-tab picker (Toggles / Sensors)
- Up to 12 tiles; selection persists in `localStorage` across app restarts
- Status pill (LOADING / ONLINE / OFFLINE / TOKEN ERR)

## Configure from the TV

1. Launch **HA Lite** and press **BLUE** if settings are not already open.
2. **Server URL** is prefilled with the page's origin (same-origin). Leave it.
3. Select **Access token**, press **OK**, and type a long-lived token with the
   D-pad keyboard (Home Assistant: **Profile -> Long-lived access tokens**).
4. Select **Connect & choose tiles**.
5. Use **LEFT/RIGHT** to switch between **Toggles** and **Sensors**, **UP/DOWN**
   to move, **OK** to tick, then move to **Save selection** and press **OK**.
6. **OK** toggles the focused switch tile; sensor tiles are read-only.

### Optional: seed the token from a URL

```
http://<ha-host>:8123/local/halite/index.html?v=0.3.1#<long-lived-token>
```

The fragment is stored locally and stripped from the address bar.

## Controls

| Context | Keys |
|---|---|
| Dashboard | D-pad move, OK toggle, BLUE settings |
| Settings (connection) | UP/DOWN move, OK activate, BLUE/Back close |
| Entity picker | UP/DOWN move, LEFT/RIGHT tabs, OK tick, BLUE/Back |
| On-screen keyboard | Arrows move, OK type, BLUE/Back cancel |

Desktop shortcuts: arrows, Enter, `B`/`S` for BLUE, `Esc` to close.

## Deploy

1. **Copy the web app to Home Assistant**

   ```sh
   ssh root@<ha-host> 'mkdir -p /config/www/halite'
   scp webapp/index.html root@<ha-host>:/config/www/halite/index.html
   ```

   Verify `http://<ha-host>:8123/local/halite/index.html` returns the page.

   Home Assistant caches `/local/` files for 31 days. When you update the app,
   bump the `?v=` query in `launcher/index.html` (and reload) to bust the cache.

2. **Package and install the launcher**

   ```sh
   ares-package launcher -o dist
   ares-install --device tv dist/com.halite.dashboard_0.3.1_all.ipk
   ares-launch --device tv com.halite.dashboard
   ```

3. Set `LAUNCH_URL` in `launcher/index.html` if your host or path differs.

## Local development

```sh
./test/smoke.sh
```

The smoke test verifies:

- ES5 syntax (`es-check`) of the inline JavaScript;
- the entity list contains toggles and sensors;
- the history endpoint returns points;
- `homeassistant.toggle` changes state;
- WebSocket auth + a pushed `state_changed` event;
- first-run settings render and a configured render with a sensor canvas.

Manual run:

```sh
python3 test/mock_ha.py --port 8099
# open http://127.0.0.1:8099/local/halite/#demo-token
```

The mock serves the app, REST, a synthetic 24 h history and the WebSocket API
on one port, and pushes two live events after subscription.

## Hardware test checklist (webOS 3.x)

- [ ] `ares-package` + `ares-install` succeed and the app appears in the launcher
- [ ] Settings: URL prefilled, token entry works with the D-pad
- [ ] The picker shows Toggles and Sensors tabs; sensor rows are present
- [ ] Selecting switches and sensors and saving renders the tiles
- [ ] Sensor tiles show icon, value, unit and a 24 h sparkline
- [ ] Live WebSocket updates change tiles without waiting for the poll
- [ ] Closing and relaunching the app keeps the configuration
- [ ] Wrong token shows TOKEN ERR; stopping HA shows OFFLINE

## Compatibility

Target: **Chromium 38** (webOS 3.0; also covers 3.5/Chromium 53). The code uses
only ES5, `XMLHttpRequest`, `WebSocket`, `keyCode` events, flexbox, inline SVG
and Canvas 2D. No CSS grid, custom properties, `fetch`, arrow functions,
`let`/`const`, template literals, classes or external dependencies.

## Security notes

- The long-lived token is stored in the TV's `localStorage` for the Home
  Assistant origin. Treat the TV as a trusted device.
- No token is committed to this repository or embedded in any served file.
- Revoke the token in Home Assistant if the TV is lost or replaced.

## Scope

Implemented: on-TV configuration, toggles, sensor tiles with icons and 24 h
charts, WebSocket live updates with polling fallback, persistence, status.

Not yet: TV-optimized polish and layout tuning (Phase 4), larger chart detail
views, arbitrary cross-origin servers, theming.

## Deviations from the phase brief

- **WebSocket was added in this phase** (per request); the brief's steps only
  mentioned the REST API, but live updates are what make "values update as data
  changes" real.
- **All `sensor` and `binary_sensor` entities are selectable** (per choice), not
  just the numeric/chartable ones. Non-chartable sensors show a "no history"
  placeholder in the chart area.
- **24-hour chart window** (per choice) and a **two-tab picker**.
- **Tiles are capped at 12** to protect low-memory TV hardware; the picker shows
  the count.

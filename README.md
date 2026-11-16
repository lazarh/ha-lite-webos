# HA Lite for webOS 3.x

A minimal, sideloadable Home Assistant dashboard for older LG smart TVs
(webOS 3.x, Chromium 38). Configure it entirely from the TV remote: enter the
access token with an on-screen D-pad keyboard, pick switches/lights from a
D-pad list, and control them from a high-contrast tile grid.

## Architecture: same-origin on Home Assistant

Home Assistant's browser security policy blocks cross-origin API calls by
default (its `cors_allowed_origins` defaults to `cast.home-assistant.io` only).
Instead of weakening that, the app is served **by Home Assistant itself**:

- the app lives in `config/www/halite/`, so it is served at
  `/local/halite/index.html` on the same origin as `/api/`;
- calls to `/api/states/...` and `/api/services/...` are therefore same-origin,
  with no CORS and no extra server configuration;
- the sideloaded webOS app is only a tiny **launcher** that opens that URL, so
  the dashboard still appears in the TV's launcher.

```
launcher/   webOS package installed on the TV (appinfo.json + redirect page)
webapp/     the real app; copy into Home Assistant's config/www/halite/
test/       same-origin mock Home Assistant + smoke test
```

The token is stored in the TV's `localStorage`, never in a served file (served
files under `/local/` are public).

## Configure from the TV

1. Launch **HA Lite** and press **BLUE** if settings are not already open.
2. **Server URL** is prefilled with the page's origin (same-origin). Leave it
   unless you know you need a different host.
3. Select **Access token**, press **OK**, and type a long-lived token using the
   D-pad keyboard. Create one in Home Assistant under
   **Profile -> Long-lived access tokens**.
4. Select **Connect & choose switches**. This validates the token and loads
   the entity list (`switch`, `light`, `input_boolean`).
5. In the picker, use **UP/DOWN** to move, **OK** to tick entities, then move
   to **Save selection** and press **OK**.
6. The dashboard shows the selected entities. **OK** toggles the focused tile.

Everything persists in `localStorage` (`halite.config.v1`) and survives app
restarts.

### Optional: seed the token from a URL

For a one-time setup you can append the token to the URL instead of typing it:

```
http://<ha-host>:8123/local/halite/index.html?v=0.2.0#<long-lived-token>
```

The fragment is stored locally and stripped from the address bar. The on-TV
keyboard remains the primary path.

## Controls

| Context | Keys |
|---|---|
| Dashboard | D-pad move, OK toggle, BLUE settings |
| Settings (connection) | UP/DOWN move, OK activate, BLUE/Back close |
| Entity picker | UP/DOWN move, OK tick, BLUE/Back to connection |
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
   bump the `?v=` query in `launcher/index.html` (and reload) to bust the TV's
   cache.

2. **Package and install the launcher**

   ```sh
   ares-package launcher -o dist
   ares-install --device tv dist/com.halite.dashboard_0.2.0_all.ipk
   ares-launch --device tv com.halite.dashboard
   ```

3. Set `LAUNCH_URL` in `launcher/index.html` if your Home Assistant host or
   path differs.

## Local development

```sh
./test/smoke.sh
```

The smoke test:

- extracts and syntax-checks the inline JavaScript;
- runs `es-check es5`;
- starts a same-origin mock Home Assistant (`test/mock_ha.py`) that serves both
  the app and `/api/`;
- checks the entity list, rejects unauthenticated reads, and toggles an entity
  via `homeassistant.toggle`;
- renders the first-run settings overlay and a configured three-tile dashboard
  in headless Chromium.

Manual run:

```sh
python3 test/mock_ha.py --port 8099
# open http://127.0.0.1:8099/local/halite/#demo-token
```

## Hardware test checklist (webOS 3.x)

- [ ] `ares-package` + `ares-install` succeed and the app appears in the launcher
- [ ] BLUE opens Settings; URL is prefilled with the HA origin
- [ ] Token entry works with the D-pad keyboard
- [ ] Connect loads the entity list; sensors are not listed
- [ ] Multiple entities can be ticked and saved
- [ ] The dashboard shows the selected tiles; OK toggles the focused tile
- [ ] Closing and relaunching the app keeps the configuration
- [ ] Wrong token shows TOKEN ERR; stopping HA shows OFFLINE

## Compatibility

Target: **Chromium 38** (webOS 3.0; also covers 3.5/Chromium 53). The code
uses only ES5, `XMLHttpRequest`, `keyCode` keyboard events, flexbox and plain
CSS. No CSS grid, custom properties, `fetch`, arrow functions, `let`/`const`,
template literals, classes or external dependencies.

## Security notes

- The long-lived token is stored in the TV's `localStorage` for the Home
  Assistant origin. Treat the TV as a trusted device.
- No token is committed to this repository or embedded in any served file.
- Revoke the token in Home Assistant if the TV is lost or replaced.

## Scope

Implemented: on-TV connection setup (D-pad keyboard), entity list, multi-select
of `switch`/`light`/`input_boolean`, multi-tile dashboard, persistence,
`homeassistant.toggle`, connection status.

Not yet: sensor value tiles and charts (Phase 3), WebSocket live updates,
polish/layout tuning (Phase 4), arbitrary cross-origin servers.

## Deviations from the phase brief

- **Server URL defaults to the same origin** and token-only entry is the
  supported path; arbitrary cross-origin URLs are not offered because they
  would require CORS changes on the HA side.
- **Selectable domains** are `switch`, `light`, and `input_boolean` (all
  toggleable via `homeassistant.toggle`), not only `switch.*`.
- **Keyboard entry** uses a custom D-pad keyboard rather than `window.prompt()`,
  which is unreliable on webOS Chromium.

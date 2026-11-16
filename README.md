# HA Lite for webOS 3.x

A minimal, sideloadable Home Assistant dashboard for older LG smart TVs
(webOS 3.x, Chromium 38). Phase 1 renders a **single high-contrast switch tile**
and toggles it with the TV remote, talking to Home Assistant's REST API.

## Architecture: same-origin on Home Assistant

Home Assistant's browser security policy blocks cross-origin API calls by
default (its `cors_allowed_origins` defaults to `cast.home-assistant.io` only).
Instead of weakening that, the real app is served **by Home Assistant itself**:

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

The token is never stored in a served file. On first run it is read from a URL
fragment (which browsers do not send to the server), then stored in the TV's
`localStorage` and stripped from the address bar.

## Configure

Edit the `CONFIG` block at the top of `webapp/index.html`:

```js
var CONFIG = {
  entityId: 'switch.esphome_web_e4c400_3d_auto',
  fallbackName: 'Bedroom 3 e4c400 3D Auto',
  tokenStorageKey: 'halite.token',
  pollSeconds: 10
};
```

The entity must be a `switch.*` (or any entity that supports the
`switch.toggle` service). Phase 1 deliberately renders one tile only.

Set `LAUNCH_URL` in `launcher/index.html` to wherever you host the app, e.g.
`http://your-ha-host:8123/local/halite/`.

## Deploy

1. **Copy the web app to Home Assistant**

   ```sh
   scp webapp/index.html root@your-ha-host:/config/www/halite/index.html
   ```

   (Create `/config/www/halite/` first if needed.) Verify:
   `http://<ha-host>:8123/local/halite/index.html` returns the page.

   Home Assistant caches `/local/` files for 31 days. When you update the app,
   bump the `?v=` query in `launcher/index.html` (and reload the page) to bust
   the TV's cache.

2. **Package and install the launcher**

   ```sh
   ares-package launcher -o dist
   ares-install --device tv dist/com.halite.dashboard_0.1.0_all.ipk
   ares-launch --device tv com.halite.dashboard
   ```

3. **Seed the token once**

   Open the app URL with the token appended, e.g.

   ```
   http://your-ha-host:8123/local/halite/index.html?v=0.1.0#<long-lived-token>
   ```

   Create the token in Home Assistant under **Profile -> Long-lived access
   tokens**. The app stores it locally and removes it from the URL.

   For a one-time device seed you can also temporarily set `SEED_TOKEN` in
   `launcher/index.html` before packaging, then revert it. Never commit a real
   token.

## Controls

| Action | Remote | Desktop |
|--------|--------|---------|
| Toggle the switch | OK / Enter | Enter |

## Local development

```sh
./test/smoke.sh
```

The smoke test:

- extracts and syntax-checks the inline JavaScript;
- runs `es-check es5`;
- starts a same-origin mock Home Assistant (`test/mock_ha.py`) that serves both
  the app and `/api/`;
- verifies authenticated read, rejected unauthenticated read, and a real toggle;
- renders the page in headless Chromium and checks the tile.

Manual run:

```sh
python3 test/mock_ha.py --port 8099
# open http://127.0.0.1:8099/local/halite/#demo-token
```

The mock stores state in memory and logs every request.

## Hardware test checklist (webOS 3.x)

- [ ] `ares-package` + `ares-install` succeed and the app appears in the TV launcher
- [ ] The dashboard opens and the tile shows the current state (ON/OFF)
- [ ] The status pill reads ONLINE
- [ ] Pressing OK on the remote toggles the switch; the tile flips immediately
- [ ] Home Assistant shows the new state for the entity
- [ ] Wrong / expired token shows TOKEN ERR
- [ ] Stopping Home Assistant shows OFFLINE while the last state remains visible

## Compatibility

Target: **Chromium 38** (webOS 3.0; also covers 3.5/Chromium 53). The code
uses only ES5, `XMLHttpRequest`, `keyCode` keyboard events, flexbox and plain
CSS. No CSS grid, custom properties, `fetch`, arrow functions, `let`/`const`,
template literals, classes or external dependencies.

## Security notes

- The long-lived token is stored in the TV's `localStorage` for the Home
  Assistant origin. Treat the TV as a trusted device.
- No token is committed to this repository or embedded in any served file.
- Use a token with the narrowest scope you can; revoke it in Home Assistant if
  the TV is lost or replaced.

## Phase 1 scope

In: sideloadable launcher, one switch tile, REST authentication, remote toggle,
optimistic state update, connection/error status.

Out: on-TV configuration UI (Phase 2), sensor tiles and charts (Phase 3),
multi-tile layouts and TV polish (Phase 4), WebSocket live updates (later
phase), mouse/touch/voice input.

## Deviations from the phase brief

- **Config is code-only, not `prompt()`** - `window.prompt()` is unreliable in
  webOS 3.x Chromium, so the entity is set in `CONFIG` and the token seeded via
  a URL fragment.
- **Chromium 38** is the floor (the brief mentions both 38 and 53; 38
  compatibility covers both).
- **Hardware validation** is performed against the owner's TV via `ares-*`;
  results are recorded in the phase report rather than in an automated test.

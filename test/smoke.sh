#!/bin/sh
# HA Lite Phase 3 smoke test.
# Verifies: ES5 syntax, same-origin app serving, entity list, history,
# WebSocket auth + pushed state, toggle, and a configured sensor/switch render.

set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

PORT="${PORT:-8099}"
PORT2=$((PORT + 1))
BASE="http://127.0.0.1:$PORT"
BASE2="http://127.0.0.1:$PORT2"
TOKEN="${TOKEN:-demo-token}"
TMP=$(mktemp -d)
MOCK_PID=""
MOCK2_PID=""
MOCK3_PID=""

cleanup() {
  for pid in ${MOCK_PID:-} ${MOCK2_PID:-} ${MOCK3_PID:-}; do
    [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
  done
  rm -rf "$TMP"
}
trap cleanup EXIT INT TERM

wait_for() {
  url=$1
  i=0
  while [ "$i" -lt 100 ]; do
    if curl -fsS -H "Authorization: Bearer $TOKEN" "$url/api/" >/dev/null 2>&1; then
      return 0
    fi
    i=$((i + 1))
    sleep 0.1
  done
  return 1
}

echo "== extract inline JavaScript =="
python3 - "$TMP/app.js" <<'PY'
import re
import sys

html = open("webapp/index.html", encoding="utf-8").read()
match = re.search(r"<script>(.*)</script>", html, re.S)
if not match:
    raise SystemExit("no inline <script> found in webapp/index.html")
open(sys.argv[1], "w", encoding="utf-8").write(match.group(1))
PY

echo "== syntax check (node) =="
node --check "$TMP/app.js"

echo "== ES5 compatibility (es-check) =="
if command -v npx >/dev/null 2>&1; then
  npx --yes es-check es5 "$TMP/app.js"
else
  echo "npx not found - skipping es-check" >&2
fi

echo "== start mock Home Assistant on port $PORT =="
python3 test/mock_ha.py --port "$PORT" --token "$TOKEN" >"$TMP/mock.log" 2>&1 &
MOCK_PID=$!
wait_for "$BASE" || { echo "mock server did not start" >&2; cat "$TMP/mock.log" >&2; exit 1; }

echo "== app is served same-origin =="
curl -fsS "$BASE/local/halite/index.html" | grep -q 'id="grid"'

echo "== entity list includes toggles and sensors =="
curl -fsS -H "Authorization: Bearer $TOKEN" "$BASE/api/states" \
  | python3 -c 'import sys, json; d = json.load(sys.stdin); domains = set(x["entity_id"].split(".")[0] for x in d); assert {"switch", "light", "input_boolean", "sensor", "binary_sensor"} <= domains, domains; print("domains:", ",".join(sorted(domains)))'

echo "== unauthenticated read is rejected =="
code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/states")
[ "$code" = "401" ] || { echo "expected 401, got $code" >&2; exit 1; }

echo "== history endpoint =="
curl -fsS -H "Authorization: Bearer $TOKEN" \
  "$BASE/api/history/period/2026-01-01T00:00:00Z?filter_entity_id=sensor.living_room_temperature&minimal_response" \
  | python3 -c 'import sys, json; d = json.load(sys.stdin); assert d and len(d[0]) > 10, "short history"; print("history points:", len(d[0]))'

echo "== toggle via homeassistant.toggle =="
start_state=$(curl -fsS -H "Authorization: Bearer $TOKEN" "$BASE/api/states/switch.desk_lamp" \
  | python3 -c 'import sys, json; print(json.load(sys.stdin)["state"])')
curl -fsS -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"entity_id":"switch.desk_lamp"}' \
  "$BASE/api/services/homeassistant/toggle" >/dev/null
end_state=$(curl -fsS -H "Authorization: Bearer $TOKEN" "$BASE/api/states/switch.desk_lamp" \
  | python3 -c 'import sys, json; print(json.load(sys.stdin)["state"])')
[ "$start_state" != "$end_state" ] || { echo "state did not change" >&2; exit 1; }
echo "toggled: $start_state -> $end_state"

echo "== websocket auth + pushed state_changed =="
if python3 -c 'import websockets' >/dev/null 2>&1; then
  python3 - "$PORT" "$TOKEN" <<'PY'
import asyncio
import json
import sys

import websockets

port = int(sys.argv[1])
token = sys.argv[2]


async def main():
    async with websockets.connect("ws://127.0.0.1:%d/api/websocket" % port) as ws:
        first = json.loads(await ws.recv())
        assert first.get("type") == "auth_required", first
        await ws.send(json.dumps({"type": "auth", "access_token": token}))
        auth = json.loads(await ws.recv())
        assert auth.get("type") == "auth_ok", auth
        await ws.send(json.dumps({"id": 1, "type": "subscribe_events", "event_type": "state_changed"}))
        result = json.loads(await ws.recv())
        assert result.get("success") is True, result
        event = json.loads(await asyncio.wait_for(ws.recv(), timeout=6))
        assert event.get("type") == "event", event
        entity = event["event"]["data"]["entity_id"]
        state = event["event"]["data"]["new_state"]["state"]
        print("ws event:", entity, "=", state)


asyncio.run(main())
PY
else
  echo "websockets module not available - skipping WS check" >&2
fi

if command -v chromium >/dev/null 2>&1; then
  echo "== first-run render (settings overlay) =="
  chromium --headless --no-sandbox --disable-gpu --hide-scrollbars \
    --user-data-dir="$TMP/profile1" --window-size=1920,1080 --virtual-time-budget=4000 \
    --dump-dom "$BASE/local/halite/index.html" 2>/dev/null >"$TMP/dom1.html"
  grep -q 'id="settings" class="overlay"' "$TMP/dom1.html"
  grep -q "http://127.0.0.1:$PORT" "$TMP/dom1.html"
  echo "settings overlay opened with origin URL"

  echo "== configured render (switches + sensor chart + binary sensor) =="
  python3 - "$TMP/seeded.html" <<'PY'
import sys

html = open("webapp/index.html", encoding="utf-8").read()
seed = """
<script>
try {
  localStorage.setItem('halite.config.v1', JSON.stringify({
    url: window.location.origin,
    token: 'demo-token',
    entities: ['switch.desk_lamp', 'light.living_room',
               'sensor.living_room_temperature', 'binary_sensor.front_door']
  }));
} catch (e) {}
</script>
"""
html = html.replace("</head>", seed + "</head>")
open(sys.argv[1], "w", encoding="utf-8").write(html)
PY
  python3 test/mock_ha.py --port "$PORT2" --token "$TOKEN" --webapp "$TMP/seeded.html" >"$TMP/mock2.log" 2>&1 &
  MOCK2_PID=$!
  wait_for "$BASE2" || { echo "second mock did not start" >&2; cat "$TMP/mock2.log" >&2; exit 1; }

  chromium --headless --no-sandbox --disable-gpu --hide-scrollbars \
    --user-data-dir="$TMP/profile2" --window-size=1920,1080 --virtual-time-budget=6000 \
    --dump-dom "$BASE2/local/halite/index.html" 2>/dev/null >"$TMP/dom2.html"
  [ "$(grep -o 'class="tile' "$TMP/dom2.html" | wc -l)" -eq 4 ]
  grep -q 'class="spark"' "$TMP/dom2.html"
  grep -q 'Desk Lamp' "$TMP/dom2.html"
  grep -q 'Living Room Temperature' "$TMP/dom2.html"
  grep -q 'Front Door' "$TMP/dom2.html"
  grep -q 'id="settings" class="overlay hidden"' "$TMP/dom2.html"
  echo "four tiles rendered (including sensor canvas)"

  echo "== add-on mode render (config.json, no on-TV setup) =="
  cat > "$TMP/addon.json" <<'JSON'
{"token":"demo-token","title":"HA Lite","chart_hours":12,"refresh_seconds":5,"entities":["switch.desk_lamp","sensor.living_room_temperature","binary_sensor.front_door"]}
JSON
  PORT3=$((PORT + 2))
  BASE3="http://127.0.0.1:$PORT3"
  python3 test/mock_ha.py --port "$PORT3" --token "$TOKEN" --addon-config "$TMP/addon.json" >"$TMP/mock3.log" 2>&1 &
  MOCK3_PID=$!
  wait_for "$BASE3" || { echo "third mock did not start" >&2; cat "$TMP/mock3.log" >&2; exit 1; }

  curl -fsS "$BASE3/local/halite/config.json" | grep -q '"entities"'
  chromium --headless --no-sandbox --disable-gpu --hide-scrollbars \
    --user-data-dir="$TMP/profile3" --window-size=1920,1080 --virtual-time-budget=6000 \
    --dump-dom "$BASE3/local/halite/index.html" 2>/dev/null >"$TMP/dom3.html"
  [ "$(grep -o 'class="tile' "$TMP/dom3.html" | wc -l)" -eq 3 ]
  grep -q 'id="settings" class="overlay hidden"' "$TMP/dom3.html"
  grep -q 'D-PAD Move' "$TMP/dom3.html"
  if grep -q 'BLUE Settings' "$TMP/dom3.html"; then
    echo "footer should not advertise settings in add-on mode" >&2
    exit 1
  fi
  echo "add-on mode rendered 3 tiles with settings disabled"

  echo "== add-on config POST =="
  curl -fsS -X POST -H "Content-Type: application/json" \
    -d '{"entities":["switch.desk_lamp","sensor.living_room_temperature"],"theme":"blue","layout":"small","chart_hours":12,"refresh_seconds":5}' \
    "$BASE3/local/halite/api/config" | grep -q '"ok": true'
  curl -fsS "$BASE3/local/halite/config.json" \
    | python3 -c 'import sys, json; d = json.load(sys.stdin); assert d["theme"] == "blue", d; assert d["layout"] == "small", d; assert len(d["entities"]) == 2, d; print("config saved:", d["theme"], d["layout"], len(d["entities"]), "entities")'

  echo "== config UI render =="
  chromium --headless --no-sandbox --disable-gpu --hide-scrollbars \
    --user-data-dir="$TMP/profile4" --window-size=1920,1080 --virtual-time-budget=8000 \
    --dump-dom "$BASE3/local/halite/index.html?config=1" 2>/dev/null >"$TMP/dom4.html"
  grep -q 'id="config" class="overlay"' "$TMP/dom4.html"
  grep -q 'Configure HA Lite' "$TMP/dom4.html"
  grep -q 'Desk Lamp' "$TMP/dom4.html"
  echo "config UI rendered with entity list"
else
  echo "chromium not found - skipping render checks" >&2
fi

echo
echo "SMOKE TEST PASSED"

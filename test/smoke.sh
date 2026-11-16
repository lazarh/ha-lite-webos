#!/bin/sh
# HA Lite Phase 2 smoke test.
# Verifies: ES5 syntax, same-origin app serving, entity list, toggle,
# first-run settings render, and a configured multi-tile dashboard render.

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

cleanup() {
  for pid in ${MOCK_PID:-} ${MOCK2_PID:-}; do
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

echo "== entity list includes toggleable domains =="
curl -fsS -H "Authorization: Bearer $TOKEN" "$BASE/api/states" \
  | python3 -c 'import sys, json; d = json.load(sys.stdin); domains = set(x["entity_id"].split(".")[0] for x in d); assert {"switch", "light", "input_boolean"} <= domains, domains; print("domains:", ",".join(sorted(domains)))'

echo "== unauthenticated read is rejected =="
code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/states")
[ "$code" = "401" ] || { echo "expected 401, got $code" >&2; exit 1; }

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

if command -v chromium >/dev/null 2>&1; then
  echo "== first-run render (settings overlay) =="
  chromium --headless --no-sandbox --disable-gpu --hide-scrollbars \
    --user-data-dir="$TMP/profile1" --window-size=1920,1080 --virtual-time-budget=4000 \
    --dump-dom "$BASE/local/halite/index.html" 2>/dev/null >"$TMP/dom1.html"
  grep -q 'id="settings" class="overlay"' "$TMP/dom1.html"
  grep -q "http://127.0.0.1:$PORT" "$TMP/dom1.html"
  echo "settings overlay opened with origin URL"

  echo "== configured dashboard render (three tiles) =="
  python3 - "$TMP/seeded.html" <<'PY'
import sys

html = open("webapp/index.html", encoding="utf-8").read()
seed = """
<script>
try {
  localStorage.setItem('halite.config.v1', JSON.stringify({
    url: window.location.origin,
    token: 'demo-token',
    entities: ['switch.desk_lamp', 'light.living_room', 'input_boolean.guest_mode']
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
    --user-data-dir="$TMP/profile2" --window-size=1920,1080 --virtual-time-budget=5000 \
    --dump-dom "$BASE2/local/halite/index.html" 2>/dev/null >"$TMP/dom2.html"
  [ "$(grep -o 'class="tile' "$TMP/dom2.html" | wc -l)" -eq 3 ]
  grep -q 'Desk Lamp' "$TMP/dom2.html"
  grep -q 'Living Room Light' "$TMP/dom2.html"
  grep -q 'Guest Mode' "$TMP/dom2.html"
  grep -q 'id="settings" class="overlay hidden"' "$TMP/dom2.html"
  echo "three configured tiles rendered"
else
  echo "chromium not found - skipping render checks" >&2
fi

echo
echo "SMOKE TEST PASSED"

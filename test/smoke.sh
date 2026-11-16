#!/bin/sh
# HA Lite Phase 1 smoke test.
# Verifies: ES5 syntax, same-origin app serving, REST read, REST toggle,
# and (when Chromium is available) a real render of the tile.

set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

PORT="${PORT:-8099}"
BASE="http://127.0.0.1:$PORT"
TOKEN="${TOKEN:-demo-token}"
TMP=$(mktemp -d)
MOCK_PID=""

cleanup() {
  if [ -n "$MOCK_PID" ]; then
    kill "$MOCK_PID" 2>/dev/null || true
    wait "$MOCK_PID" 2>/dev/null || true
  fi
  rm -rf "$TMP"
}
trap cleanup EXIT INT TERM

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

ready=0
i=0
while [ "$i" -lt 100 ]; do
  if curl -fsS -H "Authorization: Bearer $TOKEN" "$BASE/api/" >/dev/null 2>&1; then
    ready=1
    break
  fi
  i=$((i + 1))
  sleep 0.1
done

if [ "$ready" -ne 1 ]; then
  echo "mock server did not start" >&2
  cat "$TMP/mock.log" >&2 || true
  exit 1
fi

echo "== app is served same-origin =="
curl -fsS "$BASE/local/halite/" | grep -q 'id="tile"'

echo "== authenticated read =="
curl -fsS -H "Authorization: Bearer $TOKEN" "$BASE/api/states/switch.esphome_web_e4c400_3d_auto" \
  | python3 -c 'import sys, json; d = json.load(sys.stdin); assert d["state"] in ("on", "off"), d; print("state:", d["state"])'

start_state=$(curl -fsS -H "Authorization: Bearer $TOKEN" "$BASE/api/states/switch.esphome_web_e4c400_3d_auto" \
  | python3 -c 'import sys, json; print(json.load(sys.stdin)["state"])')

echo "== unauthenticated read is rejected =="
code=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/api/states/switch.esphome_web_e4c400_3d_auto")
[ "$code" = "401" ] || { echo "expected 401, got $code" >&2; exit 1; }

echo "== toggle =="
curl -fsS -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"entity_id":"switch.esphome_web_e4c400_3d_auto"}' \
  "$BASE/api/services/switch/toggle" >/dev/null

end_state=$(curl -fsS -H "Authorization: Bearer $TOKEN" "$BASE/api/states/switch.esphome_web_e4c400_3d_auto" \
  | python3 -c 'import sys, json; print(json.load(sys.stdin)["state"])')

if [ "$start_state" = "$end_state" ]; then
  echo "state did not change (still $end_state)" >&2
  exit 1
fi
echo "toggled: $start_state -> $end_state"

echo "== headless render =="
if command -v chromium >/dev/null 2>&1; then
  chromium --headless --no-sandbox --disable-gpu --hide-scrollbars \
    --user-data-dir="$TMP/profile" --window-size=1920,1080 --virtual-time-budget=4000 \
    --dump-dom "$BASE/local/halite/#$TOKEN" 2>/dev/null >"$TMP/dom.html"
  grep -q 'id="tile"' "$TMP/dom.html"
  grep -q 'Bedroom 3 e4c400 3D Auto' "$TMP/dom.html"
  echo "tile rendered with entity name"
else
  echo "chromium not found - skipping render check" >&2
fi

echo
echo "SMOKE TEST PASSED"

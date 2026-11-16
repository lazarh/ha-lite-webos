#!/bin/sh
set -eu

HTML_DIR=/usr/share/nginx/html
OPTIONS=/data/options.json

mkdir -p "$HTML_DIR"

if [ -f "$OPTIONS" ]; then
  token="$(jq -r '.token // ""' "$OPTIONS")"
  title="$(jq -r '.title // "HA Lite"' "$OPTIONS")"
  chart_hours="$(jq -r '.chart_hours // 24' "$OPTIONS")"
  refresh_seconds="$(jq -r '.refresh_seconds // 10' "$OPTIONS")"
  entities="$(jq -c '.entities // []' "$OPTIONS")"

  jq -n \
    --arg token "$token" \
    --arg title "$title" \
    --argjson chart_hours "$chart_hours" \
    --argjson refresh_seconds "$refresh_seconds" \
    --argjson entities "$entities" \
    '{token:$token,title:$title,chart_hours:$chart_hours,refresh_seconds:$refresh_seconds,entities:$entities}' \
    > "$HTML_DIR/config.json"
else
  echo "No /data/options.json found; serving an empty configuration" >&2
  printf '%s\n' '{"token":"","entities":[]}' > "$HTML_DIR/config.json"
fi

exec nginx -g 'daemon off;'

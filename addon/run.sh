#!/bin/sh
set -eu

python3 /config_server.py &
server_pid=$!

# Wait for the config sidecar before nginx starts proxying to it.
i=0
while [ "$i" -lt 50 ]; do
  if wget -q -O /dev/null http://127.0.0.1:8098/config.json 2>/dev/null; then
    break
  fi
  i=$((i + 1))
  sleep 0.1
done

exec nginx -g 'daemon off;'

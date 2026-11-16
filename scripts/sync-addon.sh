#!/bin/sh
# Copies the webapp into the add-on build context (Supervisor builds addons
# from their own folder, so the app must live inside addon/).
set -eu

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$ROOT/addon/webapp"
cp "$ROOT/webapp/index.html" "$ROOT/addon/webapp/index.html"
echo "synced addon/webapp/index.html"

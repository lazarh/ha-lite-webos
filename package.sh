#!/usr/bin/env bash
#
# Builds a valid webOS .ipk from launcher/ using only standard Linux tools
# (ar + tar). No LG webOS SDK / ares-cli needed.
#
# The Home Assistant URL is substituted at build time:
#
#   LAUNCH_URL="http://your-ha-host:8123/local/halite/index.html?v=0.4.0" ./package.sh
#
# Output: dist/com.halite.dashboard_<version>_all.ipk
#
# Without LAUNCH_URL a template IPK is produced that shows a configuration
# message instead of opening a page.
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$ROOT/launcher"
APP_ID="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["id"])' "$SRC/appinfo.json")"
VERSION="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["version"])' "$SRC/appinfo.json")"
ARCH="all"
PKG_NAME="${APP_ID}_${VERSION}_${ARCH}.ipk"

OUT_DIR="$ROOT/dist"
BUILD_DIR="$ROOT/build"
DATA_DIR="$BUILD_DIR/data"
CTRL_DIR="$BUILD_DIR/control"
APP_DIR="$DATA_DIR/usr/palm/applications/$APP_ID"
IPK="$OUT_DIR/$PKG_NAME"

APP_FILES=(appinfo.json index.html icon.png largeIcon.png)

cd "$ROOT"

# ------------------------------------------------------------- staging
echo ">> Staging launcher files"
rm -rf "$BUILD_DIR"
mkdir -p "$APP_DIR" "$CTRL_DIR"

for entry in "${APP_FILES[@]}"; do
  if [[ ! -e "$SRC/$entry" ]]; then
    echo "Missing launcher file: $entry" >&2
    exit 1
  fi
  cp -r "$SRC/$entry" "$APP_DIR/"
done

if [[ -n "${LAUNCH_URL:-}" ]]; then
  echo ">> Using LAUNCH_URL=$LAUNCH_URL"
  python3 - "$APP_DIR/index.html" "$LAUNCH_URL" <<'PY'
import sys

path, url = sys.argv[1], sys.argv[2]
html = open(path, encoding="utf-8").read()
html = html.replace("__LAUNCH_URL__", url)
open(path, "w", encoding="utf-8").write(html)
PY
  if grep -q '__LAUNCH_URL__' "$APP_DIR/index.html"; then
    echo "Failed to substitute LAUNCH_URL" >&2
    exit 1
  fi
else
  echo ">> WARNING: LAUNCH_URL is not set; this IPK will show a configuration message." >&2
fi

# ------------------------------------------------------- control file
cat > "$CTRL_DIR/control" <<EOF
Package: $APP_ID
Version: $VERSION
Architecture: $ARCH
Maintainer: HA Lite <lhristov@gmail.com>
Section: misc
Priority: optional
Installed-Size: $(du -sk "$APP_DIR" | cut -f1)
Description: HA Lite - Home Assistant dashboard for LG webOS 3.x TVs
 A high-contrast, remote-first dashboard that talks to Home Assistant
 over the local network. This launcher opens the app served from Home
 Assistant's /local/ folder.
EOF

# -------------------------------------------- ipk members (Debian style)
echo ">> Creating control.tar.gz and data.tar.gz"
echo "2.0" > "$BUILD_DIR/debian-binary"

# Reproducible archives: normalized mtimes/ownership, no gzip timestamp.
TAR_OPTS=(--sort=name --mtime='@0' --owner=0 --group=0 --numeric-owner)
tar -C "$CTRL_DIR" "${TAR_OPTS[@]}" -cf - . | gzip -9n > "$BUILD_DIR/control.tar.gz"
tar -C "$DATA_DIR" "${TAR_OPTS[@]}" -cf - .       | gzip -9n > "$BUILD_DIR/data.tar.gz"

# ----------------------------------------------------------- assemble
# The webOS install service expects the ar header layout used by
# ares-package (mode 100644, space padded member names, no trailing slash).
echo ">> Assembling $PKG_NAME"
mkdir -p "$OUT_DIR"
rm -f "$IPK"

write_ar_member() {
  local file="$1" name size
  name="$(basename "$file")"
  size="$(wc -c < "$file" | tr -d '[:space:]')"
  printf '%-16s%-12s%-6s%-6s%-8s%-10s`\n' "$name" 0 0 0 100644 "$size" >> "$IPK"
  cat "$file" >> "$IPK"
  if (( size % 2 )); then
    printf '\n' >> "$IPK"
  fi
}

printf '!<arch>\n' > "$IPK"
write_ar_member "$BUILD_DIR/debian-binary"
write_ar_member "$BUILD_DIR/control.tar.gz"
write_ar_member "$BUILD_DIR/data.tar.gz"

# ------------------------------------------------------------- verify
echo ">> Verifying package"
members="$(ar t "$IPK")"
for member in debian-binary control.tar.gz data.tar.gz; do
  if ! grep -qx "$member" <<< "$members"; then
    echo "ERROR: $member is missing from $IPK" >&2
    exit 1
  fi
done

# Note: grep -q inside a pipefail pipeline can kill tar with SIGPIPE, so
# capture the listing into a variable first.
listing="$(ar p "$IPK" data.tar.gz | tar -tzf - 2>/dev/null || true)"
if ! grep -qx "./usr/palm/applications/$APP_ID/appinfo.json" <<< "$listing"; then
  echo "ERROR: app payload missing from $IPK" >&2
  exit 1
fi

echo ">> Built $IPK"
ls -lh "$IPK"

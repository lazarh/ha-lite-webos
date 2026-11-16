#!/usr/bin/env python3
"""Same-origin mock Home Assistant for HA Lite development.

Serves BOTH the web app (at /local/halite/) and a tiny slice of the Home
Assistant REST API on one port, mirroring how Home Assistant serves the
real app from config/www.

    python3 test/mock_ha.py --port 8099
    open http://127.0.0.1:8099/local/halite/#demo-token

Token: demo-token (override with --token). Not for production use.
"""
import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ENTITY_ID = "switch.esphome_web_e4c400_3d_auto"
FRIENDLY_NAME = "Bedroom 3 e4c400 3D Auto"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEBAPP = os.path.join(ROOT, "webapp", "index.html")

STATE = {"state": "on"}
CONFIG = {"token": "demo-token"}


def entity_payload():
    return {
        "entity_id": ENTITY_ID,
        "state": STATE["state"],
        "attributes": {
            "friendly_name": FRIENDLY_NAME,
        },
        "last_changed": "2026-01-01T00:00:00+00:00",
        "last_updated": "2026-01-01T00:00:00+00:00",
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "MockHA/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("[mock-ha] %s %s\n" % (self.client_address[0], fmt % args))

    def _send(self, code, body, content_type="application/json"):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self):
        return self.headers.get("Authorization", "") == "Bearer " + CONFIG["token"]

    def _deny(self):
        self._send(401, json.dumps({"message": "Unauthorized"}))

    def do_OPTIONS(self):
        # Not needed for same-origin requests, but harmless during development.
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        if path in ("/", "/local/halite", "/local/halite/", "/local/halite/index.html"):
            try:
                with open(WEBAPP, "r", encoding="utf-8") as fh:
                    html = fh.read()
            except OSError as exc:
                self._send(500, json.dumps({"message": str(exc)}))
                return
            self._send(200, html, "text/html; charset=utf-8")
            return

        if path == "/api/":
            if not self._authorized():
                self._deny()
                return
            self._send(200, "API running.", "text/plain; charset=utf-8")
            return

        if path == "/api/states/" + ENTITY_ID:
            if not self._authorized():
                self._deny()
                return
            self._send(200, json.dumps(entity_payload()))
            return

        self._send(404, json.dumps({"message": "Not found"}))

    def do_POST(self):
        path = urlparse(self.path).path

        if path != "/api/services/switch/toggle":
            self._send(404, json.dumps({"message": "Not found"}))
            return

        if not self._authorized():
            self._deny()
            return

        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            payload = {}

        if payload.get("entity_id") == ENTITY_ID:
            STATE["state"] = "off" if STATE["state"] == "on" else "on"
            sys.stderr.write("[mock-ha] toggled %s -> %s\n" % (ENTITY_ID, STATE["state"]))

        self._send(200, json.dumps([entity_payload()]))


def main():
    global WEBAPP

    parser = argparse.ArgumentParser(description="Mock Home Assistant for HA Lite")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8099)
    parser.add_argument("--token", default="demo-token")
    parser.add_argument("--webapp", default=WEBAPP, help="path to the app HTML to serve")
    args = parser.parse_args()

    WEBAPP = args.webapp
    CONFIG["token"] = args.token

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    sys.stderr.write(
        "[mock-ha] serving app + API on http://%s:%d/local/halite/ (token: %s)\n"
        % (args.host, args.port, args.token)
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

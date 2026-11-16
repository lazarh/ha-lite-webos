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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEBAPP = os.path.join(ROOT, "webapp", "index.html")

ENTITY_DATA = {
    "switch.esphome_web_e4c400_3d_auto": {
        "state": "on",
        "attributes": {"friendly_name": "Bedroom 3 e4c400 3D Auto"},
    },
    "switch.shellyplugsg3_coffee_machine": {
        "state": "off",
        "attributes": {"friendly_name": "Coffee machine"},
    },
    "switch.sonoff_water_pump": {
        "state": "off",
        "attributes": {"friendly_name": "Water pump"},
    },
    "switch.desk_lamp": {
        "state": "on",
        "attributes": {"friendly_name": "Desk Lamp"},
    },
    "light.living_room": {
        "state": "on",
        "attributes": {"friendly_name": "Living Room Light"},
    },
    "light.kitchen": {
        "state": "off",
        "attributes": {"friendly_name": "Kitchen Light"},
    },
    "input_boolean.guest_mode": {
        "state": "off",
        "attributes": {"friendly_name": "Guest Mode"},
    },
    "sensor.temperature": {
        "state": "21.4",
        "attributes": {"friendly_name": "Temperature", "unit_of_measurement": "\u00b0C"},
    },
    "binary_sensor.front_door": {
        "state": "off",
        "attributes": {"friendly_name": "Front Door"},
    },
}

CONFIG = {"token": "demo-token"}


def state_payload(entity_id):
    entry = ENTITY_DATA[entity_id]
    return {
        "entity_id": entity_id,
        "state": entry["state"],
        "attributes": dict(entry["attributes"]),
        "last_changed": "2026-01-01T00:00:00+00:00",
        "last_updated": "2026-01-01T00:00:00+00:00",
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "MockHA/1.1"

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

        if path == "/api/states":
            if not self._authorized():
                self._deny()
                return
            self._send(200, json.dumps([state_payload(eid) for eid in ENTITY_DATA]))
            return

        prefix = "/api/states/"
        if path.startswith(prefix):
            if not self._authorized():
                self._deny()
                return
            entity_id = path[len(prefix):]
            if entity_id in ENTITY_DATA:
                self._send(200, json.dumps(state_payload(entity_id)))
            else:
                self._send(404, json.dumps({"message": "Entity not found"}))
            return

        self._send(404, json.dumps({"message": "Not found"}))

    def do_POST(self):
        path = urlparse(self.path).path
        parts = path.strip("/").split("/")

        # /api/services/<domain>/<service>  (homeassistant/toggle is the one we use)
        if len(parts) != 4 or parts[0] != "api" or parts[1] != "services":
            self._send(404, json.dumps({"message": "Not found"}))
            return

        if not self._authorized():
            self._deny()
            return

        domain = parts[2]
        service = parts[3]
        if service != "toggle" or domain not in ("homeassistant", "switch", "light", "input_boolean"):
            self._send(404, json.dumps({"message": "Service not found"}))
            return

        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            payload = {}

        entity_id = payload.get("entity_id", "")
        if entity_id in ENTITY_DATA:
            current = ENTITY_DATA[entity_id]["state"]
            ENTITY_DATA[entity_id]["state"] = "off" if current == "on" else "on"
            sys.stderr.write("[mock-ha] toggled %s -> %s\n"
                             % (entity_id, ENTITY_DATA[entity_id]["state"]))
            self._send(200, json.dumps([state_payload(entity_id)]))
            return

        self._send(200, "[]")


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

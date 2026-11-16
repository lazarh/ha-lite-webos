#!/usr/bin/env python3
"""HA Lite add-on configuration sidecar.

Reads the token from the Supervisor options (/data/options.json) and stores
the user-editable configuration (entities, title, theme, layout, chart window,
refresh interval) in /data/ha-lite.json. Serves /config.json and /api/config.
"""
import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

OPTIONS = "/data/options.json"
STORE = "/data/ha-lite.json"
PORT = 8098

ALLOWED_THEMES = ("amber", "blue", "emerald", "rose")
ALLOWED_LAYOUTS = ("auto", "large", "small")
MAX_ENTITIES = 12
KEYS = ("entities", "title", "theme", "layout", "chart_hours", "refresh_seconds")

DEFAULTS = {
    "entities": [],
    "title": "HA Lite",
    "theme": "amber",
    "layout": "auto",
    "chart_hours": 24,
    "refresh_seconds": 10,
}


def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def load_token():
    options = read_json(OPTIONS, {}) or {}
    token = options.get("token", "")
    return token if isinstance(token, str) else ""


def _int(value, default, low, high):
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def load_config():
    stored = read_json(STORE, {}) or {}
    config = dict(DEFAULTS)

    entities = stored.get("entities")
    if isinstance(entities, list):
        config["entities"] = [e for e in entities if isinstance(e, str)][:MAX_ENTITIES]
    if isinstance(stored.get("title"), str) and stored["title"].strip():
        config["title"] = stored["title"].strip()[:60]
    if stored.get("theme") in ALLOWED_THEMES:
        config["theme"] = stored["theme"]
    if stored.get("layout") in ALLOWED_LAYOUTS:
        config["layout"] = stored["layout"]
    config["chart_hours"] = _int(stored.get("chart_hours"), 24, 1, 168)
    config["refresh_seconds"] = _int(stored.get("refresh_seconds"), 10, 1, 3600)
    return config


def save_config(payload):
    config = load_config()

    entities = payload.get("entities")
    if isinstance(entities, list):
        unique = []
        for entity_id in entities:
            if isinstance(entity_id, str) and entity_id and entity_id not in unique:
                unique.append(entity_id)
        config["entities"] = unique[:MAX_ENTITIES]

    if isinstance(payload.get("title"), str) and payload["title"].strip():
        config["title"] = payload["title"].strip()[:60]
    if payload.get("theme") in ALLOWED_THEMES:
        config["theme"] = payload["theme"]
    if payload.get("layout") in ALLOWED_LAYOUTS:
        config["layout"] = payload["layout"]
    config["chart_hours"] = _int(payload.get("chart_hours"), config["chart_hours"], 1, 168)
    config["refresh_seconds"] = _int(payload.get("refresh_seconds"), config["refresh_seconds"], 1, 3600)

    temp = STORE + ".tmp"
    with open(temp, "w", encoding="utf-8") as fh:
        json.dump(config, fh)
    os.replace(temp, STORE)
    return config


def supervisor_options():
    """Read the add-on options via the Supervisor API (upgrade migration)."""
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    if not token:
        return {}
    try:
        request = urllib.request.Request(
            "http://supervisor/addons/self/info",
            headers={"Authorization": "Bearer " + token},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
        options = (data.get("data") or {}).get("options") or {}
        return options if isinstance(options, dict) else {}
    except Exception:
        return {}


def migrate_legacy():
    """Seed the UI config from the old Supervisor options on first run."""
    if os.path.exists(STORE):
        return
    options = read_json(OPTIONS, {}) or {}

    # Older versions kept entities/title/layout in the Supervisor options.
    # The schema change can strip those from /data/options.json, so fall back
    # to the Supervisor's stored options.
    if not options.get("entities"):
        extra = supervisor_options()
        for key in KEYS:
            if key not in options and key in extra:
                options[key] = extra[key]

    seed = {key: options[key] for key in KEYS if key in options}
    if seed:
        save_config(seed)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, content_type="application/json"):
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/config.json") or self.path.startswith("/api/config"):
            migrate_legacy()
        if self.path.startswith("/config.json"):
            payload = {"token": load_token()}
            payload.update(load_config())
            self._send(200, json.dumps(payload))
        elif self.path.startswith("/api/config"):
            self._send(200, json.dumps(load_config()))
        else:
            self._send(404, json.dumps({"message": "Not found"}))

    def do_POST(self):
        if not self.path.startswith("/api/config"):
            self._send(404, json.dumps({"message": "Not found"}))
            return

        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._send(400, json.dumps({"message": "Invalid JSON"}))
            return
        if not isinstance(payload, dict):
            self._send(400, json.dumps({"message": "Invalid payload"}))
            return

        config = save_config(payload)
        self._send(200, json.dumps({"ok": True, "config": config}))


def main():
    migrate_legacy()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()

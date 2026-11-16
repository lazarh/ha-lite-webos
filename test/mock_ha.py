#!/usr/bin/env python3
"""Same-origin mock Home Assistant for HA Lite development (HTTP + WebSocket).

Serves BOTH the web app (at /local/halite/) and a tiny slice of the Home
Assistant API on one port, including the WebSocket API and a synthetic
24-hour history endpoint.

    python3 test/mock_ha.py --port 8099
    open http://127.0.0.1:8099/local/halite/#demo-token

Token: demo-token (override with --token). Not for production use.
"""
import argparse
import asyncio
import base64
import hashlib
import json
import math
import os
import struct
import sys
import time
from urllib.parse import unquote, urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEBAPP = os.path.join(ROOT, "webapp", "index.html")

CONFIG = {"token": "demo-token"}

ENTITY_DATA = {
    "switch.desk_lamp": {
        "state": "on",
        "attributes": {"friendly_name": "Desk Lamp"},
    },
    "switch.coffee_machine": {
        "state": "off",
        "attributes": {"friendly_name": "Coffee machine"},
    },
    "light.living_room": {
        "state": "on",
        "attributes": {"friendly_name": "Living Room Light"},
    },
    "input_boolean.guest_mode": {
        "state": "off",
        "attributes": {"friendly_name": "Guest Mode"},
    },
    "sensor.living_room_temperature": {
        "state": "21.4",
        "attributes": {
            "friendly_name": "Living Room Temperature",
            "unit_of_measurement": "\u00b0C",
            "device_class": "temperature",
            "state_class": "measurement",
        },
        "history": (21.0, 2.4),
    },
    "sensor.humidity": {
        "state": "48",
        "attributes": {
            "friendly_name": "Humidity",
            "unit_of_measurement": "%",
            "device_class": "humidity",
            "state_class": "measurement",
        },
        "history": (48.0, 6.0),
    },
    "sensor.power": {
        "state": "120",
        "attributes": {
            "friendly_name": "Power",
            "unit_of_measurement": "W",
            "device_class": "power",
            "state_class": "measurement",
        },
        "history": (120.0, 60.0),
    },
    "sensor.energy": {
        "state": "12.3",
        "attributes": {
            "friendly_name": "Energy Today",
            "unit_of_measurement": "kWh",
            "device_class": "energy",
            "state_class": "total_increasing",
        },
        "history": (12.0, 1.0),
    },
    "sensor.battery": {
        "state": "87",
        "attributes": {
            "friendly_name": "Battery",
            "unit_of_measurement": "%",
            "device_class": "battery",
            "state_class": "measurement",
        },
        "history": (87.0, 2.0),
    },
    "sensor.signal": {
        "state": "-61",
        "attributes": {
            "friendly_name": "Wi-Fi Signal",
            "unit_of_measurement": "dBm",
            "device_class": "signal_strength",
            "state_class": "measurement",
        },
        "history": (-61.0, 6.0),
    },
    "sensor.pressure": {
        "state": "1013",
        "attributes": {
            "friendly_name": "Pressure",
            "unit_of_measurement": "hPa",
            "device_class": "pressure",
            "state_class": "measurement",
        },
        "history": (1013.0, 4.0),
    },
    "sensor.uptime_text": {
        "state": "3 days",
        "attributes": {"friendly_name": "Uptime"},
        "history": None,
    },
    "binary_sensor.front_door": {
        "state": "off",
        "attributes": {"friendly_name": "Front Door", "device_class": "door"},
    },
    "binary_sensor.motion": {
        "state": "off",
        "attributes": {"friendly_name": "Hallway Motion", "device_class": "motion"},
    },
}


def log(message):
    sys.stderr.write("[mock-ha] %s\n" % message)
    sys.stderr.flush()


def iso_time(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(epoch)) + "Z"


def state_payload(entity_id):
    entry = ENTITY_DATA[entity_id]
    return {
        "entity_id": entity_id,
        "state": entry["state"],
        "attributes": dict(entry["attributes"]),
        "last_changed": "2026-01-01T00:00:00+00:00",
        "last_updated": "2026-01-01T00:00:00+00:00",
    }


def history_payload(entity_id):
    """Return the HA history shape: a list containing one list of records."""
    entry = ENTITY_DATA.get(entity_id)
    if not entry or not entry.get("history"):
        return [[]]

    base, amplitude = entry["history"]
    now = time.time()
    count = 49
    span = 24 * 3600
    records = []
    for i in range(count):
        t = now - span + (span * i / float(count - 1))
        phase = i / float(count - 1)
        value = base + amplitude * math.sin(phase * 2 * math.pi) + ((i % 3) - 1) * 0.1
        records.append({
            "entity_id": entity_id,
            "state": "%.2f" % value,
            "last_changed": iso_time(t),
        })
    return [records]


def http_response(status, body, content_type="application/json"):
    reason = {200: "OK", 204: "No Content", 401: "Unauthorized", 404: "Not Found"}.get(status, "OK")
    data = body.encode("utf-8")
    headers = [
        "HTTP/1.1 %d %s" % (status, reason),
        "Content-Type: %s" % content_type,
        "Content-Length: %d" % len(data),
        "Access-Control-Allow-Origin: *",
        "Access-Control-Allow-Headers: Authorization, Content-Type",
        "Access-Control-Allow-Methods: GET, POST, OPTIONS",
        "Connection: close",
    ]
    return ("\r\n".join(headers) + "\r\n\r\n").encode("ascii") + data


async def read_frame(reader):
    header = await reader.readexactly(2)
    b1, b2 = header[0], header[1]
    opcode = b1 & 0x0F
    masked = bool(b2 & 0x80)
    length = b2 & 0x7F
    if length == 126:
        length = struct.unpack(">H", await reader.readexactly(2))[0]
    elif length == 127:
        length = struct.unpack(">Q", await reader.readexactly(8))[0]
    mask = await reader.readexactly(4) if masked else b"\x00\x00\x00\x00"
    payload = await reader.readexactly(length) if length else b""
    if masked:
        payload = bytes(payload[i] ^ mask[i % 4] for i in range(len(payload)))
    return opcode, payload


def frame(payload, opcode=0x1):
    data = payload.encode("utf-8") if isinstance(payload, str) else payload
    header = bytearray([0x80 | opcode])
    n = len(data)
    if n < 126:
        header.append(n)
    elif n < 65536:
        header.append(126)
        header += struct.pack(">H", n)
    else:
        header.append(127)
        header += struct.pack(">Q", n)
    return bytes(header) + data


async def send_json(writer, obj):
    writer.write(frame(json.dumps(obj)))
    await writer.drain()


def state_event(entity_id):
    return {
        "id": 1,
        "type": "event",
        "event": {
            "event_type": "state_changed",
            "data": {
                "entity_id": entity_id,
                "new_state": state_payload(entity_id),
            },
        },
    }


async def ws_session(reader, writer):
    log("ws: client connected")
    try:
        await send_json(writer, {"type": "auth_required", "ha_version": "2026.1.0-mock"})
        opcode, payload = await read_frame(reader)
        if opcode == 0x8:
            return
        msg = json.loads(payload.decode("utf-8"))
        if msg.get("type") != "auth" or msg.get("access_token") != CONFIG["token"]:
            await send_json(writer, {"type": "auth_invalid", "message": "Invalid access token"})
            log("ws: auth_invalid")
            return
        await send_json(writer, {"type": "auth_ok", "ha_version": "2026.1.0-mock"})
        log("ws: auth_ok")

        subscription_id = 1
        while True:
            opcode, payload = await read_frame(reader)
            if opcode == 0x8:
                return
            if opcode == 0x9:
                writer.write(frame(payload, 0xA))
                await writer.drain()
                continue
            msg = json.loads(payload.decode("utf-8"))
            if msg.get("type") == "subscribe_events":
                subscription_id = msg.get("id", 1)
                await send_json(writer, {"id": subscription_id, "type": "result", "success": True, "result": None})
                log("ws: subscribe_events")
                break

        await asyncio.sleep(1.2)
        ENTITY_DATA["sensor.living_room_temperature"]["state"] = "24.1"
        await send_json(writer, state_event("sensor.living_room_temperature"))
        log("ws: pushed temperature=24.1")

        await asyncio.sleep(0.8)
        ENTITY_DATA["binary_sensor.front_door"]["state"] = "on"
        await send_json(writer, state_event("binary_sensor.front_door"))
        log("ws: pushed front_door=on")

        while True:
            opcode, payload = await read_frame(reader)
            if opcode == 0x8:
                return
            if opcode == 0x9:
                writer.write(frame(payload, 0xA))
                await writer.drain()
    except (asyncio.IncompleteReadError, ConnectionError, json.JSONDecodeError) as exc:
        log("ws: closed (%s)" % type(exc).__name__)
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def read_request(reader):
    raw = await reader.readuntil(b"\r\n\r\n")
    head = raw.decode("latin-1")
    lines = head.split("\r\n")
    request_line = lines[0] if lines else ""
    parts = request_line.split(" ")
    method = parts[0] if len(parts) > 0 else ""
    path = parts[1] if len(parts) > 1 else "/"
    headers = {}
    for line in lines[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
    return method, path, headers


async def handle(reader, writer):
    try:
        method, raw_path, headers = await read_request(reader)
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError):
        writer.close()
        return

    parsed = urlparse(raw_path)
    path = parsed.path
    query = parsed.query
    log("%s %s" % (method, path))

    if headers.get("upgrade", "").lower() == "websocket":
        key = headers.get("sec-websocket-key", "")
        accept = base64.b64encode(
            hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
        ).decode("ascii")
        writer.write(
            ("HTTP/1.1 101 Switching Protocols\r\n"
             "Upgrade: websocket\r\n"
             "Connection: Upgrade\r\n"
             "Sec-WebSocket-Accept: %s\r\n\r\n" % accept).encode("ascii")
        )
        await writer.drain()
        await ws_session(reader, writer)
        return

    if method == "OPTIONS":
        writer.write(http_response(204, ""))
        await writer.drain()
        writer.close()
        return

    auth = headers.get("authorization", "")
    if path.startswith("/api/") and auth != "Bearer " + CONFIG["token"]:
        writer.write(http_response(401, json.dumps({"message": "Unauthorized"})))
        await writer.drain()
        writer.close()
        return

    if path in ("/", "/local/halite", "/local/halite/", "/local/halite/index.html"):
        try:
            with open(WEBAPP, "r", encoding="utf-8") as fh:
                html = fh.read()
        except OSError as exc:
            writer.write(http_response(500, json.dumps({"message": str(exc)})))
            await writer.drain()
            writer.close()
            return
        writer.write(http_response(200, html, "text/html; charset=utf-8"))
    elif path == "/api/":
        writer.write(http_response(200, "API running.", "text/plain; charset=utf-8"))
    elif path == "/api/states":
        writer.write(http_response(200, json.dumps([state_payload(eid) for eid in ENTITY_DATA])))
    elif path.startswith("/api/states/"):
        entity_id = path[len("/api/states/"):]
        if entity_id in ENTITY_DATA:
            writer.write(http_response(200, json.dumps(state_payload(entity_id))))
        else:
            writer.write(http_response(404, json.dumps({"message": "Entity not found"})))
    elif path.startswith("/api/history/period/"):
        entity_id = ""
        for part in query.split("&"):
            if part.startswith("filter_entity_id="):
                entity_id = unquote(part[len("filter_entity_id="):])
        writer.write(http_response(200, json.dumps(history_payload(entity_id))))
    elif method == "POST" and path.startswith("/api/services/"):
        length = int(headers.get("content-length", "0") or "0")
        body = await reader.readexactly(length) if length else b"{}"
        try:
            payload = json.loads(body.decode("utf-8"))
            entity_id = payload.get("entity_id", "")
        except (ValueError, UnicodeDecodeError):
            entity_id = ""
        parts = path.strip("/").split("/")
        domain = parts[2] if len(parts) > 2 else ""
        if entity_id in ENTITY_DATA and (
            domain == "homeassistant" or entity_id.startswith(domain + ".")
        ):
            current = ENTITY_DATA[entity_id]["state"]
            ENTITY_DATA[entity_id]["state"] = "off" if current == "on" else "on"
            log("toggled %s -> %s" % (entity_id, ENTITY_DATA[entity_id]["state"]))
            writer.write(http_response(200, json.dumps([state_payload(entity_id)])))
        else:
            writer.write(http_response(200, "[]"))
    else:
        writer.write(http_response(404, json.dumps({"message": "Not found"})))

    await writer.drain()
    writer.close()
    try:
        await writer.wait_closed()
    except Exception:
        pass


async def main_async(host, port):
    server = await asyncio.start_server(handle, host, port)
    log("serving app + REST/WS on http://%s:%d/local/halite/ (token: %s)"
        % (host, port, CONFIG["token"]))
    async with server:
        await server.serve_forever()


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

    try:
        asyncio.run(main_async(args.host, args.port))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

"""
Yaquod Fake Vehicle Simulator
==============================
Simulates an embedded device for local development and testing.

What it does:
  1. Calls POST /login on the local FastAPI backend (seeds Redis with auth).
  2. Connects to MQTT and subscribes to inbound command topics.
  3. Periodically publishes fake vehicle state (telemetry) and GPS location.
  4. Processes inbound agent commands in real time — when the agent sends
     an action (e.g. ac_on, set_temperature), the simulator applies it to
     its internal state and publishes the updated state back, just like a
     real vehicle would.

Usage:
  conda activate livekit-agent
  python scripts/fake_vehicle_simulator.py

Environment (reads from .env automatically):
  MQTT_HOST, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD, MQTT_SSL

Hardcoded defaults match the static test credentials in validation_service.py:
  vehicle_id = vehicle_001
  vin_number = VIN_12345
"""

import asyncio
import contextlib
import json
import logging
import math
import os
import signal
import ssl
import sys
import time
from typing import Any

import aiomqtt
import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("fake-vehicle")

# ── Configuration ──────────────────────────────────────────────────────────────
VEHICLE_ID = os.getenv("FAKE_VEHICLE_ID", "vehicle_001")
VIN_NUMBER = os.getenv("FAKE_VIN_NUMBER", "VIN_12345")
JWT_TOKEN = os.getenv("FAKE_JWT_TOKEN", "JWT_SECRET_TOKEN")
BACKEND_URL = os.getenv("FAKE_BACKEND_URL", "https://yaquod-agent.fastapicloud.dev")

MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USERNAME", "") or None
MQTT_PASS = os.getenv("MQTT_PASSWORD", "") or None
MQTT_SSL_ON = os.getenv("MQTT_SSL", "false").lower() == "true"

STATE_INTERVAL_S = 20  # publish full state every N seconds
LOCATION_INTERVAL_S = 10  # publish GPS every N seconds

_background_tasks = set()

# ── Fake telemetry state (mutable) ─────────────────────────────────────────────
# Mimics a real embedded device payload. Updated in place when commands arrive.
STATE: dict[str, Any] = {
    "vin_number": VIN_NUMBER,
    "vehicle_model": "Yaquod EV",
    "vehicle_color": "Pearl White",
    "plate_num": "ABC-1234",
    "number_of_seats": 4,
    "battery_level": 82,
    "speed": 0.0,
    "pickup_point_name": "Cairo International Airport",
    "destination_name": "Tahrir Square",
    "remaining_distance": 14.3,
    "remaining_time": 22.0,
    "expected_trip_duration": 30.0,
    # Cabin
    "ac_status": "on",
    "ac_temperature": 22.0,
    "ac_fan_speed": 2,
    "ac_airflow_mode": "face",
    "ac_auto": False,
    "ac_sync": False,
    "window_status": {
        "front_left": "closed",
        "front_right": "closed",
        "rear_left": "closed",
        "rear_right": "closed",
    },
    "window_lock_status": False,
    "music_status": True,
    "music_volume": 55,
    "reading_light_status": {"front": "off", "rear": "off"},
    "seat_status": {"driver": "normal", "passenger": "normal"},
    "_safe_stop": False,
}

# Start near Cairo (30.0444°N, 31.2357°E) and drift slightly each tick
_BASE_LAT = 30.0444
_BASE_LNG = 31.2357


def _gps_tick(tick: int) -> tuple[float, float]:
    """Tiny circle route so the agent gets changing coords."""
    angle = (tick * 5) % 360
    rad = math.radians(angle)
    return (
        round(_BASE_LAT + 0.001 * math.cos(rad), 6),
        round(_BASE_LNG + 0.001 * math.sin(rad), 6),
    )


def _apply_action(action: str, params: dict) -> list[str]:
    """
    Apply an action to the mutable STATE and return human-readable changes.

    Returns a list of strings describing what changed (empty = nothing changed).
    """
    changes: list[str] = []
    p = params or {}

    try:
        if action == "ac_on":
            STATE["ac_status"] = "on"
            changes.append("AC turned ON")
        elif action == "ac_off":
            STATE["ac_status"] = "off"
            changes.append("AC turned OFF")
        elif action == "set_temperature":
            temp = float(p.get("temperature", 22))
            STATE["ac_temperature"] = temp
            changes.append(f"AC temperature set to {temp}°C")
        elif action == "set_fan_speed":
            speed = int(p.get("speed", 1))
            STATE["ac_fan_speed"] = speed
            changes.append(f"Fan speed set to {speed}")
        elif action == "set_airflow_mode":
            mode = str(p.get("mode", "face"))
            STATE["ac_airflow_mode"] = mode
            changes.append(f"Airflow mode set to {mode}")
        elif action == "climate_auto":
            STATE["ac_auto"] = bool(p.get("enabled", True))
            changes.append(f"Climate auto {'ON' if STATE['ac_auto'] else 'OFF'}")
        elif action == "climate_sync":
            STATE["ac_sync"] = bool(p.get("enabled", True))
            changes.append(f"Climate sync {'ON' if STATE['ac_sync'] else 'OFF'}")
        elif action == "window_open":
            target = str(p.get("window", "all"))
            STATE["window_status"] = (
                dict.fromkeys(STATE["window_status"], "open")
                if target == "all"
                else {**STATE["window_status"], target: "open"}
            )
            changes.append(f"Window opened: {target}")
        elif action == "window_close":
            target = str(p.get("window", "all"))
            STATE["window_status"] = (
                dict.fromkeys(STATE["window_status"], "closed")
                if target == "all"
                else {**STATE["window_status"], target: "closed"}
            )
            changes.append(f"Window closed: {target}")
        elif action == "window_lock":
            STATE["window_lock_status"] = True
            changes.append("Windows LOCKED")
        elif action == "window_unlock":
            STATE["window_lock_status"] = False
            changes.append("Windows UNLOCKED")
        elif action == "music_play":
            STATE["music_status"] = True
            changes.append("Music playing")
        elif action == "music_pause":
            STATE["music_status"] = False
            changes.append("Music paused")
        elif action == "set_volume":
            change = int(p.get("change", 0))
            STATE["music_volume"] = max(0, min(100, STATE["music_volume"] + change))
            changes.append(f"Volume adjusted by {change} to {STATE['music_volume']}/100")
        elif action == "next_track":
            changes.append("Track skipped forward (simulated)")
        elif action == "previous_track":
            changes.append("Track skipped backward (simulated)")
        elif action == "reading_light_on":
            target = str(p.get("light", "both"))
            if target == "both":
                STATE["reading_light_status"] = {"front": "on", "rear": "on"}
            else:
                STATE["reading_light_status"][target] = "on"
            changes.append(f"Reading light ON: {target}")
        elif action == "reading_light_off":
            target = str(p.get("light", "both"))
            if target == "both":
                STATE["reading_light_status"] = {"front": "off", "rear": "off"}
            else:
                STATE["reading_light_status"][target] = "off"
            changes.append(f"Reading light OFF: {target}")
        elif action == "seat_position":
            seat = str(p.get("seat", "driver"))
            pct = int(p.get("percentage", 50))
            STATE["seat_status"][seat] = f"position_{pct}"
            changes.append(f"{seat} seat position set to {pct}%")
        elif action == "seat_recline":
            seat = str(p.get("seat", "driver"))
            pct = int(p.get("percentage", 0))
            STATE["seat_status"][seat] = f"recline_{pct}"
            changes.append(f"{seat} seat recline set to {pct}%")
        elif action == "seat_height":
            seat = str(p.get("seat", "driver"))
            pct = int(p.get("percentage", 50))
            STATE["seat_status"][seat] = f"height_{pct}"
            changes.append(f"{seat} seat height set to {pct}%")
        elif action == "safe_stop":
            changes.append("SAFE STOP initiated — decelerating gradually")
        elif action in ("change_destination", "cancel_destination"):
            changes.append(f"Navigation action '{action}' forwarded to vehicle")
        else:
            changes.append(f"Unknown action '{action}' (no simulation handler)")
    except (ValueError, KeyError, TypeError) as e:
        changes.append(f"Error applying '{action}': {e}")

    return changes


async def _publish_state(client: aiomqtt.Client, lat: float, lng: float, tick: int) -> None:
    """Publish current STATE with fresh GPS and derived fields."""
    snapshot = {
        **STATE,
        "timestamp": int(time.time()),
        "lat": lat,
        "long": lng,
        "battery_level": max(10, STATE["battery_level"]),
    }
    topic = f"vehicle/{VEHICLE_ID}/state"
    await client.publish(topic, json.dumps(snapshot))
    logger.info(
        "📤 [PUBLISH] → %s  (lat=%.6f lon=%.6f spd=%.1f km/h bat=%d%%)",
        topic,
        lat,
        lng,
        snapshot["speed"],
        snapshot["battery_level"],
    )


async def _publish_location(client: aiomqtt.Client, lat: float, lng: float) -> None:
    """Publish a standalone GPS update."""
    payload = {
        "vin_number": VIN_NUMBER,
        "lat": lat,
        "long": lng,
        "timestamp": int(time.time()),
    }
    topic = f"vehicle/{VEHICLE_ID}/location"
    await client.publish(topic, json.dumps(payload))
    logger.info("📤 [PUBLISH] → %s  (lat=%.6f lon=%.6f)", topic, lat, lng)


async def _gradual_stop(client: aiomqtt.Client, lat: float, lng: float, tick: int) -> None:
    """Decelerate the vehicle gradually over ~5 seconds, publishing each step."""
    STATE["_safe_stop"] = True
    current = STATE.get("speed", 30.0)
    steps = 10
    for i in range(1, steps + 1):
        STATE["speed"] = round(current * (1 - i / steps), 1)
        await _publish_state(client, lat, lng, tick)
        await asyncio.sleep(0.5)
    STATE["speed"] = 0.0
    STATE["_safe_stop"] = False
    await _publish_state(client, lat, lng, tick)
    logger.info("   ✅ Vehicle fully stopped")


# ── Step 1: Login ──────────────────────────────────────────────────────────────
def do_login() -> bool:
    url = f"{BACKEND_URL}/login"
    payload = {
        "vehicle_id": VEHICLE_ID,
        "vin_number": VIN_NUMBER,
        "jwt": JWT_TOKEN,
    }
    logger.info("Calling POST %s ...", url)
    try:
        r = requests.post(url, json=payload, timeout=8)
        if r.ok:
            logger.info("✅ Login OK: %s", r.json())
            return True
        logger.error("❌ Login failed %s: %s", r.status_code, r.text)
        return False
    except requests.exceptions.ConnectionError:
        logger.error("❌ Cannot reach backend at %s — is FastAPI running?", BACKEND_URL)
        return False


# ── Step 2: MQTT publisher + subscriber ───────────────────────────────────────
async def run_simulator():
    tls_ctx = ssl.create_default_context() if MQTT_SSL_ON else None
    stop_event = asyncio.Event()

    def _signal_handler():
        logger.info("Shutdown signal received, stopping simulator...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, _signal_handler)

    logger.info("Connecting to MQTT broker %s:%s (SSL=%s)", MQTT_HOST, MQTT_PORT, MQTT_SSL_ON)

    async with aiomqtt.Client(
        hostname=MQTT_HOST,
        port=MQTT_PORT,
        username=MQTT_USER,
        password=MQTT_PASS,
        tls_context=tls_ctx,
    ) as client:
        action_topic = f"vehicle/{VEHICLE_ID}/action"
        nav_topic = f"vehicle/{VEHICLE_ID}/navigation/#"
        await client.subscribe(action_topic)
        await client.subscribe(nav_topic)
        logger.info("✅ Connected. Subscribed to %s and %s", action_topic, nav_topic)
        logger.info(
            "Publishing state every %ds, GPS every %ds. Press Ctrl+C to stop.",
            STATE_INTERVAL_S,
            LOCATION_INTERVAL_S,
        )

        tick = 0
        last_state_t = 0.0
        last_loc_t = 0.0

        async def publish_loop():
            nonlocal tick, last_state_t, last_loc_t
            while not stop_event.is_set():
                now = time.monotonic()

                if now - last_state_t >= STATE_INTERVAL_S:
                    lat, lng = _gps_tick(tick)
                    if not STATE.get("_safe_stop"):
                        STATE["speed"] = round(30 + 10 * math.sin(math.radians(tick * 7)), 1)
                    await _publish_state(client, lat, lng, tick)
                    last_state_t = now
                    tick += 1

                if now - last_loc_t >= LOCATION_INTERVAL_S:
                    lat, lng = _gps_tick(tick)
                    await _publish_location(client, lat, lng)
                    last_loc_t = now

                await asyncio.sleep(0.5)

        async def listen_loop():
            nonlocal tick, last_state_t, last_loc_t
            async for message in client.messages:
                topic = message.topic.value
                raw = message.payload.decode(errors="replace")
                logger.info("📥 [RECEIVED] ← %s  %s", topic, raw[:200])

                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                if "/action" in topic:
                    action = data.get("action", "")
                    params = data.get("parameters", {})
                    changes = _apply_action(action, params)
                    for c in changes:
                        logger.info("   ⚙️  %s", c)

                    lat, lng = _gps_tick(tick)

                    if action == "safe_stop":
                        task = asyncio.create_task(_gradual_stop(client, lat, lng, tick))
                        _background_tasks.add(task)
                        task.add_done_callback(_background_tasks.discard)
                    else:
                        await _publish_state(client, lat, lng, tick)

                elif "/navigation/change" in topic:
                    dest = data.get("destination", "unknown")
                    nav_lat = data.get("latitude")
                    nav_lng = data.get("longitude")
                    STATE["destination_name"] = dest
                    STATE["remaining_distance"] = 999.0
                    STATE["remaining_time"] = 999.0
                    logger.info(
                        "   🗺️  Navigation changed → %s  (%.4f, %.4f)", dest, nav_lat, nav_lng
                    )
                    await _publish_state(client, nav_lat or _BASE_LAT, nav_lng or _BASE_LNG, tick)

                elif "/navigation/cancel" in topic:
                    STATE.pop("destination_name", None)
                    logger.info("   🗺️  Navigation cancelled")
                    lat, lng = _gps_tick(tick)
                    await _publish_state(client, lat, lng, tick)

        tg = asyncio.TaskGroup()
        try:
            async with tg:
                t1 = tg.create_task(publish_loop())
                t2 = tg.create_task(listen_loop())
                await stop_event.wait()
                t1.cancel()
                t2.cancel()
        except asyncio.CancelledError:
            pass

        logger.info("Simulator disconnected from broker.")


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  Yaquod Fake Vehicle Simulator")
    print("=" * 60)
    print(f"  Vehicle ID : {VEHICLE_ID}")
    print(f"  VIN        : {VIN_NUMBER}")
    print(f"  Backend    : {BACKEND_URL}")
    print(f"  MQTT       : {MQTT_HOST}:{MQTT_PORT}")
    print("=" * 60)

    if not do_login():
        print("\n⚠️  Login failed. Fix the error above then re-run.")
        print("   (The simulator needs FastAPI running to seed Redis.)")
        sys.exit(1)

    print()
    try:
        asyncio.run(run_simulator())
    except KeyboardInterrupt:
        print("\n🛑 Simulator stopped.")

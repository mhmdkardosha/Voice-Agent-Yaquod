import asyncio
import sys

# Add this to fix the Windows aiomqtt NotImplementedError
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import json
import logging
import os
import re
from collections.abc import AsyncGenerator, AsyncIterable

import httpx2
from dotenv import load_dotenv

from config.redis_db import get_redis
from services.mqtt_service import central_mqtt

load_dotenv(override=True)

from livekit import agents
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    APIConnectOptions,
    RunContext,
    function_tool,
    inference,
)
from livekit.agents.voice import room_io
from livekit.agents.voice.agent_session import SessionConnectOptions
from livekit.plugins import google

from config.constants import ALLOWED_ACTIONS
from llm.prompts import STARTER_GREETING, SYSTEM_PROMPT
from utils.get_place_coordinates import get_place_coordinates
from utils.google_places import search_places_text
from utils.validator import validate_vehicle_action
from utils.web_search import search_web as search_web_util

_TASHKEEL_RE = re.compile(r"[\u064B-\u065F\u0670]")


def _strip_tashkeel(text: str) -> str:
    return _TASHKEEL_RE.sub("", text)


logger = logging.getLogger("yaquod-agent")

LANGUAGE_CONFIGS = {
    "ar": {"stt_lang": "ar-XA", "tts_lang": "ar-XA", "voice_name": "ar-XA-Chirp3-HD-Aoede"},
    "en": {"stt_lang": "en-US", "tts_lang": "en-US", "voice_name": "en-US-Chirp3-HD-Aoede"},
}

DEFAULT_LANG = "ar"

# Default test location (Cairo, Egypt) - Replace with MQTT subscription data in production
_DEFAULT_LOCATION = (30.0444, 31.2357)

_WAIT_MESSAGES: dict[str, dict[str, str]] = {
    "ar": {
        "search_web": "جاري البحث على الإنترنت. يُرجى الانتظار قليلًا.",
        "change_destination": "حاضر، جارٍ تغيير الوجهة. يُرجى الانتظار قليلًا.",
    },
    "en": {
        "search_web": "Searching the web. Please wait a moment.",
        "change_destination": "Okay, I'm changing your destination. Please wait a moment.",
    },
}


class Assistant(Agent):
    def __init__(self, vehicle_id: str) -> None:
        super().__init__(instructions=SYSTEM_PROMPT)
        self._current_lang = DEFAULT_LANG
        self.vehicle_id = vehicle_id

    async def transcription_node(
        self, text: AsyncIterable[str], model_settings: object
    ) -> AsyncGenerator[str, None]:
        async for chunk in text:
            if isinstance(chunk, str):
                yield _strip_tashkeel(chunk)
            else:
                yield chunk

    @function_tool
    async def switch_language(self, context: RunContext, language: str) -> str:
        config = LANGUAGE_CONFIGS.get(language)

        if not config:
            return f"Unsupported language '{language}'. Supported: ar, en."

        if language == self._current_lang:
            return f"Already using {language}"

        session = context.session
        logger.info(f"Switching language: {self._current_lang} -> {language}")

        session.tts.update_options(
            voice_name=config["voice_name"],
            language=config["tts_lang"],
        )

        self._current_lang = language

        return f"Switched to {language}"

    @function_tool
    async def vehicle_action(
        self,
        context: RunContext,
        action: str,
        parameters: dict | None = None,
    ) -> str:
        """Executes a vehicle action directly via MQTT."""
        parameters = parameters or {}

        # Safety whitelist check
        if action not in ALLOWED_ACTIONS:
            return "This action is not allowed."

        # Validate parameters
        error = validate_vehicle_action(action, parameters)

        if error:
            return error

        vehicle_id = self.vehicle_id
        payload = {"vehicle_id": vehicle_id, "action": action, "parameters": parameters}
        logger.info("Publishing action '%s' for car: %s", action, vehicle_id)

        try:
            success = await central_mqtt.publish_action(vehicle_id, "action", payload)
            if success:
                return f"Executed {action}"
            else:
                return "Vehicle system unavailable"
        except Exception as e:
            logger.error(f"MQTT publish error: {e}")
            return "Vehicle system unavailable"

    @function_tool
    async def get_weather_and_time(
        self,
        context: RunContext,
        request_type: str = "both",
    ) -> str:
        """
        Fetches vehicle environment metrics (weather, time, or both) based on current GPS coordinates.

        Args:
            request_type: Determined by the user's intent. Supported values:
                          "time" (if user strictly asks for time/date),
                          "weather" (if user asks for weather),
                          "both" (default, or if user requests both).
        """
        import datetime

        logger.info(f"Initiating environment fetch. Request type: {request_type}")

        # 1. Fetch vehicle coordinates using the internal async method
        location = await self._get_vehicle_location()
        if location is None:
            return "Vehicle tracking system unavailable or invalid coordinates."

        lat, lon = location

        # 2. Verify Weather API Key configuration
        weather_api_key = os.environ.get("WEATHER_API_KEY")
        if not weather_api_key:
            return "WEATHER_API_KEY is not configured."

        weather_url = "https://api.weatherapi.com/v1/current.json"
        weather_params = {"key": weather_api_key, "q": f"{lat},{lon}", "lang": "en"}

        try:
            async with httpx2.AsyncClient() as client:
                weather_response = await client.get(weather_url, params=weather_params, timeout=5)

                if weather_response.is_success:
                    weather_data = weather_response.json()

                    # Extract dynamic local time data
                    localtime_str = weather_data["location"][
                        "localtime"
                    ]  # e.g., "2026-07-08 21:00"
                    dt = datetime.datetime.strptime(localtime_str, "%Y-%m-%d %H:%M")

                    day_name = dt.strftime("%A")
                    formatted_date = dt.strftime("%B %d, %Y")
                    time_str = dt.strftime("%I:%M %p")

                    time_output = f"The local time in the vehicle is {time_str} on {day_name}, {formatted_date}."

                    # Branch response logic based on the LLM-selected request_type
                    if request_type == "time":
                        return time_output

                    # Extract weather properties
                    city = weather_data["location"]["name"]
                    temp = weather_data["current"]["temp_c"]
                    condition = weather_data["current"]["condition"]["text"]

                    weather_output = (
                        f"The weather in {city} is {condition} with a temperature of {temp}°C."
                    )

                    return f"{weather_output} {time_output}"
                else:
                    logger.error(f"Weather API error: {weather_response.status_code}")
                    return "Environment service error."

        except Exception as e:
            logger.error(f"Weather/Time API exception: {e}")
            return "Environment synchronization system unavailable."

    async def _get_vehicle_location(self) -> tuple[float, float] | None:
        """Fetch real-time location from Redis, or return default if unavailable."""
        redis_key = f"vehicle:status:{self.vehicle_id}"

        try:
            r_client = get_redis()

            data_str = await r_client.get(redis_key)
            if data_str:
                data = json.loads(data_str)
                lat = data.get("lat")
                lon = data.get("long")

                if lat is not None and lon is not None:
                    logger.info(f"Using real-time location for {self.vehicle_id}")
                    return (float(lat), float(lon))

        except Exception as e:
            logger.error(f"Error fetching location from Redis: {e}")

        logger.info(f"Using default location for {self.vehicle_id}")
        return _DEFAULT_LOCATION

    @function_tool
    async def search_nearby_places(
        self,
        context: RunContext,
        query: str,
        radius_meters: int = 1500,
    ) -> str:
        """Search for nearby places using Google Maps Places API."""
        location = await self._get_vehicle_location()
        if not location:
            return "Unable to get vehicle location for search."

        places = await search_places_text(
            query, location_bias=location, radius_meters=radius_meters
        )

        if places is None:
            return "Places search unavailable."
        if not places:
            return f"No results found for '{query}' nearby."

        results = []
        for place in places[:5]:
            name = place.get("displayName", {}).get("text", "Unknown")
            address = place.get("formattedAddress", "No address")
            rating = place.get("rating", "N/A")
            open_now = place.get("currentOpeningHours", {}).get("openNow", None)
            open_status = "Open" if open_now else "Closed" if open_now is not None else ""

            result = f"{name}, {address}"
            if rating != "N/A":
                result += f", Rating: {rating}"
            if open_status:
                result += f", {open_status}"
            results.append(result)

        return "Found: " + "; ".join(results)

    @function_tool
    async def search_web(
        self,
        context: RunContext,
        query: str,
    ) -> str:
        """Search the web for up-to-date information using Brave Search."""

        search_lang = "ar" if self._current_lang == "ar" else "en"

        context.session.say(
            _WAIT_MESSAGES[search_lang]["search_web"],
            add_to_chat_ctx=True,
        )

        results = await search_web_util(query, search_lang=search_lang)

        if results is None:
            return "Web search is not configured or unavailable."
        if not results:
            return f"No search results found for '{query}'."

        lines = []
        for i, r in enumerate(results, 1):
            snippet = r.get("description", "").strip()
            title = r.get("title", "").strip()
            if title and snippet:
                lines.append(f"{i}. {title} — {snippet}")
            elif title:
                lines.append(f"{i}. {title}")
            else:
                lines.append(f"{i}. {snippet}")

        return "Search results: " + " | ".join(lines)

    @function_tool
    async def change_destination(
        self,
        context: RunContext,
        destination: str,
    ) -> str:
        """Start navigation to a destination via direct MQTT publish."""
        lang = "ar" if self._current_lang == "ar" else "en"
        context.session.say(
            _WAIT_MESSAGES[lang]["change_destination"],
            add_to_chat_ctx=True,
        )

        try:
            # Step 1: Search Google Places
            place = await get_place_coordinates(destination)

            if place is None:
                return "I couldn't find the destination you specified. Please check the name or address and try again."

            vehicle_id = self.vehicle_id
            payload = {
                "vehicle_id": vehicle_id,
                "destination": place["name"],
                "latitude": place["lat"],
                "longitude": place["lng"],
            }

            logger.info(
                "Publishing Navigation Change to %s:\n%s", "navigation/change", json.dumps(payload)
            )

            success = await central_mqtt.publish_action(vehicle_id, "navigation/change", payload)

            if success:
                return f"Navigation started to {place['name']}."
            else:
                return "Navigation system unavailable."

        except Exception as e:
            logger.exception(e)
            return "Navigation system unavailable."

    @function_tool
    async def cancel_destination(
        self,
        context: RunContext,
    ) -> str:
        """Cancel the current navigation via direct MQTT publish."""
        vehicle_id = self.vehicle_id
        payload = {"vehicle_id": vehicle_id}

        try:
            logger.info("Publishing Cancel Navigation to %s", "navigation/cancel")
            success = await central_mqtt.publish_action(vehicle_id, "navigation/cancel", payload)

            if success:
                return "Navigation cancelled."
            else:
                return "Navigation system unavailable."
        except Exception as e:
            logger.error(f"Navigation cancel error: {e}")
            return "Navigation system unavailable."

    async def _get_raw_vehicle_dict(self) -> dict:
        """Fetch and parse raw vehicle status from Redis."""
        vehicle_id = self.vehicle_id
        r_client = getattr(self, "redis_client", None)
        if not r_client:
            from config.redis_db import get_redis

            r_client = get_redis()

        redis_key = f"vehicle:status:{vehicle_id}"
        raw_data_str = r_client.get(redis_key)

        if not raw_data_str:
            return {}
        try:
            return json.loads(raw_data_str)
        except Exception as e:
            logger.error(f"Error decoding Redis JSON: {e}")
            return {}

    @function_tool
    async def get_vehicle_core_telemetry(
        self,
        context: RunContext,
    ) -> str:
        """Get basic specifications, identity, speed, and battery/fuel levels."""
        vehicle_id = self.vehicle_id
        data = await self._get_raw_vehicle_dict()
        if not data:
            return f"No core telemetry found for vehicle {vehicle_id}."

        model = data.get("vehicle_model") or "Unknown"
        color = data.get("vehicle_color") or "Unknown"
        plate = data.get("plate_num") or "N/A"

        summary = f"Vehicle: {color} {model} (Plate: {plate}). "
        if data.get("battery_level") is not None:
            summary += f"Battery Level: {data['battery_level']}%. "
        if data.get("number_of_seats") is not None:
            summary += f"Available Seats: {data['number_of_seats']}. "

        return summary.strip()

    @function_tool
    async def get_vehicle_trip_profile(
        self,
        context: RunContext,
    ) -> str:
        vehicle_id = self.vehicle_id
        """Get active trip details, route, destination, remaining distance, and ETA."""
        data = await self._get_raw_vehicle_dict()
        if not data:
            return f"No active trip data found for vehicle {vehicle_id}."

        summary = ""
        if data.get("pickup_point_name") or data.get("destination_name"):
            summary += (
                f"Trip: From '{data.get('pickup_point_name', 'N/A')}' "
                f"to '{data.get('destination_name', 'N/A')}'. "
            )
        if data.get("expected_trip_duration") is not None:
            summary += f"Total Duration: {data['expected_trip_duration']} mins. "
        if data.get("remaining_distance") is not None:
            summary += f"Remaining Distance: {data['remaining_distance']} km. "
        if data.get("remaining_time") is not None:
            summary += f"Time to Arrival: {data['remaining_time']} minutes. "
        if data.get("speed") is not None:
            summary += f"Current Speed: {data['speed']} km/h. "

        return summary.strip()

    @function_tool
    async def get_cabin_systems_status(
        self,
        context: RunContext,
        system_type: str = "all",
    ) -> str:
        """Get cabin status. Filter by 'ac', 'windows', 'multimedia', 'lights', 'seats', or 'all'."""
        vehicle_id = self.vehicle_id
        data = await self._get_raw_vehicle_dict()
        if not data:
            return f"No cabin system data found for vehicle {vehicle_id}."

        system_type = system_type.lower().strip()
        status_parts = []

        if system_type in ["ac", "all"]:
            ac_details = []
            if data.get("ac_status") is not None:
                ac_details.append(f"Status: {data['ac_status']}")
            if data.get("ac_temperature") is not None:
                ac_details.append(f"Temp: {data['ac_temperature']}°C")
            if data.get("ac_fan_speed") is not None:
                ac_details.append(f"Fan Speed: {data['ac_fan_speed']}")
            if data.get("ac_airflow_mode") is not None:
                ac_details.append(f"Airflow: {data['ac_airflow_mode']}")
            if data.get("ac_auto") is not None:
                ac_details.append(f"Auto: {data['ac_auto']}")
            if data.get("ac_sync") is not None:
                ac_details.append(f"Sync: {data['ac_sync']}")
            if ac_details:
                status_parts.append(f"AC: [{', '.join(ac_details)}]")

        if system_type in ["windows", "all"]:
            win_details = []
            if data.get("window_status") is not None:
                win_details.append(f"Status: {data['window_status']}")
            if data.get("window_lock_status") is not None:
                win_details.append(f"Locked: {data['window_lock_status']}")
            if win_details:
                status_parts.append(f"Windows: [{', '.join(win_details)}]")

        if system_type in ["multimedia", "music", "all"]:
            music_details = []
            if data.get("music_status") is not None:
                music_details.append(f"Playing: {data['music_status']}")
            if data.get("music_volume") is not None:
                music_details.append(f"Volume: {data['music_volume']}/100")
            if music_details:
                status_parts.append(f"Music: [{', '.join(music_details)}]")

        if system_type in ["lights", "all"] and data.get("reading_light_status") is not None:
            status_parts.append(f"Reading Lights: {data['reading_light_status']}")

        if system_type in ["seats", "all"] and data.get("seat_status") is not None:
            status_parts.append(f"Seats: {data['seat_status']}")

        if not status_parts:
            return f"No metrics found for cabin system type: '{system_type}'."

        return f"Vehicle {vehicle_id} Cabin Status -> " + " | ".join(status_parts)


server = AgentServer()


@server.rtc_session(agent_name="yaquod")
async def my_agent(ctx: agents.JobContext):
    default_config = LANGUAGE_CONFIGS[DEFAULT_LANG]
    r_client = get_redis()
    import json

    try:
        meta = json.loads(ctx.job.metadata)
        vehicle_id = meta.get("car_id", "vehicle_001")
    except (json.JSONDecodeError, TypeError):
        vehicle_id = "vehicle_001"
        logger.warning("Failed to parse metadata; falling back to vehicle_001")

    central_mqtt.start()

    session = AgentSession(
        stt=google.STT(
            languages=[default_config["stt_lang"], LANGUAGE_CONFIGS["en"]["stt_lang"]],
            detect_language=True,
            model="chirp_3",
            location="eu",
        ),
        llm=google.LLM(
            model="gemini-3.5-flash",
            vertexai=True,
            location="europe-west2",
            thinking_config={"thinking_level": "low"},
        ),
        tts=google.TTS(
            language=default_config["tts_lang"],
            voice_name=default_config["voice_name"],
            location="eu",
        ),
        turn_detection=inference.TurnDetector(),
        conn_options=SessionConnectOptions(
            tts_conn_options=APIConnectOptions(timeout=60.0),
        ),
    )

    try:
        assistant = Assistant(vehicle_id=vehicle_id)
        await session.start(
            room=ctx.room,
            agent=assistant,
            room_options=room_io.RoomOptions(close_on_disconnect=False),
        )
        await session.generate_reply(instructions=STARTER_GREETING)

        disconnected = asyncio.Event()
        ctx.room.on("disconnected", disconnected.set)
        await disconnected.wait()

    finally:
        logger.info(f"[LiveKit Session] Ending for car: {vehicle_id}. Cleaning up...")
        r_client.delete(f"vehicle:status:{vehicle_id}")
        logger.info(f"[LiveKit CleanUp] Cleared live state for {vehicle_id}")


if __name__ == "__main__":
    agents.cli.run_app(server)

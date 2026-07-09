import asyncio
import sys

# Add this to fix the Windows aiomqtt NotImplementedError
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import json
import logging
import os
import re
import ssl
from collections.abc import AsyncGenerator, AsyncIterable
import aiomqtt
import json
import httpx2
from dotenv import load_dotenv
from config.redis_db import get_redis
from routes.vehicle_mqtt import listen_to_mqtt_state
import ssl
from collections.abc import AsyncGenerator, AsyncIterable


load_dotenv(override=True)

from livekit import agents
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    RunContext,
    TurnHandlingOptions,
    function_tool,
    inference,
)
from livekit.plugins import azure

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

_ARABIC_VOICE = (
    "fc923f89-1de5-4ddf-b93c-6da2ba63428a"  # Katie (Cartesia default) — multilingual, works with ar
)
_ENGLISH_VOICE = "273f9ef7-9fc2-4def-88bb-ab108c6249ca"  # Jacqueline — en-US female

LANGUAGE_CONFIGS = {
    "ar": {"stt_lang": "ar", "tts_lang": "ar", "voice_id": _ARABIC_VOICE},
    "en": {"stt_lang": "en", "tts_lang": "en", "voice_id": _ENGLISH_VOICE},
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
    def __init__(self, mqtt_client: aiomqtt.Client) -> None:
        super().__init__(instructions=SYSTEM_PROMPT)
        self._current_lang = DEFAULT_LANG
        self.mqtt_client = mqtt_client

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
            voice=config["voice_id"],
            language=config["tts_lang"],
        )

        pool = getattr(session.tts, "_pool", None)
        if pool is not None and hasattr(pool, "invalidate"):
            pool.invalidate()

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

        vehicle_id = "vehicle_001"
        payload = {"vehicle_id": vehicle_id, "action": action, "parameters": parameters}
        topic = f"vehicle/{vehicle_id}/action"

        logger.info("Publishing Vehicle Action to %s:\n%s", topic, json.dumps(payload, indent=2))

        try:
            await self.mqtt_client.publish(topic, json.dumps(payload))
            return f"Executed {action}"
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
                    localtime_str = weather_data["location"]["localtime"]  # e.g., "2026-07-08 21:00"
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
                    
                    weather_output = f"The weather in {city} is {condition} with a temperature of {temp}°C."

                    return f"{weather_output} {time_output}"
                else:
                    logger.error(f"Weather API error: {weather_response.status_code}")
                    return "Environment service error."

        except Exception as e:
            logger.error(f"Weather/Time API exception: {e}")
            return "Environment synchronization system unavailable."

    async def _get_vehicle_location(self) -> tuple[float, float] | None:
        """
        Returns the vehicle location.
        Note: Currently uses a static default. To make this dynamic,
        you can subscribe to your MQTT location topic in a background task.
        """
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

            vehicle_id = "vehicle_001"
            payload = {
                "vehicle_id": vehicle_id,
                "destination": place["name"],
                "latitude": place["lat"],
                "longitude": place["lng"],
            }
            topic = f"vehicle/{vehicle_id}/navigation/change"

            logger.info("Publishing Navigation Change to %s:\n%s", topic, json.dumps(payload))

            # Step 2: Publish to MQTT
            await self.mqtt_client.publish(topic, json.dumps(payload))
            return f"Navigation started to {place['name']}."

        except Exception as e:
            logger.exception(e)
            return "Navigation system unavailable."

    @function_tool
    async def cancel_destination(
        self,
        context: RunContext,
    ) -> str:
        """Cancel the current navigation via direct MQTT publish."""
        vehicle_id = "vehicle_001"
        payload = {"vehicle_id": vehicle_id}
        topic = f"vehicle/{vehicle_id}/navigation/cancel"

        try:
            logger.info("Publishing Cancel Navigation to %s", topic)
            await self.mqtt_client.publish(topic, json.dumps(payload))
            return "Navigation cancelled."
        except Exception as e:
            logger.error(f"Navigation cancel error: {e}")
            return "Navigation system unavailable."

    async def _get_raw_vehicle_dict(self, vehicle_id: str) -> dict:
        """Fetch and parse raw vehicle status from Redis."""
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
        vehicle_id: str = "vehicle_001",
    ) -> str:
        """Get basic specifications, identity, speed, and battery/fuel levels."""
        data = await self._get_raw_vehicle_dict(vehicle_id)
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
        vehicle_id: str = "vehicle_001",
    ) -> str:
        """Get active trip details, route, destination, remaining distance, and ETA."""
        data = await self._get_raw_vehicle_dict(vehicle_id)
        if not data:
            return f"No active trip data found for vehicle {vehicle_id}."
            
        if not data.get("pickup_point_name") and not data.get("destination_name"):
            return "The vehicle is currently not on an active scheduled trip."
            
        summary = f"Trip: From '{data.get('pickup_point_name', 'N/A')}' to '{data.get('destination_name', 'N/A')}'. "
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
        vehicle_id: str = "vehicle_001",
    ) -> str:
        """Get cabin status. Filter by 'ac', 'windows', 'multimedia', 'lights', 'seats', or 'all'."""
        data = await self._get_raw_vehicle_dict(vehicle_id)
        if not data:
            return f"No cabin system data found for vehicle {vehicle_id}."
            
        system_type = system_type.lower().strip()
        status_parts = []
        
        if system_type in ["ac", "all"]:
            ac_details = []
            if data.get("ac_status") is not None: ac_details.append(f"Status: {data['ac_status']}")
            if data.get("ac_temperature") is not None: ac_details.append(f"Temp: {data['ac_temperature']}°C")
            if data.get("ac_fan_speed") is not None: ac_details.append(f"Fan Speed: {data['ac_fan_speed']}")
            if data.get("ac_airflow_mode") is not None: ac_details.append(f"Airflow: {data['ac_airflow_mode']}")
            if data.get("ac_auto") is not None: ac_details.append(f"Auto: {data['ac_auto']}")
            if data.get("ac_sync") is not None: ac_details.append(f"Sync: {data['ac_sync']}")
            if ac_details:
                status_parts.append(f"AC: [{', '.join(ac_details)}]")
                
        if system_type in ["windows", "all"]:
            win_details = []
            if data.get("window_status") is not None: win_details.append(f"Status: {data['window_status']}")
            if data.get("window_lock_status") is not None: win_details.append(f"Locked: {data['window_lock_status']}")
            if win_details:
                status_parts.append(f"Windows: [{', '.join(win_details)}]")
                
        if system_type in ["multimedia", "music", "all"]:
            music_details = []
            if data.get("music_status") is not None: music_details.append(f"Playing: {data['music_status']}")
            if data.get("music_volume") is not None: music_details.append(f"Volume: {data['music_volume']}/100")
            if music_details:
                status_parts.append(f"Music: [{', '.join(music_details)}]")

        if system_type in ["lights", "all"]:
            if data.get("reading_light_status") is not None:
                status_parts.append(f"Reading Lights: {data['reading_light_status']}")

        if system_type in ["seats", "all"]:
            if data.get("seat_status") is not None:
                status_parts.append(f"Seats: {data['seat_status']}")

        if not status_parts:
            return f"No metrics found for cabin system type: '{system_type}'."
            
        return f"Vehicle {vehicle_id} Cabin Status -> " + " | ".join(status_parts)


server = AgentServer()


@server.rtc_session(agent_name="yaquod")
async def my_agent(ctx: agents.JobContext):
    default_config = LANGUAGE_CONFIGS[DEFAULT_LANG]
    mqtt_host = os.environ.get("MQTT_HOST", "localhost")
    mqtt_port = int(os.environ.get("MQTT_PORT", 1883))
    mqtt_username = os.environ.get("MQTT_USERNAME", "")
    mqtt_password = os.environ.get("MQTT_PASSWORD", "")
    
    use_ssl = os.environ.get("MQTT_SSL", "false").lower() == "true"
    tls_context = ssl.create_default_context() if use_ssl else None

    logger.info(f"Connecting to MQTT Broker at {mqtt_host}:{mqtt_port}...")
    
    r_client = get_redis()
    vehicle_id = "vehicle_001"

    try:
        async with aiomqtt.Client(
            hostname=mqtt_host, port=mqtt_port,
            username=mqtt_username if mqtt_username else None,
            password=mqtt_password if mqtt_password else None,
            tls_context=tls_context,
        ) as mqtt_client:
            
            # Start background MQTT listener
            mqtt_listener_task = asyncio.create_task(listen_to_mqtt_state(mqtt_client))

            session = AgentSession(
                stt=azure.STT(language=["ar-EG", "en-US"]),
                llm=inference.LLM(model="google/gemini-3.1-flash-lite"),
                tts=inference.TTS(model="cartesia/sonic-3.5", voice=default_config["voice_id"], language=default_config["tts_lang"]),
                turn_handling=TurnHandlingOptions(turn_detection="vad"),
            )

            assistant = Assistant(mqtt_client=mqtt_client)
            await session.start(room=ctx.room, agent=assistant)
            await session.generate_reply(instructions=STARTER_GREETING)

            # Wait for room disconnect
            disconnect_event = asyncio.Event()
            ctx.room.on("disconnected", disconnect_event.set)
            await disconnect_event.wait()
            
            # Cleanup MQTT task
            mqtt_listener_task.cancel()
            await asyncio.gather(mqtt_listener_task, return_exceptions=True)
            
    finally:
        # Delete vehicle data from Redis when session ends
        try:
            r_client.delete(f"vehicle:status:{vehicle_id}")
            logger.info(f"Redis data deleted successfully for vehicle: {vehicle_id}")
        except Exception as e:
            logger.error(f"Error deleting Redis data: {e}")



if __name__ == "__main__":
    agents.cli.run_app(server)

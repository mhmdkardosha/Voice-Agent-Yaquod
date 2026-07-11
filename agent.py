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
import httpx2
from dotenv import load_dotenv

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
    async def get_weather(
        self,
        context: RunContext,
    ) -> str:
        """
        Fetches the current weather by locating the vehicle first via Vehicle API,
        then calling WeatherAPI. Returns a localized message.
        """
        api_lang = self._current_lang if self._current_lang in ["ar", "en"] else "ar"
        logger.info(f"Initiating weather fetch for vehicle. Language: {api_lang}")

        # Get location
        location = await self._get_vehicle_location()

        if location is None:
            return "Vehicle tracking system unavailable or invalid coordinates."

        lat, lon = location

        # Get Weather
        weather_api_key = os.environ.get("WEATHER_API_KEY")
        if not weather_api_key:
            return "WEATHER_API_KEY is not configured."

        weather_url = "https://api.weatherapi.com/v1/current.json"

        weather_params = {"key": weather_api_key, "q": f"{lat},{lon}", "lang": api_lang}

        try:
            async with httpx2.AsyncClient() as client:
                weather_response = await client.get(weather_url, params=weather_params, timeout=5)

                if weather_response.is_success:
                    weather_data = weather_response.json()

                    city = weather_data["location"]["name"]
                    temp = weather_data["current"]["temp_c"]
                    condition = weather_data["current"]["condition"]["text"]

                    return f"The weather at the vehicle's location in {city} is {condition} with a temperature of {temp}°C."
                else:
                    logger.error(f"Weather API error: {weather_response.status_code}")
                    return "Weather service error."

        except Exception as e:
            logger.error(f"Weather API exception: {e}")
            return "Weather system unavailable."

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


server = AgentServer()


@server.rtc_session(agent_name="yaquod")
async def my_agent(ctx: agents.JobContext):
    default_config = LANGUAGE_CONFIGS[DEFAULT_LANG]

    # Pull MQTT configurations from your .env
    mqtt_host = os.environ.get("MQTT_HOST", "localhost")
    mqtt_port = int(os.environ.get("MQTT_PORT", 1883))
    mqtt_username = os.environ.get("MQTT_USERNAME", "")
    mqtt_password = os.environ.get("MQTT_PASSWORD", "")

    # Enable SSL if your port suggests it (e.g., 8883) or configure explicitly via env
    use_ssl = os.environ.get("MQTT_SSL", "true").lower() == "true"
    tls_context = ssl.create_default_context() if use_ssl else None

    logger.info(f"Connecting to MQTT Broker at {mqtt_host}:{mqtt_port}...")

    # We use aiomqtt as an async context manager to ensure the connection stays alive and cleans up
    async with aiomqtt.Client(
        hostname=mqtt_host,
        port=mqtt_port,
        username=mqtt_username if mqtt_username else None,
        password=mqtt_password if mqtt_password else None,
        tls_context=tls_context,
    ) as mqtt_client:
        session = AgentSession(
            stt=azure.STT(language=["ar-EG", "en-US"]),
            llm=inference.LLM(model="google/gemini-3.1-flash-lite"),
            tts=inference.TTS(
                model="cartesia/sonic-3.5",
                voice=default_config["voice_id"],
                language=default_config["tts_lang"],
            ),
            turn_handling=TurnHandlingOptions(turn_detection="vad"),
        )

        # Inject the active MQTT client into the Assistant
        assistant = Assistant(mqtt_client=mqtt_client)

        await session.start(room=ctx.room, agent=assistant)
        await session.generate_reply(instructions=STARTER_GREETING)

        # Keep the MQTT connection context alive until the LiveKit room disconnects
        disconnect_event = asyncio.Event()
        ctx.room.on("disconnected", disconnect_event.set)
        await disconnect_event.wait()


if __name__ == "__main__":
    agents.cli.run_app(server)

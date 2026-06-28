import json
import logging
import os
import re
from collections.abc import AsyncGenerator, AsyncIterable

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
from utils.validator import validate_vehicle_action

_TASHKEEL_RE = re.compile(r"[\u064B-\u065F\u0670]")


def _strip_tashkeel(text: str) -> str:
    return _TASHKEEL_RE.sub("", text)


logger = logging.getLogger("yaquod-agent")

_ARABIC_VOICE = (
    "f786b574-daa5-4673-aa0c-cbe3e8534c02"  # Katie (Cartesia default) — multilingual, works with ar
)
_ENGLISH_VOICE = "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc"  # Jacqueline — en-US female

LANGUAGE_CONFIGS = {
    "ar": {"stt_lang": "ar", "tts_lang": "ar", "voice_id": _ARABIC_VOICE},
    "en": {"stt_lang": "en", "tts_lang": "en", "voice_id": _ENGLISH_VOICE},
}

DEFAULT_LANG = "ar"
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
VEHICLE_API_URL = "https://yaquod-agent.fastapicloud.dev/api/vehicle"


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=SYSTEM_PROMPT)
        self._current_lang = DEFAULT_LANG

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

        self._current_lang = language

        return f"Switched to {language}"

    @function_tool
    async def vehicle_action(
        self,
        context: RunContext,
        action: str,
        parameters: dict | None = None,
    ) -> str:
        parameters = parameters or {}

        # Safety whitelist check
        if action not in ALLOWED_ACTIONS:
            return "This action is not allowed."

        # Validate parameters
        error = validate_vehicle_action(action, parameters)

        if error:
            return error

        payload = {"vehicle_id": "vehicle_001", "action": action, "parameters": parameters}

        logger.info("Vehicle Action:\n%s", json.dumps(payload, indent=2))

        try:
            async with httpx2.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{VEHICLE_API_URL}/action",
                    json=payload,
                )

            if response.is_success:
                return f"Executed {action}"
            else:
                return "Vehicle API error"

        except Exception as e:
            logger.error(f"API error: {e}")
            return "Vehicle system unavailable"

    async def _get_vehicle_location(self) -> tuple[float, float] | None:
        """Fetch current vehicle location from the vehicle API."""
        try:
            async with httpx2.AsyncClient() as client:
                response = await client.get(
                    f"{VEHICLE_API_URL}/location",
                    timeout=5.0,
                )
                if response.is_success:
                    data = response.json()
                    return data["lat"], data["lng"]
                return None
        except Exception as e:
            logger.error(f"Location fetch error: {e}")
            return None

    @function_tool
    async def search_nearby_places(
        self,
        context: RunContext,
        query: str,
        radius_meters: int = 1500,
    ) -> str:
        """Search for nearby places using Google Maps Places API."""
        if not GOOGLE_MAPS_API_KEY:
            return "Google Maps API key not configured."

        location = await self._get_vehicle_location()
        if not location:
            return "Unable to get vehicle location for search."

        lat, lng = location

        url = "https://places.googleapis.com/v1/places:searchText"
        headers = {
            "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
            "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.rating,places.currentOpeningHours.openNow",
            "Content-Type": "application/json",
        }
        payload = {
            "textQuery": query,
            "locationBias": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lng},
                    "radius": radius_meters,
                }
            },
        }

        try:
            async with httpx2.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, headers=headers, json=payload)

            if response.status_code != 200:
                return "Places search failed. Please try again."

            data = response.json()
            places = data.get("places", [])

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

        except Exception as e:
            logger.error(f"Places API error: {e}")
            return "Places search unavailable."


server = AgentServer()


@server.rtc_session(agent_name="yaquod")
async def my_agent(ctx: agents.JobContext):
    default_config = LANGUAGE_CONFIGS[DEFAULT_LANG]

    session = AgentSession(
        stt=azure.STT(
            language=["ar-EG", "en-US"],
        ),
        llm=inference.LLM(model="google/gemini-3.1-flash-lite"),
        tts=inference.TTS(
            model="cartesia/sonic-3",
            voice=default_config["voice_id"],
            language=default_config["tts_lang"],
        ),
        turn_handling=TurnHandlingOptions(
            turn_detection="vad",
        ),
    )

    await session.start(room=ctx.room, agent=Assistant())
    await session.generate_reply(instructions=STARTER_GREETING)


if __name__ == "__main__":
    agents.cli.run_app(server)

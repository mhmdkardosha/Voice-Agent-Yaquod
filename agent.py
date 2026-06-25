import logging
import re

from dotenv import load_dotenv

load_dotenv(override=True)

from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession, RunContext, function_tool
from livekit.agents.inference import TurnDetector
from livekit.plugins import google

_TASHKEEL_RE = re.compile(r"[\u064B-\u065F\u0670]")


def _strip_tashkeel(text: str) -> str:
    return _TASHKEEL_RE.sub("", text)


logger = logging.getLogger("yaquod-agent")

STARTER_GREETING = (
    "You are Yaquod (يَقُودْ). Greet the user warmly in one short Egyptian "
    "Arabic sentence, then ask how you can help.\n"
    "\n"
    "TASHKEEL: Add full tashkeel to every word.\n"
    "RESPONSE: Keep responses short, warm, and conversational."
)

LANGUAGE_CONFIGS = {
    "ar": {"stt_lang": "ar-EG", "tts_lang": "ar-XA", "voice_name": "ar-XA-Chirp3-HD-Aoede"},
    "en": {"stt_lang": "en-US", "tts_lang": "en-US", "voice_name": "en-US-Chirp3-HD-Aoede"},
}
DEFAULT_LANG = "ar"


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=(
                "<role>\n"
                "You are Yaquod (يَقُود), a friendly voice agent.\n"
                "</role>\n"
                "\n"
                "<languages>\n"
                "- Support Egyptian Arabic (اللهجة المصرية) and English.\n"
                "- Detect the user's language on every turn.\n"
                "- If it differs from the current language, call switch_language.\n"
                "- Always reply in the language the user just used.\n"
                "</languages>\n"
                "\n"
                "<tone>\n"
                "- Short, warm, conversational answers (spoken aloud).\n"
                "- Natural and polite, as if talking to a friend.\n"
                "</tone>\n"
                "\n"
                "<arabic_rule>\n"
                "TASHKEEL: Every Arabic word MUST have full tashkeel "
                "(fatha, kasra, damma, sukun, shadda). Without it the TTS "
                "mispronounces words.\n"
                "</arabic_rule>"
            )
        )
        self._current_lang = DEFAULT_LANG

    async def transcription_node(self, text, model_settings):
        async for chunk in text:
            if isinstance(chunk, str):
                yield _strip_tashkeel(chunk)
            else:
                yield chunk

    @function_tool
    async def switch_language(self, context: RunContext, language: str) -> str:
        """Switch the conversation's active language.

        Call this immediately whenever the user speaks in a different
        language than the current one, including on their first turn if it
        differs from the default. Do this before composing your reply so the
        reply is generated and spoken in the correct language.

        Args:
            language: The language code the user is now speaking.
                Must be exactly "ar" (Arabic) or "en" (English).
        """
        config = LANGUAGE_CONFIGS.get(language)
        if config is None:
            return f"Unsupported language '{language}'. Supported: ar, en."

        if language == self._current_lang:
            return f"Already using {language}."

        session = context.session
        logger.info(f"Switching language: {self._current_lang} -> {language}")

        # Only switch TTS — STT stays multilingual with detect_language=True
        session.tts.update_options(
            language=config["tts_lang"],
            voice_name=config["voice_name"],
        )

        self._current_lang = language
        return f"Switched to {language}."


server = AgentServer()


@server.rtc_session(agent_name="yaquod")
async def my_agent(ctx: agents.JobContext):
    default_config = LANGUAGE_CONFIGS[DEFAULT_LANG]

    session = AgentSession(
        stt=google.STT(
            languages=[default_config["stt_lang"], LANGUAGE_CONFIGS["en"]["stt_lang"]],
            detect_language=True,
            model="chirp_3",
            location="us",
            # ),
            #  llm=openai.LLM.with_ollama(
            # model="llama3.1:8b",
            # base_url=os.getenv("OLLAMA_BASE_URL"),
        ),
        llm=google.LLM(model="gemini-3.1-flash-lite"),
        tts=google.TTS(
            language=default_config["tts_lang"],
            voice_name=default_config["voice_name"],
        ),
        turn_detection=TurnDetector(),
    )

    await session.start(room=ctx.room, agent=Assistant())
    await session.generate_reply(instructions=STARTER_GREETING)


if __name__ == "__main__":
    agents.cli.run_app(server)

import logging
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()


from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession, RunContext, function_tool
from livekit.plugins import google, openai
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("yaquod-agent")

STARTER_GREETING = (
    "Greet the user warmly in one short sentence, then ask how you can help. "
    "Greet them in Arabic, since that's the default language."
)

LANGUAGE_CONFIGS = {
    "ar": {"stt_lang": "ar-XA", "tts_lang": "ar-XA", "voice_name": "ar-XA-Chirp3-HD-Aoede"},
    "en": {"stt_lang": "en-US", "tts_lang": "en-US", "voice_name": "en-US-Chirp3-HD-Aoede"},
}
DEFAULT_LANG = "ar"

class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=(
                "You are a helpful and concise voice assistant powered by Gemini. "
                "You support two languages: Arabic and English. "
                "Detect which language the user is speaking and call the "
                "switch_language tool with that language code ('ar' or 'en') "
                "every time you notice the user has switched languages — "
                "including on their very first utterance if it differs from "
                "the current language. Always reply in the language the user "
                "just used. "
                "Keep your answers short and conversational, as they will be "
                "spoken out loud."
            )
        )
        self._current_lang = DEFAULT_LANG

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


@server.rtc_session(agent_name="yaquod-agent")
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
         llm=google.LLM(model='gemini-2.5-flash'),
        tts=google.TTS(
            language=default_config["tts_lang"],
            voice_name=default_config["voice_name"],
        ),
        turn_detection=MultilingualModel(),
    )

    await session.start(room=ctx.room, agent=Assistant())
    await session.generate_reply(instructions=STARTER_GREETING)


if __name__ == "__main__":
    agents.cli.run_app(server)
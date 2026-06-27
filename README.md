*Maintained by Khaled Zakaria, Khaled Helmy, and Mohamed Kardosha.*

> **Note:** The commit `feat: implement vehicle action model and APIs` was authored by **Khaled Helmy** and reviewed by **Khaled Zakaria**. Their names do not appear in the commit history due to a necessary history rewrite for consistency.

# Yaquod Agent

A bilingual (Arabic/English) real-time voice AI assistant powered by **LiveKit Agents** with **Azure Speech STT**, **Cartesia TTS**, and **Gemini LLM**.

## Features

- **Real-time voice conversation** with low-latency streaming
- **Arabic (Egyptian) & English support** with automatic language detection
- **Dynamic language switching** — the agent detects when you switch languages and responds in kind
- **Azure Speech Services** for speech-to-text (`ar-EG` / `en-US`)
- **Cartesia Sonic-3** for text-to-speech (via LiveKit Inference)
- **Google Gemini 3.1 Flash Lite** for conversational LLM (via LiveKit Inference)
- **Multilingual turn detection** for natural conversation flow

## Prerequisites

- Python 3.11+
- A [LiveKit Cloud](https://livekit.io) account with Inference enabled (included on all plans)
- An [Azure Speech Services](https://azure.microsoft.com/en-us/products/ai-services/ai-speech) resource (free tier works)

## Setup

1. **Clone the repo and create the conda environment:**

   ```bash
   conda env create -f environment.yml
   conda activate livekit-agent
   ```

2. **Configure environment variables:**

   Copy `.env-example` to `.env` and fill in your credentials:

   ```bash
   cp .env-example .env
   ```

   Required variables:

   | Variable | Description |
   |---|---|
   | `LIVEKIT_URL` | LiveKit Cloud WebSocket URL |
   | `LIVEKIT_API_KEY` | LiveKit Cloud API key |
   | `LIVEKIT_API_SECRET` | LiveKit Cloud API secret |
   | `AZURE_SPEECH_KEY` | Azure Speech Services key |
   | `AZURE_SPEECH_REGION` | Azure Speech Services region (e.g. `eastus`) |

3. **Run the agent:**

   ```bash
   python agent.py start
   ```

## Alternative: Using Ollama (Llama) instead of Gemini

To run the LLM locally with Ollama instead of LiveKit Inference:

1. **Install Ollama** from [ollama.ai](https://ollama.ai) and pull a model:

   ```bash
   ollama pull llama3.1:8b
   ```

2. **In `agent.py`, replace the inference.LLM line with:**

   ```python
   llm=openai.LLM.with_ollama(
       model="llama3.1:8b",
       base_url=os.getenv("OLLAMA_BASE_URL"),
   ),
   ```

3. **Set `OLLAMA_BASE_URL` in `.env`** (defaults to `http://localhost:11434`):

   ```env
   OLLAMA_BASE_URL=http://localhost:11434
   ```

4. **Ensure Ollama is running** before starting the agent:

   ```bash
   ollama serve
   ```

> Note: STT uses Azure Speech (not LiveKit Inference) and TTS uses LiveKit Inference (Cartesia). Only the LLM changes.

## Linting & Formatting

This project uses [Ruff](https://docs.astral.sh/ruff) — a fast Python linter and formatter written in Rust.

### Commands

```bash
# Lint (report issues)
ruff check .

# Lint + auto-fix safe issues
ruff check --fix .

# Format (rewrite files in place)
ruff format .

# Check if files are already formatted (no changes)
ruff format --check .
```

### Configuration

All settings live in `pyproject.toml` under `[tool.ruff]`, `[tool.ruff.lint]`, and `[tool.ruff.format]`.

## Testing

Tests use **pytest** with mocked HTTP — no network or running server required.

### Run all tests

```bash
pytest -v
```

### Test structure

| Test file | What it covers |
| --- | --- |
| `tests/test_vehicle_api.py` | FastAPI route validation — payload format, missing fields, status codes |
| `tests/test_agent_tools.py` | Agent function-tool logic — action whitelist, payload construction, error handling, language switching |
| `tests/test_integration.py` | Agent → API wiring — verifies the agent's HTTP calls match the API's expectations |

The agent's `vehicle_action` and `switch_language` methods are tested by calling them directly with mock objects, simulating the LiveKit framework. This means if anyone edits the agent code and breaks the whitelist, payload format, or error handling, the tests fail immediately without needing a LiveKit cloud connection.

### CI

Every pull request to `main` runs Ruff linting + all tests via GitHub Actions.

## Usage

Connect using any LiveKit-compatible client (e.g., [LiveKit CLI](https://github.com/livekit/livekit-cli), [Agents Playground](https://agents-playground.livekit.io), or a custom web/mobile app).

The agent greets in Arabic by default. Speak in Arabic or English — it auto-detects and switches dynamically.

## Architecture

- `agent.py` — Main application defining the `Assistant` class and RTC session
- `environment.yml` — Conda environment specification
- `pyproject.toml` — Linting and formatting configuration (ruff)
- `tests/` — Unit tests for the agent configuration

The agent uses LiveKit Agents **v1 session API** (`Agent`, `AgentServer`, `AgentSession`):

- **STT**: `azure.STT` (Azure Speech Services) with candidate languages `["ar-EG", "en-US"]`
- **LLM**: `inference.LLM` (Gemini 3.1 Flash Lite) via LiveKit Inference
- **TTS**: `inference.TTS` (Cartesia Sonic-3) via LiveKit Inference
- **VAD**: Silero VAD for turn detection

Azure Speech requires its own API key and region. LiveKit Inference handles the rest (LLM, TTS) — no separate API keys needed beyond LiveKit Cloud credentials.

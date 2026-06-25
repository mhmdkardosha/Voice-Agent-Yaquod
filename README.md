# Yaquod Agent

A bilingual (Arabic/English) real-time voice AI assistant powered by **LiveKit Agents** and **Google Vertex AI (Gemini) / Ollama**.

## Features

- **Real-time voice conversation** with low-latency streaming
- **Arabic & English support** with automatic language detection
- **Dynamic language switching** — the agent detects when you switch languages and responds in kind
- **Google Chirp 3** for speech-to-text and text-to-speech
- **Gemini 2.5 Flash** for conversational LLM
- **Multilingual turn detection** for natural conversation flow

## Prerequisites

- Python 3.11+
- A [LiveKit Cloud](https://livekit.io) account
- A Google Cloud project with Vertex AI API enabled and a service account

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

   Place your Google Cloud service account key at `service-account.json`.

3. **Run the agent:**

   ```bash
   python agent.py start
   ```

## Alternative: Using Ollama (Llama) instead of Gemini

To run the LLM locally with Ollama instead of Google Gemini:

1. **Install Ollama** from [ollama.ai](https://ollama.ai) and pull a model:

   ```bash
   ollama pull llama3.1:8b
   ```

2. **In `agent.py`, uncomment the Ollama LLM block and comment out the Gemini line:**

   ```python
   llm=openai.LLM.with_ollama(
       model="llama3.1:8b",
       base_url=os.getenv("OLLAMA_BASE_URL"),
   ),
   # llm=google.LLM(model='gemini-2.5-flash'),
   ```

3. **Set `OLLAMA_BASE_URL` in `.env`** (defaults to `http://localhost:11434`):

   ```env
   OLLAMA_BASE_URL=http://localhost:11434
   ```

4. **Ensure Ollama is running** before starting the agent:

   ```bash
   ollama serve
   ```

> Note: With Ollama you still need Google Cloud credentials for STT and TTS (Chirp 3). Only the LLM changes.

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

## Usage

Connect using any LiveKit-compatible client (e.g., [LiveKit CLI](https://github.com/livekit/livekit-cli), [Agents Playground](https://agents-playground.livekit.io), or a custom web/mobile app).

The agent greets in Arabic by default. Speak in Arabic or English — it auto-detects and switches dynamically.

## Architecture

- `agent.py` — Main application defining the `Assistant` class and RTC session
- `environment.yml` — Conda environment specification
- `pyproject.toml` — Linting and formatting configuration (ruff)
- `tests/` — Unit tests for the agent configuration

The agent uses LiveKit Agents **v1 session API** (`Agent`, `AgentServer`, `AgentSession`) with `google.STT`, `google.LLM`, and `google.TTS` plugins, plus `TurnDetector` for turn detection.

# Yaquod Agent

A bilingual (Arabic/English) real-time voice AI assistant powered by **LiveKit Agents** with **Google Cloud STT**, **Google Cloud TTS**, and **Google Gemini LLM**.

## Features

- **Real-time voice conversation** with low-latency streaming
- **Arabic (Egyptian) & English support** with automatic language detection
- **Dynamic language switching** — the agent detects when you switch languages and responds in kind
- **Google Cloud Speech-to-Text (Chirp 3)** for multi-language transcription
- **Google Cloud Text-to-Speech (Chirp 3 HD)** for natural voice synthesis
- **Google Gemini 3.5 Flash** for conversational LLM (via Vertex AI)
- **Multilingual turn detection** for natural conversation flow
- **MQTT vehicle communication** — real-time vehicle control and telemetry via MQTT broker
- **Nearby Places Search** — find restaurants, gas stations, hospitals, and more using Google Maps Places API
- **Web Search** — search the web for any information via Brave Search API
- **Weather lookup** through WeatherAPI.com
- **Allowed-action whitelist** for vehicle controls to enforce safety
- **Docker containerization** support for easy deployment
- **Built-in simulators** including an HTML test client and an MQTT vehicle simulator

## Prerequisites

- Python 3.11+
- A [LiveKit Cloud](https://livekit.io) account
- A **Google Cloud Platform** project with Vertex AI and Speech APIs enabled, and `GOOGLE_APPLICATION_CREDENTIALS` configured
- A free **WeatherAPI** account for weather information

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
   | `GOOGLE_APPLICATION_CREDENTIALS` | Path to Google Cloud Service Account JSON key |
   | `GOOGLE_MAPS_API_KEY` | Google Maps Places API key (required for nearby places search) |
   | `WEATHER_API_KEY` | Your WeatherAPI.com API key (required for weather tool) |
   | `MQTT_HOST` | MQTT broker hostname or IP address (e.g. `localhost`) |
   | `MQTT_PORT` | MQTT broker port (e.g. `1883`) |
   | `MQTT_USERNAME` | MQTT broker username (optional) |
   | `MQTT_PASSWORD` | MQTT broker password (optional) |
   | `BRAVE_SEARCH_API_KEY` | Brave Search API key (required for web search) — get one free at https://api.search.brave.com |

3. **Run the agent:**

   ```bash
   python agent.py start
   ```

### Docker Setup

You can also run the agent using Docker:

```bash
docker build -t yaquod-agent .
docker run --env-file .env -p 8081:8081 yaquod-agent
```

### MQTT Topics

The agent communicates with the vehicle via MQTT. Here are the available topics:

#### **Publishing Topics** (Agent → Vehicle)

| Topic | Payload Schema | Example |
|---|---|---|
| `vehicle/{vehicle_id}/action` | `{"vehicle_id": "str", "action": "str", "parameters": {}}` | `{"vehicle_id": "vehicle_001", "action": "ac_on", "parameters": {}}` |
| `vehicle/{vehicle_id}/navigation/change` | `{"vehicle_id": "str", "destination": "str", "latitude": float, "longitude": float}` | `{"vehicle_id": "vehicle_001", "destination": "Cairo Tower", "latitude": 30.0444, "longitude": 31.2357}` |
| `vehicle/{vehicle_id}/navigation/cancel` | `{"vehicle_id": "str"}` | `{"vehicle_id": "vehicle_001"}` |

**Allowed Actions:**
`ac_on`, `ac_off`, `set_temperature`, `set_fan_speed`, `set_airflow_mode`, `climate_auto`, `climate_sync`, `window_open`, `window_close`, `window_lock`, `window_unlock`, `music_play`, `music_pause`, `set_volume`, `next_track`, `previous_track`, `reading_light_on`, `reading_light_off`, `change_destination`, `cancel_destination`, `safe_stop`, `seat_position`, `seat_recline`, `seat_height`
### Getting a Brave Search API Key

The agent uses **Brave Search API** to fetch real-time web information.

1. Go to [api.search.brave.com](https://api.search.brave.com/app) and create a free account.
2. Navigate to the **API Keys** section.
3. Create a new key and copy it into your `.env` as `BRAVE_SEARCH_API_KEY`.
4. The free tier provides up to 2,000 queries/month — sufficient for typical usage.

### Getting a Weather API Key

The agent uses **WeatherAPI.com** to fetch real-time weather data based on the vehicle's location.

1. Go to [WeatherAPI.com](https://www.weatherapi.com/) and click **Sign Up** to create a free account.
2. Once logged in, go to your **Dashboard**.
3. Copy your unique **API Key** from the dashboard.

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

> Note: STT and TTS use Google Cloud. Only the LLM changes.

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

### Simulators & Test Client

To test the full integration locally without the actual vehicle or a mobile app, you can use the built-in scripts:

1. **Fake Vehicle Simulator:** Subscribes to MQTT topics and simulates vehicle behavior.
   ```bash
   python scripts/fake_vehicle_simulator.py
   ```
2. **Test Client UI:** Open the test client to connect to the agent and test voice and text interactions.
   - **Remote URL:** [https://storage.googleapis.com/yaquod-test-client-project-83ac3b6e-bac2-4a8b-b48/test_client.html](https://storage.googleapis.com/yaquod-test-client-project-83ac3b6e-bac2-4a8b-b48/test_client.html)
   - Alternatively, you can open `scripts/test_client.html` locally in your browser.

   **How to Authenticate & Get a Token:**
   Before connecting on the test client webpage, you must authenticate the vehicle and generate a LiveKit token using the backend endpoints.

   1. **Login the Vehicle:** Send a `POST` request to authenticate the vehicle.
      ```bash
      curl -X POST https://yaquod-agent.fastapicloud.dev/login \
           -H "Content-Type: application/json" \
           -d '{"vin_number": "VALID_VIN_NUMBER", "vehicle_id": "vehicle_001"}'
      ```
   2. **Generate Token:** Send a `POST` request to retrieve the connection credentials.
      ```bash
      curl -X POST https://yaquod-agent.fastapicloud.dev/getToken \
           -H "Content-Type: application/json" \
           -d '{"car_id": "vehicle_001", "locale": "en-US"}'
      ```
   3. **Connect:** Copy the `participant_token` and `server_url` from the JSON response and paste them into the corresponding fields on the Test Client webpage, then click Connect.

### CI

Every pull request to `main` runs Ruff linting + all tests via GitHub Actions.

## Usage

Connect using any LiveKit-compatible client (e.g., [LiveKit CLI](https://github.com/livekit/livekit-cli), [Agents Playground](https://agents-playground.livekit.io), or a custom web/mobile app).

The agent greets in Arabic by default. Speak in Arabic or English — it auto-detects and switches dynamically.

## Architecture

- `agent.py` — Main application defining the `Assistant` class and RTC session
- `config/` — Shared constants (`ALLOWED_ACTIONS`, validation sets)
- `llm/` — `SYSTEM_PROMPT` and `STARTER_GREETING` prompt strings
- `utils/` — Helper functions for Google Places integration and vehicle action validation
- `routes/` — FastAPI app (`vehicle_api.py`) and request models (`vehicle_action_model.py`, `navigation_models.py`, `token_request_model.py`)
- `scripts/` — Test client UI (`test_client.html`) and vehicle simulator (`fake_vehicle_simulator.py`)
- `Dockerfile` & `.dockerignore` — Containerization setup
- `environment.yml` & `requirements.txt` — Environment and dependency specifications
- `pyproject.toml` — Linting, formatting, and packaging configuration (ruff + setuptools)
- `tests/` — Unit and integration tests

The agent uses LiveKit Agents **v1 session API** (`Agent`, `AgentServer`, `AgentSession`):

- **STT**: `google.STT` (Chirp 3) with language auto-detection (`ar-XA`, `en-US`)
- **LLM**: `google.LLM` (Gemini 3.5 Flash) via Vertex AI
- **TTS**: `google.TTS` (Chirp 3 HD Aoede) via Vertex AI
- **VAD**: Silero VAD for turn detection

Google STT, LLM, and TTS require Google Cloud credentials (e.g., via the `GOOGLE_APPLICATION_CREDENTIALS` environment variable).

## Contribution
*Maintained by Yaquod AI Engineering team (Mohamed Kardosha, Khaled Helmy, Khaled Zakarya).*


We accept contributions from all over the world! However, please note that our code is written in English and all commits should be in English.


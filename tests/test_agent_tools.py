import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("livekit")

from agent import ALLOWED_ACTIONS, Assistant

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_mqtt():
    """Provides a mocked async aiomqtt Client instance."""
    client = MagicMock()
    client.publish = AsyncMock()
    return client


@pytest.fixture
def assistant(mock_mqtt):
    """Instantiates Assistant with the mocked MQTT client."""
    return Assistant(mqtt_client=mock_mqtt)


@pytest.fixture
def mock_context():
    ctx = MagicMock()
    ctx.session.tts.update_options = MagicMock()
    ctx.session.say = MagicMock()
    return ctx


VALID_PARAMETERS = {
    "ac_on": {},
    "ac_off": {},
    "set_temperature": {"zone": "both", "temperature": 22},
    "set_fan_speed": {"speed": 3},
    "set_airflow_mode": {"mode": "face"},
    "climate_auto": {"enabled": True},
    "climate_sync": {"enabled": True},
    "window_open": {"window": "all", "percentage": 100},
    "window_close": {"window": "all", "percentage": 0},
    "music_play": {},
    "music_pause": {},
    "next_track": {},
    "previous_track": {},
    "set_volume": {"change": 5},
    "reading_light_on": {"light": "both"},
    "reading_light_off": {"light": "both"},
    "change_destination": {},
    "cancel_destination": {},
    "safe_stop": {},
    "seat_position": {"seat": "passenger", "percentage": 50},
    "seat_recline": {"seat": "passenger", "percentage": 0},
    "seat_height": {"seat": "passenger", "percentage": 50},
    "window_lock": {},
    "window_unlock": {},
}


class TestVehicleAction:
    async def test_allowed_action_returns_success(self, assistant, mock_mqtt, mock_context):
        result = await assistant.vehicle_action(mock_context, action="ac_on", parameters={})

        assert result == "Executed ac_on"
        mock_mqtt.publish.assert_called_once()

    async def test_sends_correct_payload(self, assistant, mock_mqtt, mock_context):
        await assistant.vehicle_action(
            mock_context, action="set_fan_speed", parameters={"speed": 3}
        )

        expected_payload = {
            "vehicle_id": "vehicle_001",
            "action": "set_fan_speed",
            "parameters": {"speed": 3},
        }

        # Pull args out to match serializable content smoothly
        topic, payload_str = mock_mqtt.publish.call_args[0]
        assert topic == "vehicle/vehicle_001/action"
        assert json.loads(payload_str) == expected_payload

    async def test_disallowed_action_is_rejected(self, assistant, mock_mqtt, mock_context):
        result = await assistant.vehicle_action(mock_context, action="accelerate", parameters={})

        assert result == "This action is not allowed."
        mock_mqtt.publish.assert_not_called()

    async def test_mqtt_publish_error(self, assistant, mock_mqtt, mock_context):
        mock_mqtt.publish.side_effect = Exception("Broker unreachable")

        result = await assistant.vehicle_action(mock_context, action="ac_on", parameters={})

        assert result == "Vehicle system unavailable"

    async def test_none_parameters_defaults_to_empty(self, assistant, mock_mqtt, mock_context):
        await assistant.vehicle_action(mock_context, action="ac_on", parameters=None)

        _, payload_str = mock_mqtt.publish.call_args[0]
        assert json.loads(payload_str)["parameters"] == {}

    async def test_all_allowed_actions_are_accepted(self, assistant, mock_context):
        for action in ALLOWED_ACTIONS:
            # Skip navigation items handled by dedicated functions if they cause structural errors
            if action in ["change_destination", "cancel_destination"]:
                continue
            with patch("utils.validator.validate_vehicle_action", return_value=None):
                result = await assistant.vehicle_action(
                    mock_context, action=action, parameters=VALID_PARAMETERS.get(action, {})
                )
                assert result == f"Executed {action}"


class TestSwitchLanguage:
    async def test_switch_to_valid_language(self, assistant, mock_context):
        result = await assistant.switch_language(mock_context, language="en")

        assert result == "Switched to en"
        assert assistant._current_lang == "en"
        mock_context.session.tts.update_options.assert_called_once()

    async def test_switch_to_same_language(self, assistant, mock_context):
        assistant._current_lang = "ar"
        result = await assistant.switch_language(mock_context, language="ar")

        assert result == "Already using ar"

    async def test_unsupported_language(self, assistant, mock_context):
        result = await assistant.switch_language(mock_context, language="fr")

        assert result == "Unsupported language 'fr'. Supported: ar, en."
        mock_context.session.tts.update_options.assert_not_called()


class TestSearchNearbyPlaces:
    async def test_successful_search_returns_formatted_results(self, assistant, mock_context):
        mock_places_response = [
            {
                "displayName": {"text": "Starbucks"},
                "formattedAddress": "123 Main St",
                "rating": 4.5,
                "currentOpeningHours": {"openNow": True},
            }
        ]
        with patch("agent.search_places_text", return_value=mock_places_response):
            result = await assistant.search_nearby_places(mock_context, query="coffee")

        assert "Starbucks" in result
        assert "Rating: 4.5" in result
        assert "Open" in result

    async def test_no_results_found(self, assistant, mock_context):
        with patch("agent.search_places_text", return_value=[]):
            result = await assistant.search_nearby_places(mock_context, query="nonexistent")

        assert result == "No results found for 'nonexistent' nearby."

    async def test_places_api_error(self, assistant, mock_context):
        with patch("agent.search_places_text", return_value=None):
            result = await assistant.search_nearby_places(mock_context, query="coffee")

        assert result == "Places search unavailable."


class TestSearchWeb:
    async def test_successful_search_returns_formatted_results(self, assistant, mock_context):
        mock_results = [
            {"title": "OpenAI", "description": "AI research company.", "url": "https://openai.com"},
        ]
        with patch("agent.search_web_util", return_value=mock_results):
            result = await assistant.search_web(mock_context, query="AI companies")

        assert "Search results:" in result
        assert "OpenAI" in result
        mock_context.session.say.assert_called_once()

    async def test_no_results_found(self, assistant, mock_context):
        with patch("agent.search_web_util", return_value=[]):
            result = await assistant.search_web(mock_context, query="xyznonexistent")

        assert "No search results found" in result


class TestGetWeather:
    async def test_successful_weather_fetch(self, assistant, mock_context):
        mock_weather_response = {
    "location": {
        "name": "Cairo",
        "localtime": "2026-07-09 20:30",
    },
    "current": {
        "temp_c": 35,
        "condition": {
            "text": "Sunny",
        },
    },
}
        
        with patch("agent.httpx2.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.is_success = True
            mock_response.json.return_value = mock_weather_response
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response

            result = await assistant.get_weather_and_time(mock_context)

        assert "Cairo" in result
        assert "35" in result

    async def test_missing_weather_api_key(self, assistant, mock_context):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("WEATHER_API_KEY", None)
            result = await assistant.get_weather_and_time(mock_context)

        assert "WEATHER_API_KEY" in result

    async def test_weather_api_error(self, assistant, mock_context):
        with (
            patch.dict(os.environ, {"WEATHER_API_KEY": "test_key"}),
            patch("httpx2.AsyncClient") as mock_client,
        ):
            mock_response = MagicMock()
            mock_response.is_success = False
            mock_response.status_code = 500
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response

            result = await assistant.get_weather_and_time(mock_context)

        assert "error" in result.lower() or "unavailable" in result.lower()


class TestNavigationMQTTActions:
    async def test_change_destination_success(self, assistant, mock_mqtt, mock_context):
        mock_place = {"name": "Mall of Arabia", "lat": 29.98, "lng": 30.95}

        with patch("agent.get_place_coordinates", return_value=mock_place):
            result = await assistant.change_destination(mock_context, destination="Mall of Arabia")

        assert "Navigation started" in result
        mock_context.session.say.assert_called_once()

        topic, payload_str = mock_mqtt.publish.call_args[0]
        assert topic == "vehicle/vehicle_001/navigation/change"
        assert json.loads(payload_str)["destination"] == "Mall of Arabia"

    async def test_change_destination_not_found(self, assistant, mock_mqtt, mock_context):
        with patch("agent.get_place_coordinates", return_value=None):
            result = await assistant.change_destination(mock_context, destination="Atlantis")

        assert "I couldn't find the destination" in result
        mock_mqtt.publish.assert_not_called()

    async def test_cancel_destination_success(self, assistant, mock_mqtt, mock_context):
        result = await assistant.cancel_destination(mock_context)

        assert result == "Navigation cancelled."
        mock_mqtt.publish.assert_called_once_with(
            "vehicle/vehicle_001/navigation/cancel", json.dumps({"vehicle_id": "vehicle_001"})
        )

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("livekit")

from agent import ALLOWED_ACTIONS, Assistant

pytestmark = pytest.mark.asyncio


@pytest.fixture
def assistant():
    return Assistant()


@pytest.fixture
def mock_context():
    ctx = MagicMock()
    ctx.session.tts.update_options = MagicMock()
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
    "set_volume": {"change": 5},
    "reading_light_on": {"light" : "both"},
    "reading_light_off": {"light" : "both"},
    "change_destination": {},
    "cancel_destination": {},
    "safe_stop": {},
    "seat_position":{"seat": "passenger", "percentage": 50},
    "seat_recline":{"seat": "passenger", "percentage": 0},
    "seat_height": {"seat": "passenger", "percentage": 50},
    "window_lock": {},
}


class TestVehicleAction:
    async def test_allowed_action_returns_success(self, assistant, mock_context):
        with patch("requests.post") as mock_post:
            mock_post.return_value.ok = True
            mock_post.return_value.status_code = 200

            result = await assistant.vehicle_action(mock_context, action="ac_on", parameters={})

        assert result == "Executed ac_on"

    async def test_sends_correct_payload(self, assistant, mock_context):
        with patch("requests.post") as mock_post:
            mock_post.return_value.ok = True

            await assistant.vehicle_action(
                mock_context, action="set_fan_speed", parameters={"speed": 3}
            )

        mock_post.assert_called_once_with(
            "https://yaquod-agent.fastapicloud.dev/api/vehicle/action",
            json={
                "vehicle_id": "vehicle_001",
                "action": "set_fan_speed",
                "parameters": {"speed": 3},
            },
            timeout=5,
        )

    async def test_disallowed_action_is_rejected(self, assistant, mock_context):
        with patch("requests.post") as mock_post:
            result = await assistant.vehicle_action(
                mock_context, action="accelerate", parameters={}
            )

        assert result == "This action is not allowed."
        mock_post.assert_not_called()

    async def test_api_error_response(self, assistant, mock_context):
        with patch("requests.post") as mock_post:
            mock_post.return_value.ok = False
            mock_post.return_value.status_code = 500

            result = await assistant.vehicle_action(mock_context, action="ac_on", parameters={})

        assert result == "Vehicle API error"

    async def test_network_error(self, assistant, mock_context):
        with patch("requests.post") as mock_post:
            mock_post.side_effect = Exception("Connection refused")

            result = await assistant.vehicle_action(mock_context, action="ac_on", parameters={})

        assert result == "Vehicle system unavailable"

    async def test_none_parameters_defaults_to_empty(self, assistant, mock_context):
        with patch("requests.post") as mock_post:
            mock_post.return_value.ok = True

            await assistant.vehicle_action(mock_context, action="ac_on", parameters=None)

        mock_post.assert_called_once_with(
            "https://yaquod-agent.fastapicloud.dev/api/vehicle/action",
            json={"vehicle_id": "vehicle_001", "action": "ac_on", "parameters": {}},
            timeout=5,
        )

    async def test_all_allowed_actions_are_accepted(self, assistant, mock_context):
        for action in ALLOWED_ACTIONS:
            with patch("requests.post") as mock_post:
                mock_post.return_value.ok = True

                result = await assistant.vehicle_action(
                    mock_context,
                    action=action,
                    parameters=VALID_PARAMETERS[action],
                )

            assert result == f"Executed {action}", f"Failed for action: {action}"


class TestSwitchLanguage:
    async def test_switch_to_valid_language(self, assistant, mock_context):
        result = await assistant.switch_language(mock_context, language="en")

        assert result == "Switched to en"
        mock_context.session.tts.update_options.assert_called_once()

    async def test_switch_to_same_language(self, assistant, mock_context):
        await assistant.switch_language(mock_context, language="ar")

        result = await assistant.switch_language(mock_context, language="ar")

        assert result == "Already using ar"

    async def test_unsupported_language(self, assistant, mock_context):
        result = await assistant.switch_language(mock_context, language="fr")

        assert result == "Unsupported language 'fr'. Supported: ar, en."
        mock_context.session.tts.update_options.assert_not_called()

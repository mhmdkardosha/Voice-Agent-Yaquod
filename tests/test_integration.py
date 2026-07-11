import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("livekit")

from fastapi.testclient import TestClient

from agent import Assistant
from routes.vehicle_api import app as fastapi_app

pytestmark = pytest.mark.asyncio

HEADERS = {
    "API-Key": os.environ.get("YAQUOD_API_KEY", "test_key"),
}


@pytest.fixture
def api_client():
    return TestClient(fastapi_app)


@pytest.fixture
def mock_mqtt():
    """Provides a mocked MQTT service."""
    client = MagicMock()
    client.publish_action = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_context():
    return MagicMock()


async def test_api_receives_correct_action(api_client, mock_mqtt, mock_context):
    with (
        patch("agent.central_mqtt", mock_mqtt),
        patch("services.mqtt_service.central_mqtt", mock_mqtt),
    ):
        assistant = Assistant(vehicle_id="vehicle_001")

        result = await assistant.vehicle_action(mock_context, action="music_play", parameters={})

    assert result == "Executed music_play"

    expected_payload = {
        "vehicle_id": "vehicle_001",
        "action": "music_play",
        "parameters": {},
    }

    car_id, action_type, payload = mock_mqtt.publish_action.call_args[0]

    assert car_id == "vehicle_001"
    assert action_type == "action"
    assert payload == expected_payload

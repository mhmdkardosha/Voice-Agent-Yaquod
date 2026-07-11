import json
import os
from unittest.mock import AsyncMock, MagicMock

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
    """Provides a mocked async aiomqtt Client instance."""
    client = MagicMock()
    client.publish = AsyncMock()
    return client


@pytest.fixture
def mock_context():
    return MagicMock()


async def test_api_receives_correct_action(api_client, mock_mqtt, mock_context):
    # Inject the mocked MQTT client into the Assistant
    assistant = Assistant(mqtt_client=mock_mqtt)

    # Execute the action via the Assistant instance
    result = await assistant.vehicle_action(mock_context, action="music_play", parameters={})

    # Assert that the assistant processes and indicates execution success
    assert result == "Executed music_play"

    # Verify that the correct payload was published to the proper MQTT topic
    expected_payload = {
        "vehicle_id": "vehicle_001",
        "action": "music_play",
        "parameters": {},
    }

    # Extract args to safely match serialized JSON structures
    topic, payload_str = mock_mqtt.publish.call_args[0]
    assert topic == "vehicle/vehicle_001/action"
    assert json.loads(payload_str) == expected_payload

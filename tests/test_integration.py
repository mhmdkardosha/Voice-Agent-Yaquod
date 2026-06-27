from unittest.mock import MagicMock, patch
from urllib.parse import urlparse

import pytest

pytest.importorskip("livekit")

from fastapi.testclient import TestClient

from agent import Assistant
from routes.vehicle_api import app as fastapi_app

pytestmark = pytest.mark.asyncio


@pytest.fixture
def api_client():
    return TestClient(fastapi_app)


@pytest.fixture
def mock_context():
    return MagicMock()


class _CompatResponse:
    def __init__(self, resp):
        self.status_code = resp.status_code
        self.ok = 200 <= resp.status_code < 300

    def __bool__(self):
        return self.ok


def _route_through_testclient(api_client):
    def inner(url, json=None, **kwargs):
        path = urlparse(url).path
        raw = api_client.post(path, json=json)
        return _CompatResponse(raw)

    return inner


async def test_agent_sends_action_to_api(api_client, mock_context):
    assistant = Assistant()

    with patch("requests.post", side_effect=_route_through_testclient(api_client)):
        result = await assistant.vehicle_action(mock_context, action="ac_on", parameters={})

    assert result == "Executed ac_on"


async def test_api_receives_correct_action(api_client, mock_context):
    assistant = Assistant()

    with patch("requests.post", side_effect=_route_through_testclient(api_client)):
        await assistant.vehicle_action(mock_context, action="music_play", parameters={"track": "1"})


async def test_invalid_action_stops_at_agent(api_client, mock_context):
    assistant = Assistant()

    with patch("requests.post", side_effect=_route_through_testclient(api_client)) as mock_post:
        result = await assistant.vehicle_action(mock_context, action="accelerate", parameters={})

    assert result == "This action is not allowed."
    mock_post.assert_not_called()

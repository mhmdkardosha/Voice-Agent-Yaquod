from unittest.mock import AsyncMock, MagicMock, patch
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


def _make_httpx_router(api_client):
    """Return an httpx.AsyncClient mock that routes POST calls through the FastAPI TestClient."""

    async def _fake_post(url, **kwargs):
        path = urlparse(url).path
        raw = api_client.post(path, json=kwargs.get("json"))
        response = MagicMock()
        response.is_success = 200 <= raw.status_code < 300
        return response

    mock_cls = MagicMock()
    mock_instance = AsyncMock()
    mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
    mock_instance.post = AsyncMock(side_effect=_fake_post)
    return mock_cls


async def test_api_receives_correct_action(api_client, mock_context):
    assistant = Assistant()
    mock_httpx = _make_httpx_router(api_client)

    with patch("httpx2.AsyncClient", new=mock_httpx):
        result = await assistant.vehicle_action(
            mock_context, action="music_play", parameters={"track": "1"}
        )

    assert result == "Executed music_play"
    mock_httpx.return_value.__aenter__.return_value.post.assert_called_once_with(
        "https://yaquod-agent.fastapicloud.dev/api/vehicle/action",
        json={
            "vehicle_id": "vehicle_001",
            "action": "music_play",
            "parameters": {"track": "1"},
        },
    )

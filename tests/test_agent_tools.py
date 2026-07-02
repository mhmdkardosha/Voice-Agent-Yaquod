import os
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
    async def test_allowed_action_returns_success(self, assistant, mock_context):
        with patch("httpx2.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.is_success = True
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

            result = await assistant.vehicle_action(mock_context, action="ac_on", parameters={})

        assert result == "Executed ac_on"

    async def test_sends_correct_payload(self, assistant, mock_context):
        with patch("httpx2.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.is_success = True
            mock_post = mock_client.return_value.__aenter__.return_value.post
            mock_post.return_value = mock_response

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
        )

    async def test_disallowed_action_is_rejected(self, assistant, mock_context):
        with patch("httpx2.AsyncClient") as mock_client:
            result = await assistant.vehicle_action(
                mock_context, action="accelerate", parameters={}
            )

        assert result == "This action is not allowed."
        mock_client.assert_not_called()

    async def test_api_error_response(self, assistant, mock_context):
        with patch("httpx2.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.is_success = False
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response

            result = await assistant.vehicle_action(mock_context, action="ac_on", parameters={})

        assert result == "Vehicle API error"

    async def test_network_error(self, assistant, mock_context):
        with patch("httpx2.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post.side_effect = Exception(
                "Connection refused"
            )

            result = await assistant.vehicle_action(mock_context, action="ac_on", parameters={})

        assert result == "Vehicle system unavailable"

    async def test_none_parameters_defaults_to_empty(self, assistant, mock_context):
        with patch("httpx2.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.is_success = True
            mock_post = mock_client.return_value.__aenter__.return_value.post
            mock_post.return_value = mock_response

            await assistant.vehicle_action(mock_context, action="ac_on", parameters=None)

        mock_post.assert_called_once_with(
            "https://yaquod-agent.fastapicloud.dev/api/vehicle/action",
            json={"vehicle_id": "vehicle_001", "action": "ac_on", "parameters": {}},
        )

    async def test_all_allowed_actions_are_accepted(self, assistant, mock_context):
        for action in ALLOWED_ACTIONS:
            with patch("httpx2.AsyncClient") as mock_client:
                mock_response = MagicMock()
                mock_response.is_success = True
                mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
                result = await assistant.vehicle_action(
                    mock_context, action=action, parameters=VALID_PARAMETERS[action]
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


class TestSearchNearbyPlaces:
    async def test_missing_api_key(self, assistant, mock_context):
        with patch("agent.GOOGLE_MAPS_API_KEY", ""):
            result = await assistant.search_nearby_places(mock_context, query="coffee")
        assert "API key not configured" in result

    async def test_location_fetch_fails(self, assistant, mock_context):
        with (
            patch("agent.GOOGLE_MAPS_API_KEY", "test_key"),
            patch("httpx2.AsyncClient") as mock_client,
        ):
            mock_client.return_value.__aenter__.return_value.get.side_effect = Exception(
                "Network error"
            )
            result = await assistant.search_nearby_places(mock_context, query="coffee")
        assert "Unable to get vehicle location" in result

    def _mock_location_get(self, mock_client, lat: float, lng: float):
        mock_client.return_value.__aenter__.return_value.get.return_value = MagicMock(
            is_success=True,
            json=lambda: {"vehicle_id": "vehicle_001", "lat": lat, "lng": lng},
        )

    async def test_successful_search_returns_formatted_results(self, assistant, mock_context):
        mock_places_response = {
            "places": [
                {
                    "displayName": {"text": "Starbucks"},
                    "formattedAddress": "123 Main St",
                    "rating": 4.5,
                    "currentOpeningHours": {"openNow": True},
                },
                {
                    "displayName": {"text": "Local Cafe"},
                    "formattedAddress": "456 Oak Ave",
                    "rating": 4.2,
                    "currentOpeningHours": {"openNow": False},
                },
            ]
        }
        with (
            patch("agent.GOOGLE_MAPS_API_KEY", "test_key"),
            patch("httpx2.AsyncClient") as mock_client,
        ):
            self._mock_location_get(mock_client, lat=1.0, lng=2.0)
            mock_client.return_value.__aenter__.return_value.post.return_value = MagicMock(
                status_code=200, json=lambda: mock_places_response
            )
            result = await assistant.search_nearby_places(mock_context, query="coffee")

        assert "Starbucks" in result
        assert "Local Cafe" in result
        assert "Open" in result
        assert "Closed" in result
        assert "Rating: 4.5" in result

    async def test_search_places_api_request_shape(self, assistant, mock_context):
        mock_lat, mock_lng = 1.0, 2.0
        with (
            patch("agent.GOOGLE_MAPS_API_KEY", "test_key"),
            patch("httpx2.AsyncClient") as mock_client,
        ):
            self._mock_location_get(mock_client, lat=mock_lat, lng=mock_lng)
            mock_post = mock_client.return_value.__aenter__.return_value.post
            mock_post.return_value = MagicMock(status_code=200, json=lambda: {"places": []})
            await assistant.search_nearby_places(mock_context, query="coffee")

        mock_post.assert_called_once_with(
            "https://places.googleapis.com/v1/places:searchText",
            headers={
                "X-Goog-Api-Key": "test_key",
                "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.rating,places.currentOpeningHours.openNow",
                "Content-Type": "application/json",
            },
            json={
                "textQuery": "coffee",
                "locationBias": {
                    "circle": {
                        "center": {"latitude": mock_lat, "longitude": mock_lng},
                        "radius": 1500,
                    }
                },
            },
        )

    async def test_no_results_found(self, assistant, mock_context):
        with (
            patch("agent.GOOGLE_MAPS_API_KEY", "test_key"),
            patch("httpx2.AsyncClient") as mock_client,
        ):
            self._mock_location_get(mock_client, lat=1.0, lng=2.0)
            mock_client.return_value.__aenter__.return_value.post.return_value = MagicMock(
                status_code=200, json=lambda: {"places": []}
            )
            result = await assistant.search_nearby_places(mock_context, query="nonexistent")
        assert "No results found" in result

    async def test_api_error_returns_graceful_message(self, assistant, mock_context):
        with (
            patch("agent.GOOGLE_MAPS_API_KEY", "test_key"),
            patch("httpx2.AsyncClient") as mock_client,
        ):
            self._mock_location_get(mock_client, lat=1.0, lng=2.0)
            mock_client.return_value.__aenter__.return_value.post.return_value = MagicMock(
                status_code=500
            )
            result = await assistant.search_nearby_places(mock_context, query="coffee")
        assert result == "Places search failed. Please try again."


class TestGetWeather:
    def _mock_location_success(self, mock_client, lat: float, lng: float):
        mock_client.return_value.__aenter__.return_value.get.return_value = MagicMock(
            is_success=True,
            json=lambda: {"vehicle_id": "vehicle_001", "lat": lat, "lng": lng},
        )

    async def test_successful_weather_fetch(self, assistant, mock_context):
        mock_weather_response = {
            "location": {"name": "Cairo"},
            "current": {"temp_c": 35, "condition": {"text": "Sunny"}},
        }

        with (
            patch.dict(os.environ, {"WEATHER_API_KEY": "test_key"}),
            patch("httpx2.AsyncClient") as mock_client,
        ):
            # First call: location GET, Second call: weather GET
            mock_get = mock_client.return_value.__aenter__.return_value.get
            location_response = MagicMock(
                is_success=True,
                json=lambda: {"vehicle_id": "vehicle_001", "lat": 30.0, "lng": 31.0},
            )
            weather_response = MagicMock(
                is_success=True,
                json=lambda: mock_weather_response,
            )
            mock_get.side_effect = [location_response, weather_response]

            result = await assistant.get_weather(mock_context)

        assert "Cairo" in result
        assert "35" in result
        assert "Sunny" in result

    async def test_location_unavailable(self, assistant, mock_context):
        with patch("httpx2.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get.return_value = MagicMock(
                is_success=False,
            )

            result = await assistant.get_weather(mock_context)

        assert "unavailable" in result.lower() or "invalid" in result.lower()

    async def test_weather_api_error(self, assistant, mock_context):
        with (
            patch.dict(os.environ, {"WEATHER_API_KEY": "test_key"}),
            patch("httpx2.AsyncClient") as mock_client,
        ):
            mock_get = mock_client.return_value.__aenter__.return_value.get
            location_response = MagicMock(
                is_success=True,
                json=lambda: {"vehicle_id": "vehicle_001", "lat": 30.0, "lng": 31.0},
            )
            weather_error_response = MagicMock(
                is_success=False,
                status_code=500,
            )
            mock_get.side_effect = [location_response, weather_error_response]

            result = await assistant.get_weather(mock_context)

        assert "error" in result.lower() or "unavailable" in result.lower()

    async def test_weather_network_exception(self, assistant, mock_context):
        with (
            patch.dict(os.environ, {"WEATHER_API_KEY": "test_key"}),
            patch("httpx2.AsyncClient") as mock_client,
        ):
            mock_get = mock_client.return_value.__aenter__.return_value.get
            location_response = MagicMock(
                is_success=True,
                json=lambda: {"vehicle_id": "vehicle_001", "lat": 30.0, "lng": 31.0},
            )
            mock_get.side_effect = [location_response, Exception("Connection timeout")]

            result = await assistant.get_weather(mock_context)

        assert "unavailable" in result.lower()

    async def test_missing_weather_api_key(self, assistant, mock_context):
        with (
            patch.dict(os.environ, {}, clear=False),
            patch("httpx2.AsyncClient") as mock_client,
        ):
            os.environ.pop("WEATHER_API_KEY", None)
            self._mock_location_success(mock_client, lat=30.0, lng=31.0)

            result = await assistant.get_weather(mock_context)

        assert "WEATHER_API_KEY" in result
        assert "configured" in result.lower()

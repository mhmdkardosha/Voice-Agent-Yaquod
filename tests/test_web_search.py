from unittest.mock import MagicMock, patch

import pytest

from utils.web_search import search_web

pytestmark = pytest.mark.asyncio

_BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"


class TestSearchWebDirect:
    async def test_missing_api_key_returns_none(self):
        with patch("utils.web_search.BRAVE_SEARCH_API_KEY", ""):
            with patch("utils.web_search.logger.error") as mock_log:
                result = await search_web("test")

        assert result is None
        mock_log.assert_called_once_with("BRAVE_SEARCH_API_KEY not configured.")

    async def test_sends_request_with_expected_headers_and_params(self):
        mock_response = MagicMock(is_success=True)
        mock_response.json.return_value = {"web": {"results": []}}

        with patch("utils.web_search.BRAVE_SEARCH_API_KEY", "test-key-123"):
            with patch("httpx2.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.get.return_value = (
                    mock_response
                )

                result = await search_web("hello")

        assert result == []
        mock_client.assert_called_once_with(timeout=10.0)
        get_call = (
            mock_client.return_value.__aenter__.return_value.get.call_args
        )
        assert get_call[0][0] == _BRAVE_URL
        assert get_call[1]["headers"]["X-Subscription-Token"] == "test-key-123"
        assert get_call[1]["headers"]["Accept"] == "application/json"
        assert get_call[1]["params"]["q"] == "hello"
        assert get_call[1]["params"]["count"] == "5"

    async def test_includes_search_lang_when_provided(self):
        mock_response = MagicMock(is_success=True)
        mock_response.json.return_value = {"web": {"results": []}}

        with patch("utils.web_search.BRAVE_SEARCH_API_KEY", "test-key-123"):
            with patch("httpx2.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.get.return_value = (
                    mock_response
                )

                result = await search_web("hello", search_lang="ar")

        assert result == []
        params = (
            mock_client.return_value.__aenter__.return_value.get.call_args[1][
                "params"
            ]
        )
        assert params["search_lang"] == "ar"
        assert params["q"] == "hello"
        assert params["count"] == "5"

    async def test_non_2xx_response_returns_none_and_logs(self):
        mock_response = MagicMock(is_success=False, status_code=401)
        mock_response.text = "Unauthorized"

        with patch("utils.web_search.BRAVE_SEARCH_API_KEY", "test-key-123"):
            with patch("httpx2.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.get.return_value = (
                    mock_response
                )
                with patch("utils.web_search.logger.error") as mock_log:
                    result = await search_web("test")

        assert result is None
        mock_log.assert_called_once_with(
            "Brave Search API error: 401 Unauthorized"
        )

    async def test_exception_during_request_returns_none_and_logs(self):
        with patch("utils.web_search.BRAVE_SEARCH_API_KEY", "test-key-123"):
            with patch("httpx2.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.get.side_effect = (
                    Exception("Connection failed")
                )
                with patch("utils.web_search.logger.error") as mock_log:
                    result = await search_web("test")

        assert result is None
        mock_log.assert_called_once_with(
            "Brave Search API exception: Connection failed"
        )

    async def test_successful_response_returns_formatted_results(self):
        mock_json = {
            "web": {
                "results": [
                    {
                        "title": "Result A",
                        "description": "Desc A",
                        "url": "https://a.com",
                    },
                    {
                        "title": "Result B",
                        "description": "Desc B",
                        "url": "https://b.com",
                    },
                    {
                        "title": "Result C",
                        "description": "Desc C",
                        "url": "https://c.com",
                    },
                ]
            }
        }
        mock_response = MagicMock(is_success=True)
        mock_response.json.return_value = mock_json

        with patch("utils.web_search.BRAVE_SEARCH_API_KEY", "test-key-123"):
            with patch("httpx2.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.get.return_value = (
                    mock_response
                )

                result = await search_web("test", count=2)

        assert len(result) == 2
        assert result[0] == {
            "title": "Result A",
            "description": "Desc A",
            "url": "https://a.com",
        }
        assert result[1] == {
            "title": "Result B",
            "description": "Desc B",
            "url": "https://b.com",
        }

    async def test_honors_count_in_result_truncation(self):
        mock_json = {
            "web": {
                "results": [
                    {"title": f"Result {i}", "description": "", "url": ""}
                    for i in range(10)
                ]
            }
        }
        mock_response = MagicMock(is_success=True)
        mock_response.json.return_value = mock_json

        with patch("utils.web_search.BRAVE_SEARCH_API_KEY", "test-key-123"):
            with patch("httpx2.AsyncClient") as mock_client:
                mock_client.return_value.__aenter__.return_value.get.return_value = (
                    mock_response
                )

                result = await search_web("test", count=3)

        assert len(result) == 3

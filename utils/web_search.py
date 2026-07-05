import logging
import os

import httpx2

logger = logging.getLogger("yaquod-agent")

BRAVE_SEARCH_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY", "")

_BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


async def search_web(
    query: str,
    count: int = 5,
    timeout: float = 10.0,
) -> list[dict] | None:
    if not BRAVE_SEARCH_API_KEY:
        logger.error("BRAVE_SEARCH_API_KEY not configured.")
        return None

    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": BRAVE_SEARCH_API_KEY,
    }
    params = {"q": query, "count": str(count)}

    try:
        async with httpx2.AsyncClient(timeout=timeout) as client:
            response = await client.get(_BRAVE_SEARCH_URL, headers=headers, params=params)

        if not response.is_success:
            logger.error(f"Brave Search API error: {response.status_code} {response.text}")
            return None

        data = response.json()
        web_results = data.get("web", {}).get("results", [])

        results = []
        for r in web_results[:count]:
            results.append({
                "title": r.get("title", ""),
                "description": r.get("description", ""),
                "url": r.get("url", ""),
            })

        return results

    except Exception as e:
        logger.error(f"Brave Search API exception: {e}")
        return None

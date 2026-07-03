import logging
import os

import httpx2

logger = logging.getLogger("yaquod-agent")

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

_FIELD_MASK = "places.displayName,places.formattedAddress,places.location,places.rating,places.currentOpeningHours.openNow"


async def search_places_text(
    query: str,
    location_bias: tuple[float, float] | None = None,
    radius_meters: int = 1500,
    timeout: float = 10.0,
) -> list[dict] | None:
    """
    Call Google Places `searchText` and return the raw `places` list.
    Returns None on any failure (missing key, HTTP error, network error).
    Returns [] if the request succeeded but found nothing.
    """
    if not GOOGLE_MAPS_API_KEY:
        logger.error("Google Maps API key not configured.")
        return None

    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": _FIELD_MASK,
    }
    payload: dict = {"textQuery": query}

    if location_bias is not None:
        lat, lng = location_bias
        payload["locationBias"] = {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": radius_meters,
            }
        }

    try:
        async with httpx2.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, headers=headers, json=payload)

        if not response.is_success:
            logger.error(f"Places API error: {response.status_code} {response.text}")
            return None

        return response.json().get("places", [])

    except Exception as e:
        logger.error(f"Places API exception: {e}")
        return None

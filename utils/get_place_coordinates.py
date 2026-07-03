import os

import httpx

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")


async def get_place_coordinates(destination: str) -> dict | None:
    """
    Search Google Places and return the first matching place.
    """
    if not GOOGLE_MAPS_API_KEY:
        return None

    url = "https://places.googleapis.com/v1/places:searchText"

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_MAPS_API_KEY,
        "X-Goog-FieldMask": ("places.displayName,places.formattedAddress,places.location"),
    }

    body = {
        "textQuery": destination,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            url,
            headers=headers,
            json=body,
        )

    if not response.is_success:
        return None

    data = response.json()

    places = data.get("places", [])

    if not places:
        return None

    place = places[0]

    return {
        "name": place["displayName"]["text"],
        "address": place.get("formattedAddress"),
        "lat": place["location"]["latitude"],
        "lng": place["location"]["longitude"],
    }

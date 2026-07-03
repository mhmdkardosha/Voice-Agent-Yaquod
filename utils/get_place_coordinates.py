from utils.google_places import search_places_text


async def get_place_coordinates(destination: str) -> dict | None:
    """
    Search Google Places and return the first matching place.
    """

    places = await search_places_text(destination)

    if not places:
        return None

    place = places[0]

    return {
        "name": place["displayName"]["text"],
        "address": place.get("formattedAddress"),
        "lat": place["location"]["latitude"],
        "lng": place["location"]["longitude"],
    }

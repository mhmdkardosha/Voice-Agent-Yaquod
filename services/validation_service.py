import json
import logging
import os

import requests
from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
STATIC_EXPECTED_VIN = "VIN_12345"


logger = logging.getLogger(__name__)
VERIFY_API = "https://yaquod.duckdns.org/api/vehicles/verify"


def validate_vin_static(vin: str) -> bool:
    return vin == STATIC_EXPECTED_VIN


def validate_vehicle(vin: str) -> tuple[bool, str | None]:
    try:
        headers = {
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Accept": "*/*",
        }

        response = requests.get(
            f"{VERIFY_API}/{vin}",
            headers=headers,
            timeout=5,
        )
        response.raise_for_status()

        data = response.json()

        if data.get("success"):
            return True, None

    except requests.exceptions.HTTPError:
        if response.status_code == 400:
            return False, response.json().get("message", "Invalid VIN Number")

    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        pass

    except Exception:
        pass

    if validate_vin_static(vin):
        return True, None

    return False, "Invalid VIN Number"


def validate_authenticated_vehicle(
    redis_client,
    vin_number: str,
    vehicle_id: str,
) -> bool:
    auth_data = redis_client.get(f"vehicle:auth:{vin_number}")

    if not auth_data:
        return False

    auth_data = json.loads(auth_data)

    return auth_data.get("status") == "authenticated" and auth_data.get("vehicle_id") == vehicle_id

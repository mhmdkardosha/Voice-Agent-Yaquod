import json

STATIC_EXPECTED_VIN = "VIN_12345"
STATIC_EXPECTED_JWT = "JWT_SECRET_TOKEN"


def validate_vin(vin: str) -> bool:
    return vin == STATIC_EXPECTED_VIN


def validate_token(token: str) -> bool:
    return token == STATIC_EXPECTED_JWT


def validate_vehicle(vin: str, token: str) -> tuple[bool, str | None]:
    if not validate_vin(vin):
        return False, "Invalid VIN Number"

    if not validate_token(token):
        return False, "Invalid JWT Token"

    return True, None


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

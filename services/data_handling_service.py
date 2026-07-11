import json
import logging

from redis.asyncio import Redis

from routes.models.vehicle_data_model import VehicleData
from services.validation_service import validate_authenticated_vehicle

logger = logging.getLogger("yaquod-agent")


async def handle_vehicle_message(topic: str, payload: bytes, r_client: Redis):
    try:
        parts = topic.split("/")
        if len(parts) < 3:
            return

        vehicle_id = parts[1]
        data_type = parts[2]

        incoming_data = json.loads(payload.decode())
        vin_number = incoming_data.get("vin_number")

        if not vin_number or not validate_authenticated_vehicle(r_client, vin_number, vehicle_id):
            logger.debug(
                f"Unauthorized vehicle attempt. VIN: {vin_number}, Vehicle ID: {vehicle_id}"
            )
            return

        incoming_data["vehicle_id"] = vehicle_id

        redis_key = f"vehicle:status:{vehicle_id}"
        existing_data_str = r_client.get(redis_key)

        if existing_data_str:
            existing_data = json.loads(existing_data_str)
            existing_data.update(incoming_data)
            merged_payload = existing_data
        else:
            merged_payload = incoming_data

        vehicle_data = VehicleData(**merged_payload)

        data_to_store = vehicle_data.model_dump()
        data_to_store.pop("vin_number", None)

        r_client.set(redis_key, json.dumps(data_to_store))

        logger.info(f"Updated {data_type} for vehicle: {vehicle_id}")

    except Exception:
        logger.exception(f"Error handling MQTT message on {topic}")

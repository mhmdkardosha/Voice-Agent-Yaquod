import asyncio
import json
import logging
import aiomqtt
from config.redis_db import get_redis
from routes.models.vehicle_data_model import VehicleData

logger = logging.getLogger("yaquod-agent")

async def handle_vehicle_message(topic: str, payload: bytes):
    try:
        parts = topic.split('/')
        if len(parts) < 3:
            return
            
        vehicle_id = parts[1]
        data_type = parts[2]
        
        incoming_data = json.loads(payload.decode())
        incoming_data["vehicle_id"] = vehicle_id

        r_client = get_redis()
        redis_key = f"vehicle:status:{vehicle_id}"
        existing_data_str = r_client.get(redis_key)
        
        if existing_data_str:
            existing_data = json.loads(existing_data_str)
            existing_data.update(incoming_data)
            merged_payload = existing_data
        else:
            merged_payload = incoming_data

        vehicle_data = VehicleData(**merged_payload)
        r_client.set(redis_key, vehicle_data.model_dump_json())
        
        logger.info(f"Updated {data_type} for vehicle: {vehicle_id}")
        
    except Exception as e:
        logger.error(f"Error handling MQTT message on {topic}: {e}")

async def listen_to_mqtt_state(mqtt_client: aiomqtt.Client):
    try:
        await mqtt_client.subscribe("vehicle/+/state")
        await mqtt_client.subscribe("vehicle/+/location")
        logger.info("Subscribed to vehicle/+/state AND vehicle/+/location")
        
        async for message in mqtt_client.messages:
            await handle_vehicle_message(message.topic.value, message.payload)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error(f"MQTT listener error: {e}")
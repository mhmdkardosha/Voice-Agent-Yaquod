import logging
import os
import secrets
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi_mqtt import FastMQTT, MQTTConfig

from routes.models.navigation_models import CancelDestination, ChangeDestination
from routes.models.vehicle_action_model import VehicleAction, VehicleLocation

load_dotenv()

logger = logging.getLogger("yaquod-api")

API_KEY = os.environ["YAQUOD_API_KEY"]

mqtt_config = MQTTConfig(
    host=os.environ["MQTT_HOST"],
    port=int(os.environ["MQTT_PORT"]),
    keepalive=60,
    username=os.environ["MQTT_USERNAME"],
    password=os.environ["MQTT_PASSWORD"],
    ssl=True,
)

fast_mqtt = FastMQTT(config=mqtt_config)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await fast_mqtt.mqtt_startup()
    yield
    await fast_mqtt.mqtt_shutdown()


# Default test location (Cairo, Egypt) - replace with real GPS in production
_DEFAULT_LOCATION = VehicleLocation(vehicle_id="vehicle_001", lat=30.0444, lng=31.2357)


app = FastAPI(lifespan=lifespan)


async def publish(topic: str, payload: str) -> bool:
    """Publish a message to MQTT and return success status."""
    try:
        fast_mqtt.publish(topic, payload)
        logger.info(f"MQTT published to {topic}")
        return True
    except Exception as e:
        logger.error(f"MQTT publish failed: {e}")
        return False


def verify_api_key(api_key: str = Header(..., alias="API-Key")) -> None:
    if not secrets.compare_digest(api_key, API_KEY):
        logger.warning("Unauthorized HTTP request.")
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
        )


@app.get("/vehicle/location", dependencies=[Depends(verify_api_key)])
async def get_vehicle_location() -> VehicleLocation:
    return _DEFAULT_LOCATION


@app.post("/vehicle/action", dependencies=[Depends(verify_api_key)])
async def vehicle_action(data: VehicleAction):
    logger.info("Action received | vehicle_id=%s action=%s", data.vehicle_id, data.action)

    topic = f"vehicle/{data.vehicle_id}/action"
    success = await publish(topic, data.model_dump_json())

    if success:
        return {
            "status": "success",
            "message": "Vehicle action broadcasted.",
        }
    else:
        return {
            "status": "error",
            "message": "Failed to publish action.",
        }


@app.post("/vehicle/navigation/change", dependencies=[Depends(verify_api_key)])
async def change_destination(data: ChangeDestination):
    logger.info(
        f"Navigation request | vehicle_id={data.vehicle_id} destination={data.destination} latitude={data.latitude} longitude={data.longitude}"
    )

    topic = f"vehicle/{data.vehicle_id}/navigation/change"
    success = await publish(topic, data.model_dump_json())

    if success:
        return {
            "success": True,
            "message": f"Navigation started to {data.destination}.",
        }
    else:
        return {
            "success": False,
            "message": "Failed to start navigation.",
        }


@app.post("/vehicle/navigation/cancel", dependencies=[Depends(verify_api_key)])
async def cancel_destination(data: CancelDestination):
    logger.info(f"Navigation cancelled | vehicle_id={data.vehicle_id}")

    topic = f"vehicle/{data.vehicle_id}/navigation/cancel"
    success = await publish(topic, data.model_dump_json())

    if success:
        return {
            "success": True,
            "message": "Navigation cancelled.",
        }
    else:
        return {
            "success": False,
            "message": "Failed to cancel navigation.",
        }

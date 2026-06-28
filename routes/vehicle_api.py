import logging

from fastapi import FastAPI

from routes.models.vehicle_action_model import VehicleAction, VehicleLocation

app = FastAPI()

logger = logging.getLogger("yaquod-api")

# Default test location (Cairo, Egypt) - replace with real GPS in production
_DEFAULT_LOCATION = VehicleLocation(vehicle_id="vehicle_001", lat=30.0444, lng=31.2357)


@app.get("/api/vehicle/location")
async def get_vehicle_location() -> VehicleLocation:
    return _DEFAULT_LOCATION


@app.post("/api/vehicle/action")
async def vehicle_action(data: VehicleAction):
    logger.info("Action received | vehicle_id=%s action=%s", data.vehicle_id, data.action)

    return {"status": "ok"}

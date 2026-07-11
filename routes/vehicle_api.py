import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from config.redis_db import get_redis
from routes.models.login_request_model import LoginRequest
from services.mqtt_service import central_mqtt
from services.validation_service import validate_vehicle


@asynccontextmanager
async def lifespan(app: FastAPI):
    central_mqtt.start()

    yield


app = FastAPI(lifespan=lifespan)


@app.post("/login")
async def login(data: LoginRequest):
    is_valid, error = validate_vehicle(data.vin_number, data.jwt)

    if not is_valid:
        raise HTTPException(status_code=401, detail=error)

    active_vehicle_id = data.vehicle_id
    redis_client = get_redis()

    redis_client.set(
        f"vehicle:auth:{data.vin_number}",
        json.dumps({
            "status": "authenticated",
            "vehicle_id": data.vehicle_id,
        }),
    )

    redis_client.set(f"vehicle:map:{data.vehicle_id}", data.vin_number, ex=3600)

    print(f"Authenticated {active_vehicle_id}")

    return {"status": "success", "message": "Authenticated", "vehicle_id": active_vehicle_id}

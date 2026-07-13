import json
import os
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from livekit import api

from config.redis_db import get_redis
from routes.models.login_request_model import LoginRequest
from routes.models.token_request_model import TokenRequest
from services.mqtt_service import central_mqtt
from services.validation_service import validate_vehicle


@asynccontextmanager
async def lifespan(app: FastAPI):
    central_mqtt.start()
    yield


app = FastAPI(lifespan=lifespan)


@app.post("/login")
async def login(data: LoginRequest):
    is_valid, error = validate_vehicle(data.vin_number)

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


@app.post("/getToken")
async def get_token(request: TokenRequest):
    redis_client = get_redis()
    mapped_vin = redis_client.get(f"vehicle:map:{request.car_id}")
    if not mapped_vin:
        raise HTTPException(
            status_code=401,
            detail=f"Vehicle '{request.car_id}' has not authenticated. The embedded device must call POST /login first.",
        )

    api_key = os.getenv("LIVEKIT_API_KEY")
    api_secret = os.getenv("LIVEKIT_API_SECRET")
    server_url = os.getenv("LIVEKIT_URL")

    if not all([api_key, api_secret, server_url]):
        raise HTTPException(
            status_code=500, detail="LiveKit credentials are not configured on the server."
        )

    room_name = f"car-{request.car_id}-{uuid.uuid4()}"
    participant_identity = f"car-{request.car_id}"
    participant_name = f"Car {request.car_id}"

    metadata_json = json.dumps({"car_id": request.car_id, "locale": request.locale})
    room_config = api.RoomConfiguration(
        agents=[api.RoomAgentDispatch(agent_name="yaquod", metadata=metadata_json)],
        departure_timeout=300,
    )

    token = (
        api
        .AccessToken(api_key, api_secret)
        .with_identity(participant_identity)
        .with_name(participant_name)
        .with_grants(api.VideoGrants(room_join=True, room=room_name))
        .with_room_config(room_config)
        .to_jwt()
    )

    return {"server_url": server_url, "participant_token": token}

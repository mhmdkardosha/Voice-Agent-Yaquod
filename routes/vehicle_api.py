import logging
import os
import secrets
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect

from routes.models.navigation_models import CancelDestination, ChangeDestination
from routes.models.vehicle_action_model import VehicleAction, VehicleLocation
from utils.redis_pubsub import (
    publish,
    shutdown_redis,
    startup_redis,
)

load_dotenv()

logger = logging.getLogger("yaquod-api")

API_KEY = os.getenv("YAQUOD_API_KEY")

if not API_KEY:
    raise RuntimeError("YAQUOD_API_KEY environment variable is not set.")

REDIS_URL = os.getenv("REDIS_URL")
if not REDIS_URL:
    raise RuntimeError("REDIS_URL environment variable is not set. ")

# Default test location (Cairo, Egypt) - replace with real GPS in production
_DEFAULT_LOCATION = VehicleLocation(vehicle_id="vehicle_001", lat=30.0444, lng=31.2357)


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connection established: {websocket.client}")

    async def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def local_broadcast(self, message: dict):
        if not self.active_connections:
            return
        disconnected_clients = []

        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except (WebSocketDisconnect, RuntimeError, ConnectionError):
                disconnected_clients.append(connection)

        for connection in disconnected_clients:
            await self.disconnect(connection)


manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await startup_redis(REDIS_URL, manager)

    yield

    await shutdown_redis()


app = FastAPI(lifespan=lifespan)


def verify_api_key(api_key: str = Header(..., alias="API-Key")) -> None:
    if not secrets.compare_digest(api_key, API_KEY):
        logger.warning("Unauthorized HTTP request.")
        raise HTTPException(
            status_code=401,
            detail="Invalid API key",
        )


@app.websocket("/ws/vehicle/events")
async def vehicle_events(websocket: WebSocket):
    token = websocket.headers.get("api-key")

    if not token or not secrets.compare_digest(token, API_KEY):
        logger.warning(
            "Rejected WebSocket connection from %s",
            websocket.client,
        )
        await websocket.close(code=1008)
        return

    await manager.connect(websocket)

    try:
        while True:
            await websocket.receive_text()  # Keep the connection open
    except WebSocketDisconnect:
        await manager.disconnect(websocket)


@app.get("/vehicle/location", dependencies=[Depends(verify_api_key)])
async def get_vehicle_location() -> VehicleLocation:
    return _DEFAULT_LOCATION


@app.post("/vehicle/action", dependencies=[Depends(verify_api_key)])
async def vehicle_action(data: VehicleAction):
    logger.info(f"Action received | vehicle_id={data.vehicle_id} action={data.action}")

    await publish("vehicle_action", data)

    return {"status": "success", "message": "Vehicle action broadcasted."}


@app.post("/vehicle/navigation/change", dependencies=[Depends(verify_api_key)])
async def change_destination(data: ChangeDestination):
    logger.info(
        f"Navigation request | vehicle_id={data.vehicle_id} destination={data.destination} latitude={data.latitude} longitude={data.longitude}"
    )

    await publish("navigation_change", data)

    return {
        "success": True,
        "message": f"Navigation started to {data.destination}.",
    }


@app.post("/vehicle/navigation/cancel", dependencies=[Depends(verify_api_key)])
async def cancel_destination(data: CancelDestination):
    logger.info(f"Navigation cancelled | vehicle_id={data.vehicle_id}")

    await publish("navigation_cancel", data)

    return {
        "success": True,
        "message": "Navigation cancelled.",
    }

import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from routes.models.navigation_models import CancelDestination, ChangeDestination
from routes.models.vehicle_action_model import VehicleAction, VehicleLocation

app = FastAPI()

logger = logging.getLogger("yaquod-api")

# Default test location (Cairo, Egypt) - replace with real GPS in production
_DEFAULT_LOCATION = VehicleLocation(vehicle_id="vehicle_001", lat=30.0444, lng=31.2357)


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket connection established: {websocket.client}")
    
    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket connection closed: {websocket.client}")
    
    async def broadcast(self, message: dict):
        disconnected_clients = []

        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except WebSocketDisconnect:
                disconnected_clients.append(connection)
                logger.warning(f"WebSocket client disconnected: {connection.client}")
        
        for connection in disconnected_clients:
            self.disconnect(connection)

manager = ConnectionManager()

@app.websocket("/ws/vehicle/events")
async def vehicle_events(websocket: WebSocket):
    await manager.connect(websocket)

    try:
        while True:
            await websocket.receive_text()  # Keep the connection open
    except WebSocketDisconnect:
        manager.disconnect(websocket)

@app.get("/vehicle/location")
async def get_vehicle_location() -> VehicleLocation:
    return _DEFAULT_LOCATION

@app.post("/vehicle/action")
async def vehicle_action(data: VehicleAction):
    logger.info(f"Action received | vehicle_id={data.vehicle_id} action={data.action}")

    await manager.broadcast(
        {
            "event": "vehicle_action",
            "data": data.model_dump(),
        }
    )
    return {"status": "success", "message": "Vehicle action broadcasted."}

@app.post("/vehicle/navigation/change")
async def change_destination(data: ChangeDestination):
    logger.info(
        f"Navigation request | vehicle_id={data.vehicle_id} destination={data.destination} latitude={data.latitude} longitude={data.longitude}"
    )

    await manager.broadcast(
        {
            "event": "navigation_change",
            "data": data.model_dump(),
        }
    )

    return {
        "success": True,
        "message": f"Navigation started to {data.destination}.",
    }

@app.post("/vehicle/navigation/cancel")
async def cancel_destination(data: CancelDestination):
    logger.info(f"Navigation cancelled | vehicle_id={data.vehicle_id}")

    await manager.broadcast(
        {
            "event": "navigation_cancel",
            "data": data.model_dump(),
        }
    )

    return {
        "success": True,
        "message": "Navigation cancelled.",
    }

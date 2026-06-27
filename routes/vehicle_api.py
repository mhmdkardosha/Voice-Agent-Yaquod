from fastapi import FastAPI

from routes.models.vehicle_action_model import VehicleAction

app = FastAPI()


@app.post("/api/vehicle/action")
async def vehicle_action(data: VehicleAction):
    print("ACTION RECEIVED:")
    print(data.model_dump_json(indent=2))

    return {"status": "ok"}

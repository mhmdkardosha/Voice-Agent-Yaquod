import jwt
import datetime
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

app = FastAPI()

STATIC_EXPECTED_VIN = "VIN_12345"
STATIC_EXPECTED_JWT = "JWT_SECRET_TOKEN"

class LoginRequest(BaseModel):
    vehicle_id: str
    vin_number: str
    jwt: str

def validate_vin_static(vin: str) -> bool:
    return vin == STATIC_EXPECTED_VIN

def validate_jwt_static(token: str) -> bool:
    return token == STATIC_EXPECTED_JWT


@app.post("/login")
async def login(data: LoginRequest):
    if not validate_vin_static(data.vin_number):
        raise HTTPException(status_code=401, detail="Invalid VIN Number")
    
    if not validate_jwt_static(data.jwt):
        raise HTTPException(status_code=401, detail="Invalid JWT Token")
    
    active_vehicle_id = data.vehicle_id
    
    print(f"Authenticated {active_vehicle_id}")
    
    return {
        "status": "success",
        "message": "Authenticated",
        "vehicle_id": active_vehicle_id
    }
    
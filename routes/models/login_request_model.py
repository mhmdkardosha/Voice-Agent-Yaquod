from pydantic import BaseModel


class LoginRequest(BaseModel):
    vehicle_id: str
    vin_number: str
    jwt: str

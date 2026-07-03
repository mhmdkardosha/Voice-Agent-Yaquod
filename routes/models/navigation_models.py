from pydantic import BaseModel


class ChangeDestination(BaseModel):
    vehicle_id: str
    destination: str
    latitude: float
    longitude: float


class CancelDestination(BaseModel):
    vehicle_id: str

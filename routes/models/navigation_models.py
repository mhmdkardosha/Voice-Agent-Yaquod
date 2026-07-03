from pydantic import BaseModel, Field


class ChangeDestination(BaseModel):
    vehicle_id: str
    destination: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class CancelDestination(BaseModel):
    vehicle_id: str

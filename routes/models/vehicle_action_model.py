from pydantic import BaseModel, field_validator
from config.constants import ALLOWED_ACTIONS


class VehicleAction(BaseModel):
    vehicle_id: str
    action: str
    parameters: dict

    @field_validator("action")
    @classmethod
    def action_must_be_allowed(cls, v: str) -> str:
        if v not in ALLOWED_ACTIONS:
            raise ValueError(f"Action '{v}' is not allowed")
        return v


class VehicleLocation(BaseModel):
    vehicle_id: str
    lat: float
    lng: float

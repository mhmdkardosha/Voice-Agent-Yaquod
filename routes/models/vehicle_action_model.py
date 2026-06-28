from pydantic import BaseModel, field_validator

ALLOWED_ACTIONS = {
    "ac_on",
    "ac_off",
    "set_level",
    "window_open",
    "window_close",
    "music_play",
    "music_pause",
    "set_volume",
    "next_track",
    "previous_track",
    "reading_light_on",
    "reading_light_off",
    "change_destination",
    "cancel_destination",
    "safe_stop",
}


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

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class VehicleData(BaseModel):
    # extra fields
    model_config = ConfigDict(extra="allow")

    # vehivle basic inforamtion
    vehicle_id: str = Field(..., description="The unique identifier of the vehicle")
    vin_number: str = Field(..., description="The Vehicle Identification Number (Mandatory)")
    timestamp: int | None = Field(None, description="Epoch timestamp when the data was generated")
    vehicle_model: str | None = Field(None, description="Model of the vehicle")
    vehicle_color: str | None = Field(None, description="Color of the vehicle")
    plate_num: str | None = Field(None, description="License plate number")
    number_of_seats: int | None = Field(None, ge=0, description="Number of available seats")
    battery_level: int | None = Field(None, ge=0, le=100, description="Battery percentage (0-100)")

    # vehivle trip inforamtion
    lat: float | None = Field(None, description="Real-time latitude location")
    long: float | None = Field(None, description="Real-time longitude location")
    remaining_time: float | None = Field(None, ge=0, description="Remaining travel time")
    remaining_distance: float | None = Field(None, ge=0, description="Remaining distance")
    speed: float | None = Field(None, ge=0, description="Current speed of the vehicle")
    pickup_point_name: str | None = Field(None, description="Name of the starting or pickup point")
    destination_name: str | None = Field(None, description="Name of the final destination")
    expected_trip_duration: float | None = Field(
        None, ge=0, description="Expected trip duration in minutes"
    )

    # vehivle action inforamtion
    ac_status: str | None = Field(None, description="AC status")
    ac_temperature: float | None = Field(None, description="AC temperature")
    ac_fan_speed: int | None = Field(None, ge=0, le=5, description="AC fan speed")
    ac_airflow_mode: str | None = Field(None, description="AC airflow mode")
    ac_auto: bool | None = Field(None, description="AC auto mode")
    ac_sync: bool | None = Field(None, description="AC sync mode")
    window_status: dict[str, Any] | None = Field(None, description="Window status")
    window_lock_status: bool | None = Field(None, description="Window lock status")
    music_status: bool | None = Field(None, description="Music status")
    music_volume: int | None = Field(None, ge=0, le=100, description="Music volume")
    reading_light_status: dict[str, Any] | None = Field(None, description="Reading light status")
    seat_status: dict[str, Any] | None = Field(None, description="Seat status")

    @property
    def extra_data(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if k not in self.model_fields}

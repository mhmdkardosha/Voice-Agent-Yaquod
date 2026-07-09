from pydantic import BaseModel, Field, ConfigDict
from typing import Any, Dict, Optional

class VehicleData(BaseModel):
    #extra fields
    model_config = ConfigDict(extra='allow')

    #vehivle basic inforamtion
    vehicle_id: str = Field(..., description="The unique identifier of the vehicle")
    vin_number: str = Field(..., description="The Vehicle Identification Number (Mandatory)")
    timestamp: Optional[int] = Field(None, description="Epoch timestamp when the data was generated")
    vehicle_model: Optional[str] = Field(None, description="Model of the vehicle")
    vehicle_color: Optional[str] = Field(None, description="Color of the vehicle")
    plate_num: Optional[str] = Field(None, description="License plate number")
    number_of_seats: Optional[int] = Field(None, ge=0, description="Number of available seats")
    battery_level: Optional[int] = Field(None, ge=0, le=100, description="Battery percentage (0-100)")
    
    #vehivle trip inforamtion
    lat: Optional[float] = Field(None, description="Real-time latitude location")
    long: Optional[float] = Field(None, description="Real-time longitude location")
    remaining_time: Optional[float] = Field(None, ge=0, description="Remaining travel time")
    remaining_distance: Optional[float] = Field(None, ge=0, description="Remaining distance")
    speed: Optional[float] = Field(None, ge=0, description="Current speed of the vehicle")
    pickup_point_name: Optional[str] = Field(None, description="Name of the starting or pickup point")
    destination_name: Optional[str] = Field(None, description="Name of the final destination")
    expected_trip_duration: Optional[float] = Field(None, ge=0, description="Expected trip duration in minutes")

    #vehivle action inforamtion
    ac_status: Optional[str] = Field(None, description="AC status")
    ac_temperature: Optional[float] = Field(None, description="AC temperature")
    ac_fan_speed: Optional[int] = Field(None, ge=0, le=5, description="AC fan speed")
    ac_airflow_mode: Optional[str] = Field(None, description="AC airflow mode")
    ac_auto: Optional[bool] = Field(None, description="AC auto mode")
    ac_sync: Optional[bool] = Field(None, description="AC sync mode")
    window_status: Optional[Dict[str, Any]] = Field(None, description="Window status")
    window_lock_status: Optional[bool] = Field(None, description="Window lock status")
    music_status: Optional[bool] = Field(None, description="Music status")
    music_volume: Optional[int] = Field(None, ge=0, le=100, description="Music volume")
    reading_light_status: Optional[Dict[str, Any]] = Field(None, description="Reading light status")
    seat_status: Optional[Dict[str, Any]] = Field(None, description="Seat status")
    
    @property
    def extra_data(self) -> Dict[str, Any]:
        return {
            k: v for k, v in self.__dict__.items() 
            if k not in self.model_fields
        }
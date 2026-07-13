from pydantic import BaseModel, Field


class TokenRequest(BaseModel):
    car_id: str = Field(min_length=1)
    locale: str = "ar"

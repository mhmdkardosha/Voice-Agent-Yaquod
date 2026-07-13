from pydantic import BaseModel


class TokenRequest(BaseModel):
    car_id: str
    locale: str = "ar"

from fastapi.testclient import TestClient

from routes.vehicle_api import _DEFAULT_LOCATION, app

import os
from unittest.mock import AsyncMock, patch

HEADERS = {
    "API-Key": os.environ["YAQUOD_API_KEY"],
}

client = TestClient(app)


def test_valid_action_without_params():
    with patch("routes.vehicle_api.publish", new=AsyncMock()):
        resp = client.post(
            "/vehicle/action",
            headers=HEADERS,
            json={
                "vehicle_id": "vehicle_001",
                "action": "ac_on",
                "parameters": {},
            },
        )

    assert resp.status_code == 200
    assert resp.json() == {
        "status": "success",
        "message": "Vehicle action broadcasted.",
    }


def test_valid_action_with_params():
    with patch("routes.vehicle_api.publish", new=AsyncMock()):
        resp = client.post(
            "/vehicle/action",
            headers=HEADERS,
            json={
                "vehicle_id": "vehicle_001",
                "action": "set_fan_speed",
                "parameters": {"speed": 3},
            },
        )
    assert resp.status_code == 200
    assert resp.json() == {
        "status": "success",
        "message": "Vehicle action broadcasted.",
    }


def test_missing_vehicle_id():
    resp = client.post(
        "/vehicle/action",
        headers=HEADERS,
        json={"action": "ac_on", "parameters": {}},
    )
    assert resp.status_code == 422


def test_missing_action():
    resp = client.post(
        "/vehicle/action",
        headers=HEADERS,
        json={"vehicle_id": "vehicle_001", "parameters": {}},
    )
    assert resp.status_code == 422


def test_vehicle_location_returns_coordinates():
    resp = client.get("/vehicle/location", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "vehicle_id" in data
    assert "lat" in data
    assert "lng" in data
    assert isinstance(data["lat"], float)
    assert isinstance(data["lng"], float)


def test_vehicle_location_default_values():
    resp = client.get("/vehicle/location", headers=HEADERS)
    data = resp.json()
    assert data == _DEFAULT_LOCATION.model_dump()


def test_invalid_action_is_rejected():
    resp = client.post(
        "/vehicle/action",
        headers=HEADERS,
        json={"vehicle_id": "vehicle_001", "action": "accelerate", "parameters": {}},
    )
    assert resp.status_code == 422

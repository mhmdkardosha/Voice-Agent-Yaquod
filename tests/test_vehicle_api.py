from fastapi.testclient import TestClient

from routes.vehicle_api import _DEFAULT_LOCATION, app

client = TestClient(app)


def test_valid_action_without_params():
    resp = client.post(
        "/api/vehicle/action",
        json={"vehicle_id": "vehicle_001", "action": "ac_on", "parameters": {}},
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_valid_action_with_params():
    resp = client.post(
        "/api/vehicle/action",
        json={
            "vehicle_id": "vehicle_001",
            "action": "set_level",
            "parameters": {"level": 3},
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_missing_vehicle_id():
    resp = client.post(
        "/api/vehicle/action",
        json={"action": "ac_on", "parameters": {}},
    )
    assert resp.status_code == 422


def test_missing_action():
    resp = client.post(
        "/api/vehicle/action",
        json={"vehicle_id": "vehicle_001", "parameters": {}},
    )
    assert resp.status_code == 422


def test_vehicle_location_returns_coordinates():
    resp = client.get("/api/vehicle/location")
    assert resp.status_code == 200
    data = resp.json()
    assert "vehicle_id" in data
    assert "lat" in data
    assert "lng" in data
    assert isinstance(data["lat"], float)
    assert isinstance(data["lng"], float)


def test_vehicle_location_default_values():
    resp = client.get("/api/vehicle/location")
    data = resp.json()
    assert data == _DEFAULT_LOCATION.model_dump()


def test_invalid_action_is_rejected():
    resp = client.post(
        "/api/vehicle/action",
        json={"vehicle_id": "vehicle_001", "action": "accelerate", "parameters": {}},
    )
    assert resp.status_code == 422

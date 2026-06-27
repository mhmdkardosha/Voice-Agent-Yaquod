from fastapi.testclient import TestClient

from routes.vehicle_api import app

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


def test_extra_fields_ignored():
    resp = client.post(
        "/api/vehicle/action",
        json={
            "vehicle_id": "vehicle_001",
            "action": "ac_on",
            "parameters": {},
            "extra": "ignored",
        },
    )
    assert resp.status_code == 200

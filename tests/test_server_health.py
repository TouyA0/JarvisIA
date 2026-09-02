"""Fumée sur le routeur FastAPI : /api/health doit répondre sans auth, et
toute autre route /api/* doit être bloquée sans bearer token dès qu'un
CONSOLE_PASSWORD est configuré (voir server.py::_require_console_auth)."""
from fastapi.testclient import TestClient

from brain import config


def test_health_is_reachable_without_auth():
    from brain.server import app

    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200


def test_protected_route_rejects_missing_bearer_token(monkeypatch):
    from brain.server import app

    monkeypatch.setattr(config, "CONSOLE_PASSWORD", "test-password")
    client = TestClient(app)
    resp = client.get("/api/devices")
    assert resp.status_code == 401


def test_protected_route_accepts_correct_bearer_token(monkeypatch):
    from brain.server import app

    monkeypatch.setattr(config, "CONSOLE_PASSWORD", "test-password")
    client = TestClient(app)
    resp = client.get("/api/devices", headers={"Authorization": "Bearer test-password"})
    assert resp.status_code == 200

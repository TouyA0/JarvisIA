"""Fumée sur le routeur FastAPI : /api/health doit répondre sans auth, et
toute autre route /api/* doit être bloquée sans bearer token dès qu'un
CONSOLE_PASSWORD est configuré (voir server.py::_require_console_auth).

Depuis P4, le bearer attendu est un jeton de session émis par POST
/api/session — plus jamais CONSOLE_PASSWORD lui-même (voir
session_tokens.py)."""
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


def test_protected_route_rejects_raw_password_as_bearer(monkeypatch):
    """Le mot de passe lui-même n'est plus un jeton d'API valide — seul un
    jeton de session émis par /api/session l'est (P4)."""
    from brain.server import app

    monkeypatch.setattr(config, "CONSOLE_PASSWORD", "test-password")
    client = TestClient(app)
    resp = client.get("/api/devices", headers={"Authorization": "Bearer test-password"})
    assert resp.status_code == 401


def test_session_endpoint_rejects_wrong_password(monkeypatch):
    from brain.server import app

    monkeypatch.setattr(config, "CONSOLE_PASSWORD", "test-password")
    client = TestClient(app)
    resp = client.post("/api/session", json={"password": "wrong"})
    assert resp.status_code == 401


def test_protected_route_accepts_session_token_from_correct_password(monkeypatch):
    from brain.server import app

    monkeypatch.setattr(config, "CONSOLE_PASSWORD", "test-password")
    client = TestClient(app)
    session_resp = client.post("/api/session", json={"password": "test-password"})
    assert session_resp.status_code == 200
    token = session_resp.json()["token"]

    resp = client.get("/api/devices", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200

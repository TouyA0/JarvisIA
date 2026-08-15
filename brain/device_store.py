"""Registre persistant des appareils appairés (data/devices.json).

À distinguer de `brain/devices.py` (`DeviceRegistry`) : ici c'est la
confiance long terme (qui a le droit de se connecter, avec quel token) ;
là-bas c'est l'état des connexions WebSocket actuellement ouvertes. Un
appareil peut être connu ici et hors ligne (pas dans `DeviceRegistry`).
"""
from __future__ import annotations

import json
import threading
import time

from brain import config

_lock = threading.Lock()


def _load() -> dict:
    if config.DEVICES_FILE.exists():
        with open(config.DEVICES_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"devices": {}}


def _save(data: dict) -> None:
    with open(config.DEVICES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def find_by_token(token: str) -> dict | None:
    """Un appareil déjà appairé, identifié par son token définitif."""
    with _lock:
        data = _load()
    for device_id, entry in data["devices"].items():
        if entry.get("token") == token:
            return {"device_id": device_id, **entry}
    return None


def register(device_id: str, name: str, device_type: str, token: str) -> None:
    """Enregistre un appareil fraîchement appairé (ou met à jour son nom)."""
    with _lock:
        data = _load()
        data["devices"][device_id] = {
            "name": name,
            "device_type": device_type,
            "token": token,
            "paired_at": data["devices"].get(device_id, {}).get("paired_at", time.time()),
        }
        _save(data)


def list_known() -> list[dict]:
    with _lock:
        data = _load()
    return [{"device_id": k, **v} for k, v in data["devices"].items()]


def forget(device_id: str) -> bool:
    """Révoque un appareil — il devra être ré-appairé pour se reconnecter."""
    with _lock:
        data = _load()
        if device_id not in data["devices"]:
            return False
        del data["devices"][device_id]
        _save(data)
        return True

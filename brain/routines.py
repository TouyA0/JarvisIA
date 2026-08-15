"""Routines cross-appareils : séquences d'actions dispatchées sur
plusieurs appareils via brain/devices.py.

Déclenchement manuel uniquement pour l'instant (bouton « Lancer » côté
web) — pas de déclencheur automatique (horaire, vocal) : ça n'a nulle
part où s'accrocher aujourd'hui (pas de scheduler, la voix ne connaît
pas encore les routines cross-device). Voir docs/ROADMAP_MULTIDEVICE.md.

À ne pas confondre avec agents/desktop/services/routines.py : format et
fichier différents, celui-ci vit côté brain et cible plusieurs appareils.
"""
from __future__ import annotations

import json
import threading
import uuid

from brain import activity, config
from brain.devices import registry

_lock = threading.Lock()
_running: dict[str, dict] = {}  # routine_id -> état d'exécution en cours


def _load() -> dict:
    if config.CROSS_DEVICE_ROUTINES_FILE.exists():
        with open(config.CROSS_DEVICE_ROUTINES_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"routines": []}


def _save(data: dict) -> None:
    with open(config.CROSS_DEVICE_ROUTINES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def list_routines() -> list[dict]:
    data = _load()
    for r in data["routines"]:
        r["run_status"] = _running.get(r["id"])
    return data["routines"]


def create(name: str, steps: list[dict]) -> dict:
    routine = {"id": uuid.uuid4().hex, "name": name, "steps": steps}
    with _lock:
        data = _load()
        data["routines"].append(routine)
        _save(data)
    return routine


def delete(routine_id: str) -> bool:
    with _lock:
        data = _load()
        before = len(data["routines"])
        data["routines"] = [r for r in data["routines"] if r["id"] != routine_id]
        _save(data)
    _running.pop(routine_id, None)
    return len(data["routines"]) < before


def _find(routine_id: str) -> dict | None:
    return next((r for r in _load()["routines"] if r["id"] == routine_id), None)


def exists(routine_id: str) -> bool:
    return _find(routine_id) is not None


async def run(routine_id: str) -> None:
    """Exécute chaque étape dans l'ordre, s'arrête à la première erreur.

    L'état (`_running`) reste consultable après la fin (« done »/« error »)
    pour que le polling front ait le temps de l'afficher — jamais nettoyé
    automatiquement, un nouveau `run()` du même id l'écrase simplement.
    """
    routine = _find(routine_id)
    if not routine:
        raise KeyError(routine_id)

    steps = routine["steps"]
    _running[routine_id] = {"step_index": 0, "total": len(steps), "status": "running", "error": None}

    for i, step in enumerate(steps):
        _running[routine_id]["step_index"] = i
        device_id, tool, args = step["device_id"], step["tool"], step.get("args", {})
        try:
            result = await registry.dispatch(device_id, tool, args)
        except KeyError:
            activity.record(device_id, tool, ok=False, error="appareil non connecté")
            _running[routine_id].update(status="error", error=f"{device_id} non connecté")
            return
        except TimeoutError:
            activity.record(device_id, tool, ok=False, error="timeout")
            _running[routine_id].update(status="error", error=f"{device_id} n'a pas répondu")
            return

        activity.record(device_id, tool, ok=result.ok, error=result.error)
        if not result.ok:
            _running[routine_id].update(status="error", error=result.error)
            return

    _running[routine_id]["status"] = "done"


def status(routine_id: str) -> dict | None:
    return _running.get(routine_id)

"""Routines cross-appareils : séquences d'actions dispatchées sur
plusieurs appareils via brain/devices.py.

Déclenchement manuel (bouton « Lancer » côté web) ou programmé (C4,
`schedule`) — un déclencheur horaire optionnel par routine, vérifié par
`scheduler_loop()` ci-dessous. Le déclenchement événementiel (« quand
j'arrive ») reste hors de portée : rien dans ce projet ne détecte encore
de présence (pas de géofencing, pas de scan réseau) — un déclencheur ne
peut s'accrocher qu'à un signal qui existe déjà. Voir
docs/ROADMAP_MULTIDEVICE.md.

À ne pas confondre avec agents/desktop/services/routines.py : format et
fichier différents, celui-ci vit côté brain et cible plusieurs appareils.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid

from brain import activity, config
from brain.devices import registry

_lock = threading.Lock()
_running: dict[str, dict] = {}  # routine_id -> état d'exécution en cours

# ── Déclenchement programmé (C4) ─────────────────────────────────────────────
_SCHEDULE_CHECK_S = 30
_scheduler_started = False


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


def create(name: str, steps: list[dict], schedule: dict | None = None) -> dict:
    routine = {"id": uuid.uuid4().hex, "name": name, "steps": steps}
    if schedule:
        routine["schedule"] = schedule
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


def set_schedule(routine_id: str, schedule: dict | None) -> dict:
    """`schedule` : {"time": "HH:MM", "days": [0-6] (0 = lundi), optionnel
    — absent/vide = tous les jours} ou None pour repasser en manuel."""
    with _lock:
        data = _load()
        routine = next((r for r in data["routines"] if r["id"] == routine_id), None)
        if not routine:
            raise KeyError(routine_id)
        if schedule:
            routine["schedule"] = schedule
        else:
            routine.pop("schedule", None)
        _save(data)
        return routine


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


def _due(now: time.struct_time, today: str, last_fired: dict[str, str]) -> list[str]:
    hm = f"{now.tm_hour:02d}:{now.tm_min:02d}"
    due = []
    for r in _load()["routines"]:
        sched = r.get("schedule")
        if not sched or sched.get("time") != hm:
            continue
        days = sched.get("days")
        if days and now.tm_wday not in days:
            continue
        if last_fired.get(r["id"]) == today:
            continue
        due.append(r["id"])
    return due


async def scheduler_loop() -> None:
    """Vérifie toutes les `_SCHEDULE_CHECK_S` secondes si une routine
    programmée doit se déclencher (C4). `last_fired` est en mémoire, pas
    persisté : un redémarrage du brain pile dans la minute cible resterait
    silencieux cette fois-là — négligeable face à la complexité d'un état
    disque de plus pour un cas aussi rare."""
    last_fired: dict[str, str] = {}
    while True:
        await asyncio.sleep(_SCHEDULE_CHECK_S)
        now = time.localtime()
        today = time.strftime("%Y-%m-%d", now)
        for routine_id in _due(now, today, last_fired):
            last_fired[routine_id] = today
            try:
                await run(routine_id)
            except Exception as exc:
                print(f"[brain][routines] déclenchement programmé de {routine_id!r} : {exc}")


def start_scheduler() -> None:
    """À appeler depuis un contexte asyncio déjà démarré (voir
    server.py::_on_startup) — scheduler_loop() a besoin de la boucle
    d'événements pour `await run()`, contrairement à timers.start()/
    proactive.start() qui n'utilisent que des threads classiques."""
    global _scheduler_started
    if _scheduler_started:
        return
    _scheduler_started = True
    asyncio.create_task(scheduler_loop())

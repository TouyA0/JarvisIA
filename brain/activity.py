"""Journal d'activité par appareil — en mémoire uniquement, borné.

Alimenté par chaque dispatch de commande (voir brain/server.py). Pas de
persistance : un redémarrage du brain vide le journal, ce qui est
suffisant pour un écran de diagnostic (Focus appareil), pas pour un
historique durable.
"""
from __future__ import annotations

import threading
import time

_MAX_ENTRIES = 30
_lock = threading.Lock()
_log: dict[str, list[dict]] = {}


def record(device_id: str, tool: str, ok: bool, error: str | None = None) -> None:
    with _lock:
        entries = _log.setdefault(device_id, [])
        entries.append({"ts": time.time(), "tool": tool, "ok": ok, "error": error})
        del entries[:-_MAX_ENTRIES]


def for_device(device_id: str) -> list[dict]:
    with _lock:
        return list(reversed(_log.get(device_id, [])))

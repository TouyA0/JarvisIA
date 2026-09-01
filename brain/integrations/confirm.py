"""Confirmation humaine pour les actions d'écriture des intégrations
(Drive create/update/trash, et tout ce qui suivra sur le même modèle).

Miroir voulu de agents/desktop/tools/system.py::_confirm_destructive (bulle
Qt bloquante côté desktop) — mais le brain n'a pas d'interface graphique et
peut tourner sans aucun agent desktop connecté (Console web seule). La
confirmation transite donc par un endpoint REST que la Console affiche en
bannière (voir web/src/components/ConfirmationBanner.jsx), et request()
bloque le thread appelant jusqu'à la décision ou l'expiration — exactement
le même contrat (refus par défaut au timeout) que côté desktop, juste avec
un support différent.

Toujours appelé depuis un thread (brain_tools.execute tourne dans
asyncio.to_thread, voir brain/core/agent.py) : bloquer ici ne gèle jamais
la boucle événementielle FastAPI, donc l'endpoint de résolution reste
joignable pendant l'attente.
"""
from __future__ import annotations

import threading
import time
import uuid

_lock = threading.Lock()
_pending: dict[str, dict] = {}  # id -> {id, summary, created_at, event, approved}

_DEFAULT_TIMEOUT = 90


def request(summary: str, timeout: float = _DEFAULT_TIMEOUT) -> bool:
    """Bloque jusqu'à la décision de Monsieur depuis la Console, ou expire
    (refus par défaut). `summary` doit décrire précisément l'action (quoi,
    où) — c'est le seul texte que Monsieur voit avant de trancher, une
    confirmation éclairée en dépend."""
    confirmation_id = uuid.uuid4().hex
    event = threading.Event()
    with _lock:
        _pending[confirmation_id] = {
            "id": confirmation_id, "summary": summary, "created_at": time.time(),
            "event": event, "approved": None,
        }
    got_response = event.wait(timeout)
    with _lock:
        entry = _pending.pop(confirmation_id, None)
    return bool(got_response and entry and entry["approved"])


def list_pending() -> list[dict]:
    with _lock:
        return [
            {"id": e["id"], "summary": e["summary"], "created_at": e["created_at"]}
            for e in _pending.values()
        ]


def resolve(confirmation_id: str, approved: bool) -> bool:
    """True si une confirmation en attente correspondait à cet id (et pas
    déjà expirée) — False sinon, la Console doit alors dire que c'est trop
    tard plutôt que prétendre avoir agi."""
    with _lock:
        entry = _pending.get(confirmation_id)
        if not entry:
            return False
        entry["approved"] = approved
        entry["event"].set()
    return True

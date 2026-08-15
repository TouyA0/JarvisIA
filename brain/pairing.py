"""Codes d'appairage éphémères — en mémoire uniquement, jamais persistés.

Un code sert une seule fois puis expire (usage OU délai, le premier des
deux). Format « XXX-XXX » pour coller au design (`docs/site web
design/Jarvis.dc.html`, écran Centre d'appareils).
"""
from __future__ import annotations

import secrets
import string
import threading
import time

_lock = threading.Lock()
_pending: dict[str, float] = {}  # code -> expiration (epoch)

_ALPHABET = string.ascii_uppercase + string.digits
_TTL_SECONDS = 5 * 60


def _generate() -> str:
    part = lambda: "".join(secrets.choice(_ALPHABET) for _ in range(3))
    return f"{part()}-{part()}"


def create_code() -> str:
    with _lock:
        _expire_stale()
        code = _generate()
        while code in _pending:
            code = _generate()
        _pending[code] = time.time() + _TTL_SECONDS
        return code


def consume(code: str) -> bool:
    """True si le code était valide et non expiré — il ne peut plus resservir."""
    with _lock:
        expires_at = _pending.pop(code, None)
    return expires_at is not None and expires_at > time.time()


def _expire_stale() -> None:
    now = time.time()
    for code in [c for c, exp in _pending.items() if exp <= now]:
        del _pending[code]

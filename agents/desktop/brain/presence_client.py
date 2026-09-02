"""Signale au brain que ce PC vient de prendre la parole (mot d'éveil
entendu, ou commande tapée) — permet d'arbitrer qui joue l'audio de
synthèse quand ce PC et une Console web armée (téléphone compris, voir
Phase 9) sont actifs en même temps sur la même conversation partagée
(voir brain/presence.py).

Désactivé si BRAIN_ENABLED=0 (comportement inchangé, comme remote_chat.py
et agent_client.py) et toujours best-effort : un brain injoignable ne
doit jamais bloquer ni casser la boucle vocale, juste laisser Jarvis
parler comme si de rien n'était (fail-open).
"""
from __future__ import annotations

import threading

import requests

from agents.desktop import config

DEVICE_ID = "pc"
_LABEL = "PC fixe"
_TIMEOUT = 1.5


def _http_base() -> str:
    return (
        config.BRAIN_URL
        .replace("wss://", "https://")
        .replace("ws://", "http://")
        .replace("/ws/agent", "")
    )


def _activate_sync() -> None:
    try:
        requests.post(
            f"{_http_base()}/api/presence/activate",
            json={"device": DEVICE_ID, "label": _LABEL},
            timeout=_TIMEOUT,
        )
    except requests.RequestException:
        pass


def activate() -> None:
    """Fire-and-forget : ne doit jamais ralentir la boucle vocale."""
    if not config.BRAIN_ENABLED:
        return
    threading.Thread(target=_activate_sync, daemon=True).start()


def is_active() -> bool:
    """True si ce PC peut jouer sa synthèse vocale — toujours True sans le
    brain (fail-open, comportement inchangé)."""
    if not config.BRAIN_ENABLED:
        return True
    try:
        res = requests.get(f"{_http_base()}/api/presence", timeout=_TIMEOUT)
        if res.ok:
            return res.json().get("device") in (None, DEVICE_ID)
    except requests.RequestException:
        pass
    return True

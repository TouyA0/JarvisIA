"""Présence temps réel — quel appareil « a la main » pour parler à voix haute.

Le PC fixe (mot d'éveil local, TTS via les haut-parleurs du salon) et
n'importe quelle Console web armée (téléphone compris, voir Phase 9)
peuvent tous les deux être en train d'écouter en même temps. Sans
arbitrage, ouvrir Jarvis sur le téléphone pendant que le PC répond encore
ferait parler les deux appareils en même temps sur la même conversation
partagée.

Règle volontairement simple : le dernier appareil à avoir entendu
« Jarvis » (ou reçu une commande tapée) gagne — en mémoire uniquement,
vidé au redémarrage du brain, pas besoin de plus pour un usage personnel
mono-utilisateur. Chaque appareil consulte `is_active()` juste avant de
jouer sa synthèse vocale : celui qui n'est plus actif affiche quand même
le texte, mais reste silencieux.
"""
from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_state: dict = {"device": None, "label": None, "since": 0.0}


def activate(device: str, label: str) -> dict:
    """Marque `device` comme l'appareil qui vient de prendre la parole."""
    with _lock:
        _state["device"] = device
        _state["label"] = label or device
        _state["since"] = time.time()
        return dict(_state)


def get() -> dict:
    with _lock:
        return dict(_state)


def is_active(device: str) -> bool:
    """True si personne d'autre n'a pris la main depuis — avant le tout
    premier `activate()` (aucun appareil connu), tout le monde est actif :
    ne change rien tant que la fonctionnalité n'a jamais été utilisée."""
    with _lock:
        return _state["device"] in (None, device)

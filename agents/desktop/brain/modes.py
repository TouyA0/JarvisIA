"""Modes contextuels (travail, détente, repas, théologie...).

Chaque mode injecte une consigne dans le prompt système et peut être activé
à la voix (« passe en mode travail ») ou depuis le HUD.
"""
from __future__ import annotations

import json
import re
import time

from agents.desktop import config
from agents.desktop.textutil import normalize_text

_modes_cache: dict | None = None
_current_mode_cache: dict | None = None


def load() -> dict:
    global _modes_cache
    if _modes_cache is None:
        if config.MODES_FILE.exists():
            with open(config.MODES_FILE, encoding="utf-8") as f:
                _modes_cache = json.load(f)
        else:
            _modes_cache = {"version": 1, "modes": []}
    return _modes_cache


def get_current() -> dict:
    global _current_mode_cache
    if _current_mode_cache is None:
        if config.CURRENT_MODE_FILE.exists():
            with open(config.CURRENT_MODE_FILE, encoding="utf-8") as f:
                _current_mode_cache = json.load(f)
        else:
            _current_mode_cache = {"mode_id": "normal", "activated_at": None}
    return _current_mode_cache


def set_mode(mode_id: str) -> dict | None:
    global _current_mode_cache
    from agents.desktop.brain import prompts

    modes = load()
    mode = next((m for m in modes["modes"] if m["id"] == mode_id), None)
    if not mode:
        return None
    _current_mode_cache = {"mode_id": mode_id, "activated_at": time.time(), "activated_by": "voice"}
    prompts.invalidate_cache()
    with open(config.CURRENT_MODE_FILE, "w", encoding="utf-8") as f:
        json.dump(_current_mode_cache, f, ensure_ascii=False, indent=2)
    return mode


def get_active_mode_data() -> dict | None:
    """Retourne le dict du mode actif, ou None si mode normal."""
    current = get_current()
    mode_id = current.get("mode_id", "normal")
    if mode_id == "normal":
        return None
    modes = load()
    return next((m for m in modes["modes"] if m["id"] == mode_id), None)


def match_trigger(text: str) -> dict | None:
    """Retourne le mode si le texte EST une commande de changement de mode.

    Match en préfixe et non en sous-chaîne : sinon « qu'est-ce qu'on mange ? »
    déclencherait le Mode Repas au lieu d'obtenir une réponse.
    """
    normalized = normalize_text(text)
    # Tolérer un « jarvis » résiduel en tête de phrase
    normalized = re.sub(rf"^{config.WAKE_WORD}\b[\s,;:!?-]*", "", normalized).strip()
    if not normalized:
        return None
    for mode in load()["modes"]:
        for trigger in mode.get("triggers", []):
            t = normalize_text(trigger)
            if t and (normalized == t or normalized.startswith(t + " ")):
                return mode
    return None

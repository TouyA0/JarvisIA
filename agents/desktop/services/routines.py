"""Routines vocales : séquences d'actions déclenchées par une phrase.

Configurées dans data/routines.json. Types d'étapes supportés :
  speak, speak_time, speak_weather, set_mode, powershell, open_url.
"""
from __future__ import annotations

import json
import re
import time
from typing import Callable

from agents.desktop import config
from common.textutil import normalize_text

_routines_cache: dict | None = None


def load() -> dict:
    global _routines_cache
    if _routines_cache is None:
        if config.ROUTINES_FILE.exists():
            with open(config.ROUTINES_FILE, encoding="utf-8") as f:
                _routines_cache = json.load(f)
        else:
            _routines_cache = {"version": 1, "routines": []}
    return _routines_cache


def match_trigger(text: str) -> dict | None:
    """Match en préfixe, comme les modes : la phrase doit ÊTRE la commande."""
    normalized = normalize_text(text)
    normalized = re.sub(rf"^{config.WAKE_WORD}\b[\s,;:!?-]*", "", normalized).strip()
    if not normalized:
        return None
    for routine in load().get("routines", []):
        for trigger in routine.get("triggers", []):
            t = normalize_text(trigger)
            if t and (normalized == t or normalized.startswith(t + " ")):
                return routine
    return None


def run(routine: dict, say: Callable[[str], None]) -> None:
    """Exécute les étapes d'une routine. `say` est fourni par le runtime
    (parole avec interruption + affichage HUD)."""
    from brain.core import modes as modes_mod
    from agents.desktop.services import weather
    from agents.desktop import state

    print(f"[Routine] {routine.get('name', routine.get('id'))}")
    for step in routine.get("steps", []):
        if state.stop_agent.is_set():
            break
        action = step.get("action", "")
        if action == "speak":
            say(step.get("text", ""))
        elif action == "speak_time":
            now = time.localtime()
            text = step.get("text", "Il est {heure}, Monsieur.")
            say(text.replace("{heure}", f"{now.tm_hour} heures {now.tm_min:02d}"))
        elif action == "speak_weather":
            say(weather.answer())
        elif action == "set_mode":
            activated = modes_mod.set_mode(step.get("mode_id", "normal"))
            if activated:
                say(f"{activated['name']} activé, Monsieur.")
        elif action == "powershell":
            from agents.desktop.tools import system
            system.run_powershell(step.get("cmd", ""))
        elif action == "open_url":
            from agents.desktop.tools import input_ctl
            input_ctl.open_url(step.get("url", ""))
        time.sleep(0.2)

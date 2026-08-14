"""Commandes apprises : le « fast path » à 0 ms.

Quand l'agent réussit une tâche répétable, il la mémorise ici (triggers +
commande PowerShell). Les fois suivantes, la commande part instantanément
sans repasser par un LLM.
"""
from __future__ import annotations

import json
import time

from agents.desktop import config
from agents.desktop.textutil import normalize_text

_commands_cache: list | None = None


def load() -> list:
    global _commands_cache
    if _commands_cache is None:
        if config.COMMANDS_FILE.exists():
            with open(config.COMMANDS_FILE, encoding="utf-8") as f:
                _commands_cache = json.load(f).get("commands", [])
        else:
            _commands_cache = []
    return _commands_cache


def save(commands: list) -> None:
    global _commands_cache
    _commands_cache = commands
    with open(config.COMMANDS_FILE, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "commands": commands}, f, ensure_ascii=False, indent=2)


ACTION_VERBS = {
    "ouvre", "lance", "ferme", "va", "coupe", "mets", "montre", "affiche",
    "vide", "verrouille", "redemarre", "eteins", "arrete", "pause",
    "prends", "minimise", "reduis", "monte", "baisse", "next", "previous",
}


def match(question: str) -> dict | None:
    q = normalize_text(question)
    words = q.split()

    # Phrase courte (≤4 mots) ou contient un verbe d'action dans les 4 premiers mots
    is_command_like = len(words) <= 4 or any(w in ACTION_VERBS for w in words[:4])

    best = None
    best_len = 0
    for cmd in load():
        for trigger in cmd.get("triggers", []):
            t = normalize_text(trigger)
            if t not in q or len(t) <= best_len:
                continue
            # Trigger multi-mots : assez spécifique, on accepte toujours
            # Trigger mono-mot : seulement si la phrase ressemble à une commande
            if len(t.split()) >= 2 or is_command_like:
                best = cmd
                best_len = len(t)
    return best


def execute_action(action: dict) -> None:
    from agents.desktop.tools import input_ctl, system

    atype = action.get("type", "")
    if atype == "open_url":
        input_ctl.open_url(action["url"])
    elif atype == "powershell":
        system.run_powershell(action["cmd"])
    elif atype == "open_app":
        system.run_powershell(f"Start-Process '{action['app']}'")
    elif atype == "sequence":
        for step in action.get("steps", []):
            execute_action(step)
            time.sleep(0.3)


def execute_entry(cmd: dict) -> str:
    execute_action(cmd.get("action", {}))
    return cmd.get("response", "Fait, Monsieur.")


def is_learn_command(question: str) -> bool:
    """Détecte une demande d'apprentissage de COMMANDE (contient un verbe d'action)."""
    q = normalize_text(question)
    trigger_kw = ["mémorise", "retiens", "apprends", "souviens-toi", "enregistre",
                  "quand je dis", "quand je te dis", "quand je te demande",
                  "si je dis", "si je te dis"]
    action_kw = ["ouvre", "lance", "ferme", "demarre", "execute", "tape", "clique",
                 "va sur", "navigue", "fait", "fais", "ecris", "joue", "telecharge"]
    has_trigger = any(kw in q for kw in trigger_kw)
    has_action = any(kw in q for kw in action_kw)
    return has_trigger and has_action

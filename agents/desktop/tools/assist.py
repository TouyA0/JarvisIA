"""Outils d'assistance : demander de l'aide à Monsieur, apprendre une commande."""
from __future__ import annotations

import time

from agents.desktop import state
from agents.desktop.textutil import normalize_text
from agents.desktop.tools.safety import is_destructive_command


def request_human_help(what_i_tried: str, what_i_need: str) -> str:
    """Ouvre la bulle d'aide, attend la réponse de Monsieur, retourne l'explication.

    Utilise tts.speak(), pas la version avec écouteur — même raison que la
    confirmation destructive : déjà appelée depuis l'intérieur de la boucle
    d'outils, sous l'écoute d'interruption du runtime.
    """
    from agents.desktop.ui import dialogs
    from agents.desktop.ui.hud import overlay
    from agents.desktop.audio import tts

    holder = dialogs.open_help(what_i_tried, what_i_need)
    if not (state.stop_agent.is_set() or state.stop_speaking.is_set()) and not overlay.is_muted():
        tts.speak("Je n'y arrive pas seul, Monsieur. Une fenêtre d'aide vient de s'ouvrir.")

    result = dialogs.wait_help(holder, timeout=300)
    if result:
        print(f"[Aide utilisateur] {result[:120]}")
        return f"EXPLICATION DE MONSIEUR : {result}"
    return "Aucune explication reçue."


def save_learned_command(triggers: list, powershell_cmd: str, response: str) -> str:
    from agents.desktop.brain import commands as cmdstore

    # Une commande destructrice ne devient pas un raccourci silencieux permanent
    # rejoué sans confirmation ni revue à chaque fois qu'un trigger matche.
    if is_destructive_command(powershell_cmd):
        return ("Commande non mémorisée : action potentiellement destructrice. "
                "Elle restera soumise à confirmation à chaque exécution.")
    try:
        commands = cmdstore.load()
        existing = {normalize_text(t) for cmd in commands for t in cmd.get("triggers", [])}
        new_triggers = [t for t in triggers if normalize_text(t) not in existing]
        if not new_triggers:
            return "Déjà mémorisé."
        new_cmd = {
            "id": f"learned_{int(time.time())}",
            "triggers": triggers,
            "action": {"type": "powershell", "cmd": powershell_cmd},
            "response": response,
        }
        commands.append(new_cmd)
        cmdstore.save(commands)
        print(f"[Apprentissage auto] {triggers[0]}")
        return "Mémorisé. La prochaine fois ce sera instantané."
    except Exception as e:
        return f"Erreur sauvegarde : {e}"

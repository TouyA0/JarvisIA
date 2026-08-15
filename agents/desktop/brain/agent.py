"""Agent avec tool use : pilotage du PC, boucle action → vérification.

Claude reste seul à piloter le PC — c'est là que la fiabilité du tool-use
compte vraiment. Nouveauté v2 : les captures d'écran sont transmises en image,
Claude voit donc réellement l'écran.
"""
from __future__ import annotations

import re
import time
from typing import Callable, Optional

from agents.desktop import config, state
from agents.desktop.clients import get_anthropic
from brain.core import history, prompts, usage
from agents.desktop.tools import registry

# Callback branché par le runtime pour afficher l'activité dans le HUD
# (ex : "⚙ run_powershell"). Peut rester None.
on_activity: Optional[Callable[[str], None]] = None


def _notify(activity: str) -> None:
    if on_activity:
        try:
            on_activity(activity)
        except Exception:
            pass


def _recovery_hint(tool_name: str, args: dict, result: str) -> str | None:
    """Injecte un conseil de récupération quand un outil échoue."""
    r = result.lower()
    is_error = any(k in r for k in ["cannot find", "error", "introuvable", "aucun fichier",
                                    "not found", "exception", "erreur", "n'a pas pu"])
    if not is_error:
        return None

    if tool_name == "run_powershell":
        cmd = args.get("command", "").lower()

        # Start-Process échoue → chercher via Get-StartApps
        if "start-process" in cmd:
            m = re.search(r"start-process\s+['\"]?([a-z0-9_\-\.]+)['\"]?", cmd)
            name = m.group(1).rstrip(".exe") if m else "app"
            return (f"Start-Process a échoué. Étape suivante OBLIGATOIRE : "
                    f"Get-StartApps | Where-Object {{$_.Name -like '*{name}*'}}")

        # Get-StartApps vide → chercher l'exe dans LocalAppData
        if "get-startapps" in cmd:
            m = re.search(r"like\s+'?\*([a-z0-9_\-]+)\*", cmd)
            name = m.group(1) if m else "app"
            return (f"Get-StartApps n'a rien trouvé. Étape suivante OBLIGATOIRE : "
                    f"Get-ChildItem \"$env:LOCALAPPDATA\\Programs\",\"$env:LOCALAPPDATA\" "
                    f"-Recurse -Filter '*{name}*.exe' -ErrorAction SilentlyContinue "
                    f"| Select-Object -First 5 FullName")

        # Recherche filesystem échoue → demander de l'aide
        if "get-childitem" in cmd:
            return ("Toutes les recherches ont échoué. "
                    "Appelle maintenant request_human_help pour demander à Monsieur "
                    "où se trouve l'application.")

    return None


def _tool_result_content(result) -> str | list:
    """Construit le contenu d'un tool_result : texte simple, ou blocs
    image + texte quand l'outil retourne une capture d'écran."""
    if isinstance(result, dict):
        blocks = []
        if result.get("image_b64"):
            blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": result.get("media_type", "image/jpeg"),
                    "data": result["image_b64"],
                },
            })
        blocks.append({"type": "text", "text": result.get("text", "")})
        return blocks
    return result


def ask_with_tools(question: str) -> str | None:
    """Boucle d'agent complète. Retourne la réponse finale, ou None si le tour
    a été interrompu par la voix."""
    client = get_anthropic()
    if not client:
        print("[Claude] Clé API manquante — vérifiez votre ANTHROPIC_API_KEY dans .env")
        return "Je ne peux pas répondre sans clé API, Monsieur. Vérifiez le fichier point env."

    claude_tools = registry.to_claude_tools(cached=True)
    static_prompt, dynamic_prompt = prompts.get_system_prompt()
    # Bloc statique (personnalité + contexte + instructions) → mis en cache
    static_text = static_prompt + "\n\n" + prompts.AGENT_INSTRUCTIONS
    system = [{"type": "text", "text": static_text, "cache_control": {"type": "ephemeral"}}]
    # Bloc dynamique (mémoire + mode actif) → non caché, peut changer
    if dynamic_prompt:
        system.append({"type": "text", "text": dynamic_prompt})

    messages = history.recent_text_history() + [{"role": "user", "content": question}]

    tool_call_count = 0
    help_requested = False
    empty_turn_retried = False
    t0 = time.time()
    first_response = True
    # Persiste sur toute la boucle : une fois une donnée non fiable lue, elle
    # reste "dans le contexte" du modèle pour le reste du tour.
    turn_state = {"tainted": False}

    for _ in range(12):
        if state.stop_agent.is_set():
            return None

        if tool_call_count >= 5 and not help_requested:
            help_requested = True
            messages.append({"role": "user", "content":
                             "Tu as effectué plus de 5 appels sans résoudre la tâche. "
                             "Appelle request_human_help maintenant."})

        _notify("RÉFLEXION…")
        try:
            response = client.messages.create(
                model=config.CLAUDE_MODEL,
                max_tokens=1024,
                system=system,
                tools=claude_tools,
                messages=messages,
            )
            usage.track(getattr(response, "usage", None))
            if first_response:
                state.set_metric("llm_first_ms", (time.time() - t0) * 1000)
                first_response = False
        except Exception as e:
            print(f"[Claude] Erreur API : {e}")
            _notify("")
            return "Je rencontre une difficulté technique, Monsieur."

        if response.stop_reason == "end_turn":
            final = "".join(
                b.text for b in response.content if getattr(b, "type", None) == "text"
            ).strip()

            if not final:
                # Claude s'est arrêté sans un mot — fréquent juste après un
                # appel d'outil qu'il jugeait suffisant. Ce n'est PAS un échec :
                # dans ce cas précis (au moins un outil déjà utilisé), on lui
                # redemande explicitement de formuler sa réponse au lieu de
                # supposer un échec par défaut, ce qui contredirait Monsieur
                # quand la tâche a en réalité réussi.
                if tool_call_count > 0 and not empty_turn_retried:
                    empty_turn_retried = True
                    messages.append({"role": "assistant", "content": response.content})
                    messages.append({"role": "user", "content":
                        "Formule maintenant ta réponse finale à voix haute pour "
                        "Monsieur, en une phrase, sur la base de ce que tu viens "
                        "de faire. N'appelle aucun autre outil."})
                    continue
                final = "Je n'ai pas réussi à accomplir cette tâche, Monsieur."

            _notify("")
            history.remember_exchange(question, final, source="claude-agent")
            return final

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type != "tool_use":
                    continue
                print(f"[Outil] {block.name}({block.input})")
                _notify(f"OUTIL : {block.name}")
                result = registry.execute(block.name, block.input, turn_state)
                result_text = result.get("text", "") if isinstance(result, dict) else result
                print(f"[Résultat] {result_text[:200]}")
                tool_call_count += 1

                hint = _recovery_hint(block.name, block.input, result_text)
                if hint and isinstance(result, str):
                    result = result + f"\n\nCONSEIL SYSTÈME : {hint}"

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": _tool_result_content(result),
                })

            messages.append({"role": "user", "content": tool_results})

    _notify("")
    final = "Je n'ai pas réussi à accomplir cette tâche, Monsieur. Pourriez-vous préciser ?"
    history.remember_exchange(question, final, source="claude-agent")
    return final

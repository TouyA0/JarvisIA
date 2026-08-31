"""Agent avec tool use, côté brain : pilotage PC dispatché sur le réseau.

Miroir de `agents/desktop/brain/agent.py::ask_with_tools`, mais chaque
outil est exécuté sur un appareil distant (`brain.devices.registry.dispatch`)
au lieu d'être exécuté en local — c'est la seule vraie différence.
Tourne dans le process brain, donc async nativement : seul l'appel à
Claude (bloquant) passe par un thread (`asyncio.to_thread`), le dispatch
réseau (déjà async) s'attend directement, sans le pont thread→asyncio
utilisé par `brain/core/chat.py` pour la conversation pure.

Pas de `state.stop_agent` ici : c'est un `threading.Event` du process
desktop, sans équivalent réseau — voir `brain/state.py`. L'arrêt à
distance reste un chantier séparé (Phase 10, "volontairement hors de ce
chantier").
"""
from __future__ import annotations

import asyncio
import time
from typing import Callable, Optional

from brain import config, state
from brain.clients import get_anthropic
from brain.core import history, prompts, usage
from brain.devices import registry

# Callback branché par server.py pour informer la Console web de
# l'activité en cours (ex : "⚙ open_url") — même idée que le hook
# on_activity du HUD desktop (agents/desktop/brain/agent.py), transposé
# au web sous forme de message chat.status. Peut rester None.
on_activity: Optional[Callable[[str], None]] = None


def _notify(activity: str) -> None:
    if on_activity:
        try:
            on_activity(activity)
        except Exception:
            pass


def _tool_result_content(result) -> str | list:
    """Construit le contenu d'un tool_result : texte simple, ou blocs
    image + texte quand l'outil retourne une capture d'écran. Identique à
    agents/desktop/brain/agent.py::_tool_result_content — même format de
    retour des outils (`{"text":..., "image_b64":...}`), le dispatch
    réseau n'y change rien."""
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


async def _dispatch_tool(device_id: str, name: str, args: dict) -> dict:
    """Exécute un outil sur l'appareil distant. Ne lève jamais — toute
    erreur (déconnexion, timeout, échec côté agent) devient un texte que
    Claude peut voir et sur lequel il peut réagir, comme le fait déjà
    agents/desktop/tools/registry.execute() en local."""
    try:
        result = await registry.dispatch(device_id, name, args)
    except KeyError:
        return {"text": "Appareil déconnecté en cours de route, Monsieur."}
    except asyncio.TimeoutError:
        return {"text": "L'appareil n'a pas répondu à temps."}
    if not result.ok:
        return {"text": result.error or "L'appareil a signalé une erreur."}
    return result.result or {}


async def ask_with_tools(question: str, device_id: str) -> str | None:
    """Boucle d'agent complète, outils exécutés à distance. Retourne la
    réponse finale, ou None seulement si le brain n'a pas de clé API."""
    client = get_anthropic()
    if not client:
        print("[Claude] Clé API manquante — vérifiez ANTHROPIC_API_KEY dans .env")
        return "Je ne peux pas répondre sans clé API, Monsieur. Vérifiez le fichier point env."

    # Import différé : agents.desktop.tools.registry importe des modules
    # Windows-only (écran, input) juste pour leurs schémas d'outils, dont
    # on n'a besoin que de la donnée (to_claude_tools). Un brain qui
    # tournerait un jour ailleurs que sur ce PC (Raspberry Pi VPN, par ex.)
    # doit pouvoir démarrer sans ça — seul cet appel échouerait, pas le
    # process entier.
    from agents.desktop.tools.registry import to_claude_tools
    claude_tools = to_claude_tools(cached=True)
    static_prompt, dynamic_prompt = prompts.get_system_prompt()
    static_text = static_prompt + "\n\n" + prompts.AGENT_INSTRUCTIONS
    system = [{"type": "text", "text": static_text, "cache_control": {"type": "ephemeral"}}]
    if dynamic_prompt:
        system.append({"type": "text", "text": dynamic_prompt})

    messages = history.recent_text_history() + [{"role": "user", "content": question}]

    tool_call_count = 0
    help_requested = False
    empty_turn_retried = False
    t0 = time.time()
    first_response = True

    for _ in range(12):
        if tool_call_count >= 5 and not help_requested:
            help_requested = True
            messages.append({"role": "user", "content":
                             "Tu as effectué plus de 5 appels sans résoudre la tâche. "
                             "Appelle request_human_help maintenant."})

        _notify("RÉFLEXION…")
        try:
            response = await asyncio.to_thread(
                client.messages.create,
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
            history.remember_exchange(question, final, source="brain-agent")
            return final

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type != "tool_use":
                    continue
                print(f"[Outil réseau] {block.name}({block.input}) → {device_id}")
                _notify(f"OUTIL : {block.name}")
                result = await _dispatch_tool(device_id, block.name, block.input)
                tool_call_count += 1

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": _tool_result_content(result),
                })

            messages.append({"role": "user", "content": tool_results})

    _notify("")
    final = "Je n'ai pas réussi à accomplir cette tâche, Monsieur. Pourriez-vous préciser ?"
    history.remember_exchange(question, final, source="brain-agent")
    return final

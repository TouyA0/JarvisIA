"""Agent avec tool use : pilotage du PC, boucle action → vérification.

Claude reste seul à piloter le PC — c'est là que la fiabilité du tool-use
compte vraiment. Nouveauté v2 : les captures d'écran sont transmises en image,
Claude voit donc réellement l'écran.
"""
from __future__ import annotations

import json
import re
import time
from typing import Callable, Optional

import requests

from agents.desktop import config, state
from agents.desktop.clients import get_anthropic
from brain import tools as brain_tools
from brain.core import history, prompts, usage
from agents.desktop.tools import registry

# Callback branché par le runtime pour afficher l'activité dans le HUD
# (ex : "⚙ run_powershell"). Peut rester None.
on_activity: Optional[Callable[[str], None]] = None

# Même idée pour indiquer QUI a répondu ("ollama-agent" ou "claude-agent") —
# le runtime s'en sert pour afficher le bon modèle sur le HUD (F7 phase 2 :
# avant ça, l'étiquette affichée était toujours Claude, même quand le
# modèle local avait répondu).
on_source: Optional[Callable[[str], None]] = None


def _notify(activity: str) -> None:
    if on_activity:
        try:
            on_activity(activity)
        except Exception:
            pass


def _notify_source(source: str) -> None:
    if on_source:
        try:
            on_source(source)
        except Exception:
            pass


# ── Tool-use local (F7, phase 2) ─────────────────────────────────────────────
# Miroir de brain/core/agent.py::_ask_local_with_tools — mêmes outils sûrs,
# même garde-fou, mêmes chiffres mesurés (scripts/test_ollama_tools.py).
# Différence structurelle avec la Console web : la boucle Claude ci-dessous
# ne connaît QUE les outils PC (registry.PC_TOOLS) — les outils brain
# (agenda, mails, météo…) n'y ont jamais été exposés, donc pour la voix ce
# chemin local n'écarte pas Claude sur ces sujets, il ajoute une capacité
# qui manquait. Le pilotage PC (Claude + PC_TOOLS) n'est pas touché.
SAFE_LOCAL_TOOL_NAMES = frozenset({
    "weather_now", "system_diagnostics",
    "calendar_events",
    "gmail_search", "gmail_read", "zoho_search", "zoho_read",
    "web_search", "fetch_page",
    "tisseo_next",
    "jellyfin_search", "jellyfin_now_playing",
    "jellyfin_continue_watching", "jellyfin_recently_added",
})

_LOCAL_TOOL_MAX_TURNS = 4


def _safe_local_tools() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in brain_tools.to_claude_tools()
        if t["name"] in SAFE_LOCAL_TOOL_NAMES
    ]


def _ollama_chat_sync(messages: list[dict], tools: list[dict]) -> dict | None:
    try:
        resp = requests.post(
            config.OLLAMA_URL,
            json={
                "model": config.OLLAMA_MODEL,
                "messages": messages,
                "tools": tools,
                "stream": False,
                "think": False,
                "keep_alive": config.OLLAMA_KEEP_ALIVE,
                "options": {"num_predict": 400},
            },
            timeout=(config.OLLAMA_CONNECT_TIMEOUT, config.OLLAMA_READ_TIMEOUT),
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[Ollama outils] indisponible ou erreur ({e}).")
        return None
    data = resp.json()
    if data.get("error"):
        print(f"[Ollama outils] erreur : {data['error']}")
        return None
    return data.get("message", {})


def _ask_local_with_tools(question: str) -> str | None:
    """Voir brain/core/agent.py::_ask_local_with_tools — même logique,
    exécution directe (in-process) plutôt qu'asynchrone."""
    tools = _safe_local_tools()
    static_prompt, dynamic_prompt = prompts.get_system_prompt()
    system_text = static_prompt + "\n\n" + prompts.AGENT_INSTRUCTIONS
    if dynamic_prompt:
        system_text += "\n\n" + dynamic_prompt

    messages = [{"role": "system", "content": system_text}]
    messages += history.recent_text_history()
    messages.append({"role": "user", "content": question})

    tool_call_count = 0
    for _ in range(_LOCAL_TOOL_MAX_TURNS):
        if state.stop_agent.is_set():
            return None
        message = _ollama_chat_sync(messages, tools)
        if message is None:
            return None

        tool_calls = message.get("tool_calls") or []
        if not tool_calls:
            text = (message.get("content") or "").strip()
            return text if (text and tool_call_count > 0) else None

        messages.append({"role": "assistant", "content": message.get("content", ""),
                          "tool_calls": tool_calls})

        for call in tool_calls:
            fn = call.get("function", {})
            name = fn.get("name")
            args = fn.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except (json.JSONDecodeError, TypeError):
                    args = {}
            if not isinstance(args, dict):
                args = {}

            if name not in SAFE_LOCAL_TOOL_NAMES:
                print(f"[Ollama outils] outil hors périmètre local : {name} — repli Claude.")
                return None

            print(f"[Outil local] {name}({args})")
            result = brain_tools.execute(name, args)
            tool_call_count += 1
            messages.append({"role": "tool", "content": result if isinstance(result, str) else str(result)})

    return None


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

    # Tool-use local d'abord (F7 phase 2) : agenda, mails en lecture, météo,
    # diagnostics, recherche web, Tisséo, Jellyfin — voir _ask_local_with_tools.
    local_answer = _ask_local_with_tools(question)
    if local_answer:
        _notify_source("ollama-agent")
        history.remember_exchange(question, local_answer, source="ollama-agent")
        return local_answer

    # Outils pilotage PC (locaux) + outils natifs brain (comptes externes,
    # domotique, télé du salon — brain/tools.py) : un seul appel Claude voit
    # les deux, la boucle tool_use ci-dessous route chaque appel vers le bon
    # exécuteur selon son nom (brain_tools.NAMES). Miroir de
    # brain/core/agent.py::ask_with_tools.
    claude_tools = registry.to_claude_tools(cached=False) + brain_tools.to_claude_tools()
    if claude_tools:
        claude_tools[-1]["cache_control"] = {"type": "ephemeral"}
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
            _notify_source("claude-agent")
            history.remember_exchange(question, final, source="claude-agent")
            return final

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type != "tool_use":
                    continue
                _notify(f"OUTIL : {block.name}")
                if block.name in brain_tools.NAMES:
                    print(f"[Outil brain] {block.name}({block.input})")
                    result = brain_tools.execute(block.name, block.input)
                else:
                    print(f"[Outil] {block.name}({block.input})")
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
    _notify_source("claude-agent")
    final = "Je n'ai pas réussi à accomplir cette tâche, Monsieur. Pourriez-vous préciser ?"
    history.remember_exchange(question, final, source="claude-agent")
    return final

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
import json
import time
from typing import Callable, Optional

import requests

from brain import cards, config, state, tools as brain_tools
from brain.clients import get_anthropic
from brain.core import history, prompts, usage
from brain.devices import registry

# ── Tool-use local (F7, phase 2) ─────────────────────────────────────────────
# Sous-ensemble d'outils qu'un modèle Ollama local a le droit d'appeler : QUE
# du lecture-seule, sans confirmation (docs/ROADMAP.md F7 §07 phase 2). Rien
# ici ne touche brain/integrations/confirm.py — Drive en écriture, Gmail/Zoho
# en envoi, Home Assistant en contrôle restent exclusivement sur Claude.
#
# Choix mesuré, pas supposé : scripts/test_ollama_tools.py, sur qwen3:14b et
# les vrais schémas du projet, donne 100% de JSON valide et ~88% de bon choix
# d'outil sur ce même périmètre. Le garde-fou ci-dessous (SAFE_LOCAL_TOOL_NAMES
# revérifié à l'exécution) couvre le reste : un outil halluciné ou hors
# périmètre n'est jamais exécuté, la question repart simplement vers Claude.
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
    """BRAIN_TOOLS est au format Claude (name/description/input_schema) ;
    Ollama attend le format OpenAI (type=function, function={...,parameters})."""
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
    """Un tour Ollama, appels d'outils inclus. Ne lève jamais — toute panne
    (Ollama éteint, timeout, erreur de génération) doit se traduire par un
    repli vers Claude, jamais par une exception qui casse la question."""
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


async def _ask_local_with_tools(question: str) -> str | None:
    """Tente de répondre avec le modèle local, restreint aux outils sûrs.

    Retourne None dès que le résultat n'est pas fiable à 100% — outil hors
    périmètre, JSON invalide, panne, ou trop d'allers-retours sans conclure
    — plutôt que de risquer une réponse bancale : l'appelant repart alors sur
    Claude, exactement comme brain/core/chat.py::ask_stream() le fait déjà
    pour la conversation pure.

    Ne fait JAMAIS confiance à une réponse texte spontanée (sans appel
    d'outil) : un modèle limité à 14 outils n'a aucune base pour répondre à
    une question hors de ce périmètre, et pourrait répondre de façon plausible
    mais fausse (« Fait, Monsieur » sans avoir rien fait). Seul un texte final
    formulé APRÈS au moins un outil exécuté avec succès est retenu.
    """
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
        message = await asyncio.to_thread(_ollama_chat_sync, messages, tools)
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
            result = await asyncio.to_thread(brain_tools.execute, name, args)
            tool_call_count += 1
            messages.append({"role": "tool", "content": result if isinstance(result, str) else str(result)})

    return None

# Callback branché par server.py pour informer la Console web de
# l'activité en cours (ex : "⚙ open_url") — même idée que le hook
# on_activity du HUD desktop (agents/desktop/brain/agent.py), transposé
# au web sous forme de message chat.status. Peut rester None.
on_activity: Optional[Callable[[str], None]] = None

# Même idée pour indiquer QUI a réellement répondu ("ollama-agent" ou
# "claude-agent") — server.py l'utilise pour que le message chat.done envoyé
# à la Console reflète le vrai modèle, plutôt qu'une étiquette figée
# "brain-agent" qui ne dirait jamais si le tour a été géré en local (F7).
on_source: Optional[Callable[[str], None]] = None


def _device_name(device_id: str) -> str:
    device = registry.get(device_id)
    return device.name if device else "Capture d'écran"


_UNTRUSTED_START = "----- DÉBUT DONNÉES NON FIABLES -----\n"
_UNTRUSTED_END = "\n----- FIN DONNÉES NON FIABLES -----"


def _strip_untrusted_wrapper(text: str) -> str:
    """read_file_content encadre son résultat via
    agents/desktop/tools/safety.py::wrap_untrusted (anti-injection, adressé
    à Claude) — inutile et bruyant à l'écran sur la carte "file_preview",
    on retire juste l'habillage, jamais le contenu lui-même."""
    start = text.find(_UNTRUSTED_START)
    end = text.find(_UNTRUSTED_END)
    if start != -1 and end != -1 and end > start:
        return text[start + len(_UNTRUSTED_START):end]
    return text


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


async def ask_with_tools(question: str, device_id: str | None) -> str | None:
    """Boucle d'agent complète, outils exécutés à distance. Retourne la
    réponse finale, ou None seulement si le brain n'a pas de clé API.

    `device_id` peut être None : aucun appareil n'est connecté, mais les
    outils « natifs brain » (agenda, mails, Drive, itinéraires…) n'en ont
    pas besoin. Dans ce cas les outils de pilotage PC ne sont simplement
    pas proposés à Claude, plutôt que de refuser la question entière."""
    client = get_anthropic()
    if not client:
        print("[Claude] Clé API manquante — vérifiez ANTHROPIC_API_KEY dans .env")
        return "Je ne peux pas répondre sans clé API, Monsieur. Vérifiez le fichier point env."

    # Tool-use local d'abord (F7 phase 2) : agenda, mails en lecture, météo,
    # diagnostics, recherche web, Tisséo, Jellyfin. Repli silencieux vers
    # Claude si le modèle local échoue ou sort de ce périmètre — voir
    # _ask_local_with_tools ci-dessus.
    local_answer = await _ask_local_with_tools(question)
    if local_answer:
        _notify_source("ollama-agent")
        history.remember_exchange(question, local_answer, source="ollama-agent")
        return local_answer

    # Import différé : agents.desktop.tools.registry importe des modules
    # Windows-only (écran, input) juste pour leurs schémas d'outils, dont
    # on n'a besoin que de la donnée (to_claude_tools). Un brain qui
    # tournerait un jour ailleurs que sur ce PC (Raspberry Pi VPN, par ex.)
    # doit pouvoir démarrer sans ça — seul cet appel échouerait, pas le
    # process entier.
    from agents.desktop.tools.registry import to_claude_tools
    # Outils pilotage PC (dispatchés sur l'appareil) + outils natifs brain
    # (comptes externes, ex : calendar_events) — un seul appel Claude voit
    # les deux, la boucle tool_use ci-dessous route chaque appel vers le
    # bon exécuteur selon son nom (brain_tools.NAMES). Sans appareil
    # connecté, seuls les seconds sont proposés.
    pc_tools = to_claude_tools(cached=False) if device_id else []
    claude_tools = pc_tools + brain_tools.to_claude_tools()
    if claude_tools:
        claude_tools[-1]["cache_control"] = {"type": "ephemeral"}
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
    # S1 — dernière capture tv_screenshot de ce tour (image_b64/media_type) :
    # si Claude conclut après l'avoir regardée ("c'est qui cet acteur ?", "quel
    # film ?"...), on la réutilise pour une carte qui montre l'image ET la
    # réponse ensemble, plutôt que la capture brute déjà postée par
    # brain_tools.execute (carte "tv", sans le texte d'identification).
    last_tv_screenshot: dict | None = None

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
            _notify_source("claude-agent")
            history.remember_exchange(question, final, source="claude-agent")
            if last_tv_screenshot:
                cards.emit(
                    "vision", "Télé du salon",
                    {"text": final, **last_tv_screenshot},
                    subtitle="Identifié depuis la télé",
                )
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
                    result = await asyncio.to_thread(brain_tools.execute, block.name, block.input)
                    if block.name == "tv_screenshot" and isinstance(result, dict) and result.get("image_b64"):
                        last_tv_screenshot = {
                            "image_b64": result["image_b64"],
                            "media_type": result.get("media_type", "image/jpeg"),
                        }
                elif not device_id:
                    result = {"text": "Aucun appareil connecté pour exécuter ça, Monsieur."}
                else:
                    print(f"[Outil réseau] {block.name}({block.input}) → {device_id}")
                    result = await _dispatch_tool(device_id, block.name, block.input)
                    # Une capture partait jusqu'ici uniquement vers Claude,
                    # pour analyse — Monsieur ne la voyait jamais, alors
                    # qu'il demandait parfois explicitement à la voir
                    # (ROADMAP_DISPLAY_INTEGRATIONS.md §3). Elle devient une
                    # carte, affichée dans la Console.
                    if isinstance(result, dict) and result.get("image_b64"):
                        cards.emit(
                            "screenshot",
                            _device_name(device_id),
                            {"image_b64": result["image_b64"],
                             "media_type": result.get("media_type", "image/jpeg")},
                            subtitle="Capture à distance",
                        )
                    # Même logique pour un fichier local lu à distance —
                    # jusqu'ici seul Claude voyait le contenu, jamais affiché
                    # (ROADMAP_DISPLAY_INTEGRATIONS.md §2.2, "file_preview").
                    elif block.name == "read_file_content" and isinstance(result, str) and result:
                        cards.emit(
                            "file_preview",
                            block.input.get("path", "Fichier"),
                            {"text": _strip_untrusted_wrapper(result)},
                            subtitle=_device_name(device_id),
                        )
                tool_call_count += 1

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

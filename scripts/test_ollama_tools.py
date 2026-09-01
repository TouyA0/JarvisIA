"""Harnais de test F7 (phase 1) : mesure la fiabilité du tool-calling d'un
modèle Ollama sur les VRAIS schémas d'outils du projet (brain/tools.py +
agents/desktop/tools/registry.py), pas sur un benchmark générique.

Deux variantes par commande :
  - "full"   : les ~49 outils envoyés d'un bloc, comme le fait aujourd'hui
               brain/core/agent.py::ask_with_tools() pour Claude.
  - "subset" : seulement les outils du domaine concerné (5-10 outils),
               tel que proposé dans docs/ROADMAP.md (F7) en s'appuyant sur
               le découpage déjà présent dans
               agents/desktop/brain/router.py::PC_COMMAND_KEYWORDS.

Aucun outil n'est réellement exécuté : on ne mesure QUE la sortie du modèle
(nom d'outil choisi + validité/complétude des arguments), donc ce script est
sans risque à relancer autant de fois que nécessaire.

Usage :
    python scripts/test_ollama_tools.py
    python scripts/test_ollama_tools.py --model qwen3:8b
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Console Windows par défaut = cp1252, incapable d'encoder →/═/… utilisés
# plus bas — sans ça le script plante au premier caractère non représentable
# au lieu d'afficher le moindre résultat.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from brain import config
from brain.core import prompts
from brain.tools import BRAIN_TOOLS


def _brain_tools_ollama() -> list[dict]:
    """BRAIN_TOOLS est au format Claude (name/description/input_schema).
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
        for t in BRAIN_TOOLS
    ]


def _pc_tools_ollama() -> list[dict]:
    from agents.desktop.tools.registry import PC_TOOLS
    return [dict(t) for t in PC_TOOLS]


ALL_TOOLS = _pc_tools_ollama() + _brain_tools_ollama()
TOOLS_BY_NAME = {t["function"]["name"]: t for t in ALL_TOOLS}

# ── Sous-ensembles par domaine ───────────────────────────────────────────
# Reprend le découpage déjà présent (en commentaires) dans
# agents/desktop/brain/router.py::PC_COMMAND_KEYWORDS.
CATEGORIES = {
    "agenda": ["calendar_events"],
    "drive": ["drive_search", "drive_read", "drive_create", "drive_update", "drive_delete"],
    "contacts": ["contacts_search"],
    "jellyfin": ["jellyfin_search", "jellyfin_now_playing", "jellyfin_continue_watching", "jellyfin_recently_added"],
    "tisseo": ["tisseo_next"],
    "itineraire": ["directions"],
    "domotique": ["ha_state", "ha_list_all", "ha_control", "ha_set_temperature", "ha_network_status"],
    "mail": ["gmail_search", "gmail_read", "gmail_draft", "gmail_send", "zoho_search", "zoho_read", "zoho_compose"],
    "meteo_diag": ["weather_now", "system_diagnostics"],
    "web": ["web_search", "fetch_page"],
    "spotify": ["spotify_now_playing", "spotify_play", "spotify_control", "spotify_volume"],
    "pc": ["run_powershell", "type_text", "press_keys", "open_url", "mouse_click", "take_screenshot",
           "scroll_page", "get_browser_url", "read_screen", "read_clipboard", "search_file",
           "open_file", "list_folder", "read_file_content"],
}


def _subset(category: str) -> list[dict]:
    return [TOOLS_BY_NAME[name] for name in CATEGORIES[category] if name in TOOLS_BY_NAME]


# ── Jeu de commandes types ────────────────────────────────────────────────
# (prompt, catégorie, outil attendu, arguments obligatoires attendus)
TEST_CASES = [
    ("Qu'est-ce que j'ai à l'agenda aujourd'hui ?", "agenda", "calendar_events", []),
    ("J'ai quoi de prévu demain ?", "agenda", "calendar_events", []),
    ("Mon planning de la semaine ?", "agenda", "calendar_events", []),
    ("Cherche le fichier budget dans mon Drive", "drive", "drive_search", ["query"]),
    ("Montre-moi mes documents Drive récents", "drive", "drive_search", []),
    ("Résume le contenu du fichier compte-rendu", "drive", "drive_search", ["query"]),
    ("Quel est le numéro de Julien ?", "contacts", "contacts_search", ["query"]),
    ("Cherche le contact de Marie", "contacts", "contacts_search", ["query"]),
    ("Lance le dernier épisode de Loki sur Jellyfin", "jellyfin", "jellyfin_search", ["query"]),
    ("Reprends ma série en cours", "jellyfin", "jellyfin_continue_watching", []),
    ("Quoi de neuf sur Jellyfin ?", "jellyfin", "jellyfin_recently_added", []),
    ("Quand passe le prochain bus ?", "tisseo", "tisseo_next", []),
    ("Prochain métro à Jean Jaurès ?", "tisseo", "tisseo_next", []),
    ("Combien de temps pour aller à Toulouse Capitole ?", "itineraire", "directions", ["destination"]),
    ("Distance jusqu'à la gare Matabiau ?", "itineraire", "directions", ["destination"]),
    ("Allume la lumière du salon", "domotique", "ha_control", ["entity"]),
    ("Éteins toutes les lumières", "domotique", "ha_control", []),
    ("Mets le chauffage à 20 degrés", "domotique", "ha_set_temperature", []),
    ("Quel est l'état de mon serveur Home Assistant ?", "domotique", "ha_network_status", []),
    ("Quels appareils sont allumés à la maison ?", "domotique", "ha_list_all", []),
    ("Ai-je reçu un mail de la banque ?", "mail", "gmail_search", ["query"]),
    ("Lis-moi le dernier mail de Paul", "mail", "gmail_search", []),
    ("Rédige un brouillon pour répondre à Sophie", "mail", "gmail_draft", []),
    ("Envoie un mail à Marc pour confirmer le rendez-vous", "mail", "gmail_send", []),
    ("Quel temps fait-il ?", "meteo_diag", "weather_now", []),
    ("Va-t-il pleuvoir aujourd'hui ?", "meteo_diag", "weather_now", []),
    ("Comment va le PC ?", "meteo_diag", "system_diagnostics", []),
    ("Cherche sur internet la dernière version de Python", "web", "web_search", ["query"]),
    ("Résume cet article : https://fr.wikipedia.org/wiki/Python", "web", "fetch_page", ["url"]),
    ("Quelle est l'actualité du jour ?", "web", "web_search", []),
    ("Mets la musique en pause", "spotify", "spotify_control", []),
    ("Qu'est-ce qui joue en ce moment ?", "spotify", "spotify_now_playing", []),
    ("Monte le son de Spotify à 80%", "spotify", "spotify_volume", ["percent"]),
    ("Prends une capture d'écran", "pc", "take_screenshot", []),
    ("Ouvre Chrome", "pc", "run_powershell", []),
    ("Cherche le fichier rapport.pdf sur mon PC", "pc", "search_file", ["name"]),
]


def _call_ollama(model: str, prompt: str, tools: list[dict]) -> tuple[dict | None, float, str | None]:
    """Un seul tour, sans historique — reflète le premier appel de la boucle
    d'agent (agents/desktop/brain/agent.py / brain/core/agent.py)."""
    static_prompt, _ = prompts.get_system_prompt()
    system_text = static_prompt + "\n\n" + prompts.AGENT_INSTRUCTIONS

    t0 = time.time()
    try:
        resp = requests.post(
            config.OLLAMA_URL,
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_text},
                    {"role": "user", "content": prompt},
                ],
                "tools": tools,
                "stream": False,
                "think": False,
                "options": {"num_predict": 400},
            },
            timeout=(config.OLLAMA_CONNECT_TIMEOUT, config.OLLAMA_READ_TIMEOUT),
        )
        resp.raise_for_status()
    except Exception as e:
        return None, time.time() - t0, str(e)

    elapsed = time.time() - t0
    data = resp.json()
    if data.get("error"):
        return None, elapsed, data["error"]
    return data.get("message", {}), elapsed, None


def _evaluate(message: dict | None, expected_tool: str, expected_args: list[str]) -> dict:
    result = {
        "responded": message is not None,
        "called_tool": False,
        "valid_json": False,
        "correct_tool": False,
        "args_complete": False,
        "chosen_tool": None,
    }
    if not message:
        return result

    tool_calls = message.get("tool_calls") or []
    if not tool_calls:
        return result  # le modèle a répondu en texte au lieu d'appeler un outil

    result["called_tool"] = True
    call = tool_calls[0]
    fn = call.get("function", {})
    result["chosen_tool"] = fn.get("name")

    args = fn.get("arguments")
    # Ollama renvoie déjà un dict la plupart du temps ; certains modèles le
    # renvoient encore comme une chaîne JSON — les deux formes sont testées.
    if isinstance(args, str):
        try:
            args = json.loads(args)
            result["valid_json"] = True
        except (json.JSONDecodeError, TypeError):
            args = {}
    elif isinstance(args, dict):
        result["valid_json"] = True
    else:
        args = {}

    result["correct_tool"] = result["chosen_tool"] == expected_tool
    result["args_complete"] = all(args.get(k) for k in expected_args)
    return result


def run(model: str, verbose: bool) -> None:
    print(f"Modèle testé : {model}")
    print(f"Outils disponibles : {len(ALL_TOOLS)} (pilotage PC + brain)")
    print(f"Commandes testées : {len(TEST_CASES)} × 2 variantes (full / subset)\n")

    rows = []
    for i, (prompt, category, expected_tool, expected_args) in enumerate(TEST_CASES, 1):
        for variant, tools in (("full", ALL_TOOLS), ("subset", _subset(category))):
            message, elapsed, error = _call_ollama(model, prompt, tools)
            if error:
                print(f"[{i:2d}/{len(TEST_CASES)}] ERREUR ({variant}) « {prompt} » → {error}")
                rows.append({"prompt": prompt, "category": category, "variant": variant,
                             "expected": expected_tool, "error": error, "elapsed": elapsed})
                continue
            ev = _evaluate(message, expected_tool, expected_args)
            ev.update({"prompt": prompt, "category": category, "variant": variant,
                       "expected": expected_tool, "elapsed": elapsed, "n_tools": len(tools)})
            rows.append(ev)
            if verbose or not ev["correct_tool"]:
                status = "OK" if ev["correct_tool"] else "RATÉ"
                print(f"[{i:2d}/{len(TEST_CASES)}] {status:4s} ({variant:6s}, {len(tools):2d} outils, "
                      f"{elapsed:.1f}s) « {prompt} » → attendu={expected_tool} obtenu={ev['chosen_tool']}")

    _report(rows, model)


def _report(rows: list[dict], model: str) -> None:
    def rate(subset: list[dict], key: str) -> str:
        called = [r for r in subset if r.get("called_tool")]
        if not called:
            return "  —  "
        return f"{sum(1 for r in called if r.get(key)) / len(called) * 100:5.1f}%"

    print("\n" + "═" * 72)
    print(f"RÉSULTATS — {model}")
    print("═" * 72)

    for variant in ("full", "subset"):
        subset = [r for r in rows if r["variant"] == variant]
        n = len(subset)
        errors = sum(1 for r in subset if "error" in r)
        called = sum(1 for r in subset if r.get("called_tool"))
        avg_ms = sum(r.get("elapsed", 0) for r in subset) / max(1, n) * 1000
        print(f"\n  Variante « {variant} » ({'49 outils' if variant == 'full' else '5-10 outils, filtrés par domaine'})")
        print(f"    Appels d'outil déclenchés : {called}/{n}")
        print(f"    JSON valide (parmi les appels) : {rate(subset, 'valid_json')}")
        print(f"    Bon outil choisi (parmi les appels) : {rate(subset, 'correct_tool')}")
        print(f"    Arguments complets (parmi les appels corrects) :",
              rate([r for r in subset if r.get('correct_tool')], 'args_complete'))
        print(f"    Erreurs réseau/API : {errors}")
        print(f"    Latence moyenne : {avg_ms:.0f} ms")

    out_path = Path(__file__).resolve().parent / f"tool_test_results_{model.replace(':', '-')}.json"
    out_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nDétail complet : {out_path}")
    print("═" * 72)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=config.OLLAMA_MODEL, help="Modèle Ollama à tester")
    parser.add_argument("-v", "--verbose", action="store_true", help="Affiche aussi les réussites")
    args = parser.parse_args()
    run(args.model, args.verbose)

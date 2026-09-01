"""Outils « natifs brain » : exécutés directement dans le process brain,
sans dispatch réseau vers un appareil — pour tout ce qui porte sur un
compte externe (Google Calendar…) plutôt que sur une machine précise.

Miroir de agents/desktop/tools/registry.py (mêmes formes PC_TOOLS/execute/
to_claude_tools) mais un registre séparé : brain/core/agent.py fusionne les
deux listes de schémas, et route chaque tool_use vers le bon exécuteur
(réseau vs local) selon le nom, voir NAMES ci-dessous.
"""
from __future__ import annotations

from brain.integrations import google_calendar, store

BRAIN_TOOLS = [
    {
        "name": "calendar_events",
        "description": (
            "Consulte l'agenda Google Calendar de Monsieur (tous les comptes connectés, "
            "fusionnés). Utilise pour « qu'est-ce que j'ai aujourd'hui/demain/cette semaine ? », "
            "un rappel d'événement, un briefing matinal."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "range": {
                    "type": "string",
                    "enum": ["today", "tomorrow", "week"],
                    "description": "Période à consulter. Défaut : today.",
                },
            },
        },
    },
]

NAMES = {t["name"] for t in BRAIN_TOOLS}


def to_claude_tools() -> list:
    return [dict(t) for t in BRAIN_TOOLS]


def _format_events(events: list[dict]) -> str:
    if not events:
        return "Aucun événement sur cette période, Monsieur."
    lines = []
    for e in events:
        when = e["start"] or "?"
        if not e["all_day"] and when != "?":
            # "2026-08-31T14:00:00+02:00" → "14:00" pour rester lisible à
            # l'oral ; la date complète n'apporte rien pour "aujourd'hui".
            when = when[11:16] if "T" in when else when
        elif e["all_day"]:
            when = "toute la journée"
        loc = f" ({e['location']})" if e.get("location") else ""
        acct = f" [{e['account']}]" if len(events) > 1 and len({ev['account'] for ev in events}) > 1 else ""
        lines.append(f"- {when} : {e['summary']}{loc}{acct}")
    return "\n".join(lines)


def execute(name: str, args: dict):
    if name == "calendar_events":
        if not google_calendar.configured():
            return "Google Calendar n'est pas configuré, Monsieur — aucun compte connecté."
        if not store.list_public("google_calendar"):
            return "Aucun compte Google connecté — ajoute-en un depuis la Console (Intégrations), Monsieur."
        time_min, time_max = google_calendar.range_for(args.get("range", "today"))
        events = google_calendar.list_events(time_min, time_max)
        return _format_events(events)
    return f"Outil brain inconnu : {name}"

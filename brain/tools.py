"""Outils « natifs brain » : exécutés directement dans le process brain,
sans dispatch réseau vers un appareil — pour tout ce qui porte sur un
compte externe (Google Calendar, Google Drive…) plutôt que sur une machine
précise.

Miroir de agents/desktop/tools/registry.py (mêmes formes PC_TOOLS/execute/
to_claude_tools) mais un registre séparé : brain/core/agent.py fusionne les
deux listes de schémas, et route chaque tool_use vers le bon exécuteur
(réseau vs local) selon le nom, voir NAMES ci-dessous.
"""
from __future__ import annotations

from brain.integrations import google_calendar, google_drive, store

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
    {
        "name": "drive_search",
        "description": (
            "Cherche des fichiers dans le Google Drive de Monsieur (tous les comptes "
            "connectés, fusionnés) — par nom ou contenu. Sans `query`, retourne les "
            "fichiers les plus récemment modifiés. Chaque résultat inclut un `id` (à "
            "réutiliser tel quel avec drive_read pour lire son contenu) et un lien "
            "`webViewLink` (à réutiliser tel quel avec open_url si Monsieur demande "
            "d'ouvrir le fichier dans le navigateur/un onglet). Pour « trouve-moi "
            "l'info importante sur X » ou « résume/analyse le fichier Y » : cherche "
            "d'abord ici, puis appelle drive_read sur le(s) résultat(s) pertinent(s) "
            "avant de répondre — ne réponds jamais à partir du seul nom de fichier."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Terme à chercher dans le nom ou le contenu. Omis = fichiers récents."},
            },
        },
    },
    {
        "name": "drive_read",
        "description": (
            "Lit et retourne le contenu textuel d'un fichier Google Drive (Docs, Sheets, "
            "Slides, PDF, texte brut) à partir de son `id` — utilise EXACTEMENT l'id "
            "retourné par drive_search, jamais un id deviné. Utilise pour comprendre, "
            "résumer, extraire une information précise, ou répondre à une question sur "
            "le contenu d'un fichier. Renvoie une erreur explicite pour les types non "
            "lisibles (image, vidéo, fichier trop volumineux) — dans ce cas propose "
            "d'ouvrir le lien avec open_url plutôt que d'inventer un contenu."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Id du fichier, tel que retourné par drive_search."},
            },
            "required": ["id"],
        },
    },
    {
        "name": "drive_create",
        "description": (
            "Crée un NOUVEAU fichier texte sur le Google Drive de Monsieur (note, résumé, "
            "brouillon dicté…). Déclenche une confirmation à l'écran dans la Console web "
            "avant d'écrire quoi que ce soit — l'action peut être refusée ou expirer sans "
            "réponse (30-90s), dans ce cas dis-le simplement, ne réessaie pas seul. "
            "Cible le premier compte Drive connecté sauf si `account` précise un email/nom "
            "de compte que Monsieur a mentionné explicitement."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nom du fichier à créer."},
                "content": {"type": "string", "description": "Contenu texte complet du fichier."},
                "account": {"type": "string", "description": "Compte Google visé (email ou fragment), si Monsieur en a nommé un."},
            },
            "required": ["name", "content"],
        },
    },
    {
        "name": "drive_update",
        "description": (
            "Remplace ENTIÈREMENT le contenu d'un fichier Drive existant (id de "
            "drive_search) — écrase, ne fusionne pas avec l'existant : relis le fichier "
            "avec drive_read d'abord si Monsieur veut modifier plutôt que remplacer. "
            "Ne fonctionne pas sur les Docs/Sheets/Slides Google natifs (édition non "
            "prise en charge). Confirmation à l'écran obligatoire avant écriture."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Id du fichier, tel que retourné par drive_search."},
                "content": {"type": "string", "description": "Nouveau contenu texte complet, remplace l'ancien."},
            },
            "required": ["id", "content"],
        },
    },
    {
        "name": "drive_delete",
        "description": (
            "Met un fichier Drive (id de drive_search) à la corbeille — JAMAIS de "
            "suppression définitive, récupérable ~30 jours depuis Drive. Confirmation à "
            "l'écran obligatoire avant toute suppression, sans exception."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Id du fichier, tel que retourné par drive_search."},
            },
            "required": ["id"],
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


def _format_files(files: list[dict]) -> str:
    if not files:
        return "Aucun fichier trouvé, Monsieur."
    lines = []
    for f in files:
        acct = f" [{f['account']}]" if len(files) > 1 and len({fl['account'] for fl in files}) > 1 else ""
        link = f" — {f['link']}" if f.get("link") else ""
        fid = f" (id: {f['id']})" if f.get("id") else ""
        lines.append(f"- {f['name']}{acct}{link}{fid}")
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

    if name == "drive_search":
        if not google_drive.configured():
            return "Google Drive n'est pas configuré, Monsieur — aucun compte connecté."
        if not store.list_public("google_drive"):
            return "Aucun compte Google Drive connecté — ajoute-en un depuis la Console (Intégrations), Monsieur."
        files = google_drive.search(args.get("query") or None)
        return _format_files(files)

    if name == "drive_read":
        if not store.list_public("google_drive"):
            return "Aucun compte Google Drive connecté — ajoute-en un depuis la Console (Intégrations), Monsieur."
        file_id = args.get("id", "")
        if not file_id:
            return "Id de fichier manquant, Monsieur — appelle d'abord drive_search."
        result = google_drive.read_file(file_id)
        if "error" in result:
            return result["error"]
        text = result["text"]
        if result["truncated"]:
            text += f"\n\n[… contenu tronqué, {result['name']} est plus long que ce qui a été lu ici]"
        return f"— {result['name']} ({result['mime_type']}) —\n{text}"

    if name == "drive_create":
        if not store.list_public("google_drive"):
            return "Aucun compte Google Drive connecté — ajoute-en un depuis la Console (Intégrations), Monsieur."
        result = google_drive.create_file(args.get("name", ""), args.get("content", ""), args.get("account"))
        if "error" in result:
            return result["error"]
        return f"Créé : {result['name']}" + (f" — {result['link']}" if result.get("link") else "")

    if name == "drive_update":
        if not args.get("id"):
            return "Id de fichier manquant, Monsieur — appelle d'abord drive_search."
        result = google_drive.update_file(args["id"], args.get("content", ""))
        if "error" in result:
            return result["error"]
        return f"Contenu remplacé : {result['name']}"

    if name == "drive_delete":
        if not args.get("id"):
            return "Id de fichier manquant, Monsieur — appelle d'abord drive_search."
        result = google_drive.trash_file(args["id"])
        if "error" in result:
            return result["error"]
        return f"Mis à la corbeille : {result['name']} (récupérable ~30 jours depuis Drive)."

    return f"Outil brain inconnu : {name}"

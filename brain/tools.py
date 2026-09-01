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

from brain.integrations import google_calendar, google_contacts, google_drive, google_gmail, jellyfin, spotify, store, tisseo, zoho_mail

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
    {
        "name": "gmail_search",
        "description": (
            "Cherche des mails dans la boîte Gmail de Monsieur (tous les comptes connectés, "
            "fusionnés). `query` accepte la syntaxe de recherche Gmail native : "
            "'is:unread', 'from:x@y.com', 'subject:facture', 'newer_than:7d', "
            "'has:attachment', combinables. Vide = boîte de réception récente. Chaque "
            "résultat inclut un `id` (à réutiliser avec gmail_read pour le contenu "
            "complet, ou gmail_draft pour répondre). Pour « j'ai des mails importants ? » "
            "essaie 'is:unread' ou 'is:important' d'abord."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Recherche Gmail (syntaxe native). Omis = boîte de réception récente."},
            },
        },
    },
    {
        "name": "gmail_read",
        "description": (
            "Lit le contenu complet d'un mail (expéditeur, destinataire, sujet, corps) à "
            "partir de son `id` — utilise EXACTEMENT l'id retourné par gmail_search. "
            "Utilise pour comprendre/résumer un mail ou répondre à une question sur son "
            "contenu — ne réponds jamais à partir du seul aperçu (snippet) de gmail_search."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Id du message, tel que retourné par gmail_search."},
            },
            "required": ["id"],
        },
    },
    {
        "name": "gmail_draft",
        "description": (
            "Crée un BROUILLON Gmail — jamais envoyé automatiquement, Monsieur le relira "
            "dans Gmail ou via gmail_send. Aucune confirmation nécessaire pour créer un "
            "brouillon (rien ne part). Si `reply_to_id` est fourni (id d'un mail lu via "
            "gmail_search/gmail_read), le brouillon répond dans le même fil — sujet et "
            "destinataire déduits automatiquement si non précisés."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Adresse email du destinataire."},
                "subject": {"type": "string", "description": "Sujet du mail. Déduit si reply_to_id est fourni et laissé vide."},
                "body": {"type": "string", "description": "Corps du mail, texte brut."},
                "reply_to_id": {"type": "string", "description": "Id du mail auquel répondre (voir gmail_search), pour rattacher au bon fil."},
            },
            "required": ["to", "body"],
        },
    },
    {
        "name": "gmail_send",
        "description": (
            "Envoie un brouillon existant (id retourné par gmail_draft) — ACTION "
            "IRRÉVERSIBLE, déclenche systématiquement une confirmation à l'écran dans la "
            "Console web (destinataire + sujet affichés) avant tout envoi réel. Si refusée "
            "ou expirée, dis-le simplement, ne recrée pas le brouillon ni ne réessaie seul."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "draft_id": {"type": "string", "description": "Id du brouillon, tel que retourné par gmail_draft."},
            },
            "required": ["draft_id"],
        },
    },
    {
        "name": "zoho_search",
        "description": (
            "Cherche des mails dans la boîte Zoho Mail de Monsieur (tous les comptes "
            "connectés, fusionnés). `query` = recherche libre (objet, expéditeur, contenu) ; "
            "vide = boîte de réception récente. Chaque résultat inclut un `id` opaque à "
            "réutiliser tel quel avec zoho_read ou zoho_compose (ne jamais le modifier)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Recherche libre. Omis = boîte de réception récente."},
            },
        },
    },
    {
        "name": "zoho_read",
        "description": (
            "Lit le contenu complet d'un mail Zoho Mail (expéditeur, sujet, corps) à partir "
            "de son `id` — utilise EXACTEMENT l'id retourné par zoho_search. Ne réponds "
            "jamais à partir du seul aperçu de zoho_search."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Id du message, tel que retourné par zoho_search."},
            },
            "required": ["id"],
        },
    },
    {
        "name": "zoho_compose",
        "description": (
            "Compose un mail via Zoho Mail (nouveau message, pas de réponse dans un fil pour "
            "l'instant). ATTENTION : contrairement à Gmail, l'API Zoho ne garantit pas une "
            "séparation nette entre « brouillon » et « envoi » — ce mail peut partir "
            "directement. Déclenche donc TOUJOURS une confirmation à l'écran avant d'agir, "
            "qui le dit explicitement. Si refusée ou expirée, dis-le simplement, ne réessaie "
            "pas seul."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Adresse email du destinataire."},
                "subject": {"type": "string", "description": "Sujet du mail."},
                "body": {"type": "string", "description": "Corps du mail, texte brut."},
                "account": {"type": "string", "description": "Compte Zoho visé (email ou fragment), si Monsieur en a nommé un."},
            },
            "required": ["to", "subject", "body"],
        },
    },
    {
        "name": "spotify_now_playing",
        "description": "Ce qui joue actuellement sur Spotify (titre, artiste, album, en pause ou non). Utilise pour « c'est quoi ce titre ? », « qu'est-ce qui joue ? ».",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "spotify_play",
        "description": (
            "Lance la lecture sur Spotify — cherche d'abord dans les playlists personnelles "
            "de Monsieur, sinon dans le catalogue public (titre, playlist, album, artiste), et "
            "démarre le premier résultat pertinent sur l'appareil Spotify actif. Utilise pour "
            "« mets ma playlist détente », « joue X de Y », « lance de la musique ». Si aucun "
            "appareil Spotify n'est actif (app fermée partout), l'erreur le dit clairement — "
            "ne réessaie pas en boucle, dis-le à Monsieur."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Ce que Monsieur veut écouter (titre, artiste, nom de playlist…)."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "spotify_control",
        "description": "Contrôle la lecture Spotify en cours : pause, reprise, morceau suivant/précédent.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["pause", "resume", "next", "previous"], "description": "Action à effectuer."},
            },
            "required": ["action"],
        },
    },
    {
        "name": "spotify_volume",
        "description": "Règle le volume de lecture Spotify (pas le volume Windows — voir les outils système pour ça).",
        "input_schema": {
            "type": "object",
            "properties": {
                "percent": {"type": "integer", "description": "Volume cible, 0 à 100."},
            },
            "required": ["percent"],
        },
    },
    {
        "name": "contacts_search",
        "description": (
            "Cherche un contact par nom dans les carnets d'adresses Google connectés "
            "(tous comptes confondus) — retourne téléphone(s), email(s), organisation. "
            "Utilise pour « le numéro de X », « l'email de X », avant d'appeler quelqu'un "
            "ou d'envoyer un message si Monsieur ne donne qu'un nom."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Nom (ou fragment de nom) à chercher."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "jellyfin_search",
        "description": "Cherche un film, une série, un épisode ou une piste audio dans la bibliothèque Jellyfin de Monsieur. Utilise pour « j'ai quoi comme films avec X ? », « cherche la série Y ».",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Titre ou terme à chercher."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "jellyfin_now_playing",
        "description": "Ce qui est en cours de lecture sur le serveur Jellyfin de Monsieur (tous appareils). Utilise pour « qu'est-ce qui joue sur Jellyfin ? ».",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "jellyfin_continue_watching",
        "description": "Liste « reprendre la lecture » de Jellyfin — ce que Monsieur a commencé sans finir. Utilise pour « qu'est-ce que j'étais en train de regarder ? ».",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "jellyfin_recently_added",
        "description": "Derniers films/séries/épisodes ajoutés à la bibliothèque Jellyfin. Utilise pour « qu'est-ce qu'il y a de nouveau sur Jellyfin ? ».",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "tisseo_next",
        "description": (
            "Prochains passages de bus/métro/tram pour les arrêts favoris enregistrés par "
            "Monsieur (tous fusionnés, ou un seul si `stop` filtre par nom). Utilise pour "
            "« quand passe le prochain bus ? », « le métro dans combien de temps ? »."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "stop": {"type": "string", "description": "Nom (ou fragment) de l'arrêt favori visé, si Monsieur en a plusieurs et en nomme un précis."},
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


def _format_messages(messages: list[dict]) -> str:
    if not messages:
        return "Aucun mail trouvé, Monsieur."
    lines = []
    for m in messages:
        acct = f" [{m['account']}]" if len(messages) > 1 and len({ms['account'] for ms in messages}) > 1 else ""
        flag = " ●non lu" if m.get("unread") else ""
        mid = f" (id: {m['id']})" if m.get("id") else ""
        lines.append(f"- {m['subject']} — de {m['from']}{flag}{acct} : {m['snippet']}{mid}")
    return "\n".join(lines)


def _format_contacts(contacts: list[dict]) -> str:
    if not contacts:
        return "Aucun contact trouvé, Monsieur."
    lines = []
    for c in contacts:
        acct = f" [{c['account']}]" if len(contacts) > 1 and len({ct['account'] for ct in contacts}) > 1 else ""
        phones = ", ".join(c["phones"]) if c.get("phones") else "pas de téléphone"
        emails = f" — {', '.join(c['emails'])}" if c.get("emails") else ""
        org = f" ({c['organization']})" if c.get("organization") else ""
        lines.append(f"- {c['name']}{org}{acct} : {phones}{emails}")
    return "\n".join(lines)


def _jellyfin_error(items: list[dict]) -> str | None:
    if items and "error" in items[0]:
        return items[0]["error"]
    return None


def _format_jellyfin_items(items: list[dict]) -> str:
    if not items:
        return "Rien trouvé, Monsieur."
    lines = []
    for it in items:
        title = it["name"] if it.get("series") is None else f"{it['series']} — {it['name']}"
        year = f" ({it['year']})" if it.get("year") else ""
        lines.append(f"- {title}{year} [{it.get('type', '')}]")
    return "\n".join(lines)


def _format_jellyfin_sessions(sessions: list[dict]) -> str:
    if not sessions:
        return "Rien ne joue actuellement sur Jellyfin, Monsieur."
    lines = []
    for s in sessions:
        title = s["title"] if not s.get("series") else f"{s['series']} — {s['title']}"
        state = "en pause" if s.get("paused") else "en lecture"
        lines.append(f"- {title} ({state}) — {s.get('user', '')} sur {s.get('device', '')}")
    return "\n".join(lines)


def _format_departures(departures: list[dict]) -> str:
    if not departures:
        return "Aucun passage trouvé, Monsieur."
    if len(departures) == 1 and "error" in departures[0]:
        return departures[0]["error"]
    lines = []
    for d in departures:
        if "error" in d:
            lines.append(f"- {d['stop']} : [erreur : {d['error']}]")
            continue
        when = f" dans {d['waiting']}" if d.get("waiting") else f" à {d.get('datetime', '?')}"
        lines.append(f"- {d['stop']} — ligne {d.get('line', '?')} vers {d.get('destination', '?')}{when}")
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

    if name == "gmail_search":
        if not google_gmail.configured():
            return "Gmail n'est pas configuré, Monsieur — aucun compte connecté."
        if not store.list_public("gmail"):
            return "Aucun compte Gmail connecté — ajoute-en un depuis la Console (Intégrations), Monsieur."
        messages = google_gmail.search(args.get("query") or None)
        return _format_messages(messages)

    if name == "gmail_read":
        if not store.list_public("gmail"):
            return "Aucun compte Gmail connecté — ajoute-en un depuis la Console (Intégrations), Monsieur."
        message_id = args.get("id", "")
        if not message_id:
            return "Id de message manquant, Monsieur — appelle d'abord gmail_search."
        result = google_gmail.read_message(message_id)
        if "error" in result:
            return result["error"]
        text = result["text"]
        if result["truncated"]:
            text += "\n\n[… contenu tronqué, le mail est plus long que ce qui a été lu ici]"
        return f"De : {result['from']}\nÀ : {result['to']}\nSujet : {result['subject']}\nDate : {result['date']}\n\n{text}"

    if name == "gmail_draft":
        if not store.list_public("gmail"):
            return "Aucun compte Gmail connecté — ajoute-en un depuis la Console (Intégrations), Monsieur."
        result = google_gmail.create_draft(
            args.get("to", ""), args.get("subject", ""), args.get("body", ""),
            reply_to_id=args.get("reply_to_id"),
        )
        if "error" in result:
            return result["error"]
        return f"Brouillon créé : « {result['subject']} » à {result['to']} (id: {result['draft_id']})."

    if name == "gmail_send":
        draft_id = args.get("draft_id", "")
        if not draft_id:
            return "Id de brouillon manquant, Monsieur — appelle d'abord gmail_draft."
        result = google_gmail.send_draft(draft_id)
        if "error" in result:
            return result["error"]
        return f"Envoyé : « {result['subject']} » à {result['to']}."

    if name == "zoho_search":
        if not zoho_mail.configured():
            return "Zoho Mail n'est pas configuré, Monsieur — aucun compte connecté."
        if not store.list_public("zoho_mail"):
            return "Aucun compte Zoho Mail connecté — ajoute-en un depuis la Console (Intégrations), Monsieur."
        messages = zoho_mail.search(args.get("query") or None)
        return _format_messages(messages)

    if name == "zoho_read":
        if not store.list_public("zoho_mail"):
            return "Aucun compte Zoho Mail connecté — ajoute-en un depuis la Console (Intégrations), Monsieur."
        message_id = args.get("id", "")
        if not message_id:
            return "Id de message manquant, Monsieur — appelle d'abord zoho_search."
        result = zoho_mail.read_message(message_id)
        if "error" in result:
            return result["error"]
        text = result["text"]
        if result["truncated"]:
            text += "\n\n[… contenu tronqué, le mail est plus long que ce qui a été lu ici]"
        return f"De : {result['from']}\nSujet : {result['subject']}\nDate : {result['date']}\n\n{text}"

    if name == "zoho_compose":
        if not store.list_public("zoho_mail"):
            return "Aucun compte Zoho Mail connecté — ajoute-en un depuis la Console (Intégrations), Monsieur."
        result = zoho_mail.create_draft(args.get("to", ""), args.get("subject", ""), args.get("body", ""), args.get("account"))
        if "error" in result:
            return result["error"]
        return f"Composé : « {result['subject']} » à {result['to']} depuis {result['account']}."

    if name == "spotify_now_playing":
        if not store.list_public("spotify"):
            return "Aucun compte Spotify connecté — ajoute-en un depuis la Console (Intégrations), Monsieur."
        result = spotify.now_playing()
        if "error" in result:
            return result["error"]
        if "track" not in result:
            return "Rien ne joue actuellement, Monsieur."
        state = "en lecture" if result["playing"] else "en pause"
        return f"{result['track']} — {result['artists']} ({result['album']}), {state}."

    if name == "spotify_play":
        if not store.list_public("spotify"):
            return "Aucun compte Spotify connecté — ajoute-en un depuis la Console (Intégrations), Monsieur."
        result = spotify.play(args.get("query", ""))
        if "error" in result:
            return result["error"]
        return f"Lecture lancée : {result['name']} ({result['type']})."

    if name == "spotify_control":
        if not store.list_public("spotify"):
            return "Aucun compte Spotify connecté — ajoute-en un depuis la Console (Intégrations), Monsieur."
        result = spotify.control(args.get("action", ""))
        if "error" in result:
            return result["error"]
        return f"Fait : {result['action']}."

    if name == "spotify_volume":
        if not store.list_public("spotify"):
            return "Aucun compte Spotify connecté — ajoute-en un depuis la Console (Intégrations), Monsieur."
        result = spotify.set_volume(int(args.get("percent", 50)))
        if "error" in result:
            return result["error"]
        return f"Volume Spotify réglé à {result['percent']}%."

    if name == "contacts_search":
        if not google_contacts.configured():
            return "Google Contacts n'est pas configuré, Monsieur — aucun compte connecté."
        if not store.list_public("google_contacts"):
            return "Aucun compte Google Contacts connecté — ajoute-en un depuis la Console (Intégrations), Monsieur."
        contacts = google_contacts.search(args.get("query", ""))
        return _format_contacts(contacts)

    if name == "jellyfin_search":
        if not store.list_public("jellyfin"):
            return "Aucun serveur Jellyfin connecté — ajoute-en un depuis la Console (Intégrations), Monsieur."
        items = jellyfin.search(args.get("query", ""))
        return _jellyfin_error(items) or _format_jellyfin_items(items)

    if name == "jellyfin_now_playing":
        if not store.list_public("jellyfin"):
            return "Aucun serveur Jellyfin connecté — ajoute-en un depuis la Console (Intégrations), Monsieur."
        sessions = jellyfin.now_playing()
        return _jellyfin_error(sessions) or _format_jellyfin_sessions(sessions)

    if name == "jellyfin_continue_watching":
        if not store.list_public("jellyfin"):
            return "Aucun serveur Jellyfin connecté — ajoute-en un depuis la Console (Intégrations), Monsieur."
        items = jellyfin.continue_watching()
        return _jellyfin_error(items) or _format_jellyfin_items(items)

    if name == "jellyfin_recently_added":
        if not store.list_public("jellyfin"):
            return "Aucun serveur Jellyfin connecté — ajoute-en un depuis la Console (Intégrations), Monsieur."
        items = jellyfin.recently_added()
        return _jellyfin_error(items) or _format_jellyfin_items(items)

    if name == "tisseo_next":
        if not tisseo.configured():
            return "Tisséo n'est pas configuré, Monsieur — aucune clé API renseignée."
        if not store.list_public("tisseo"):
            return "Aucun arrêt favori enregistré — ajoute-en un depuis la Console (Intégrations), Monsieur."
        departures = tisseo.next_departures(args.get("stop"))
        return _format_departures(departures)

    return f"Outil brain inconnu : {name}"

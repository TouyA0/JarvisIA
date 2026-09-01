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

from brain import cards, config, diagnostics, weather
from brain.integrations import brave_search, google_calendar, google_contacts, google_drive, google_gmail, home_assistant, jellyfin, ors, spotify, store, tisseo, zoho_mail

# Chaque outil qui rapporte de la donnée structurée émet, en plus du texte
# destiné à la voix, une **carte** que la Console affiche (voir brain/cards.py
# et docs/ROADMAP_DISPLAY_INTEGRATIONS.md §2). Le texte reste la source de
# vérité pour Claude et pour la synthèse vocale : la carte ne le remplace pas,
# elle le double à l'écran.
_RANGE_TITLES = {"today": "Aujourd'hui", "tomorrow": "Demain", "week": "Cette semaine"}

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
    {
        "name": "directions",
        "description": (
            "Calcule la distance et le temps de trajet entre deux adresses (OpenRouteService, "
            "voiture/vélo/à pied). Utilise pour « combien de temps pour aller à X ? », "
            "« la distance jusqu'à Y ». Si Monsieur ne précise QUE la destination, omets "
            "`origin` — l'outil utilise automatiquement son adresse domicile enregistrée si "
            "elle existe (et le dit dans l'erreur sinon, plutôt que d'inventer un point de "
            "départ)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "origin": {"type": "string", "description": "Adresse ou lieu de départ. Omis = adresse domicile de Monsieur si configurée."},
                "destination": {"type": "string", "description": "Adresse ou lieu d'arrivée, en texte libre."},
                "mode": {"type": "string", "enum": ["voiture", "vélo", "à pied"], "description": "Moyen de transport. Défaut : voiture."},
            },
            "required": ["destination"],
        },
    },
    {
        "name": "ha_state",
        "description": (
            "Consulte l'état de TOUTES les entités Home Assistant dont le nom correspond "
            "(pas juste la première) — utile pour un domaine entier plutôt qu'un seul appareil : "
            "« le serveur » peut retourner CPU/RAM/température/disque comme plusieurs entités "
            "distinctes, chacune avec tous ses attributs (pas juste l'état brut). Utilise pour "
            "« est-ce que X est allumé ? », « quelle température ? », « qu'est-ce qui se passe "
            "avec Y ? »."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entity": {"type": "string", "description": "Nom (ou fragment) de l'appareil/capteur/domaine, en texte libre (friendly_name Home Assistant)."},
            },
            "required": ["entity"],
        },
    },
    {
        "name": "ha_list_all",
        "description": (
            "Liste TOUTES les entités Home Assistant (ou filtrées par domaine technique : "
            "'sensor', 'binary_sensor', 'persistent_notification', 'device_tracker'...). Utilise "
            "quand Monsieur demande un aperçu général (« qu'est-ce qui se passe sur Home "
            "Assistant ? »), pour retrouver une notification/un résumé matinal "
            "(domain='persistent_notification'), ou pour découvrir le nom exact d'une entité que "
            "ha_state ne trouve pas. Peut retourner beaucoup de résultats sans `domain` — précise-le "
            "si possible."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Domaine technique HA pour filtrer (ex. 'sensor', 'persistent_notification'). Omis = tout."},
            },
        },
    },
    {
        "name": "ha_control",
        "description": (
            "Allume/éteint/bascule un appareil Home Assistant par son nom (lumière, prise, volet, "
            "ventilateur, media player…). Pour les serrures et l'alarme, ouvrir/désarmer déclenche "
            "une confirmation à l'écran (rend la maison moins sûre) — verrouiller/armer jamais. "
            "Si refusée ou expirée, dis-le simplement, ne réessaie pas seul."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "entity": {"type": "string", "description": "Nom de l'appareil, en texte libre."},
                "action": {"type": "string", "enum": ["on", "off", "toggle"], "description": "on=allumer/verrouiller/armer, off=éteindre/déverrouiller/désarmer, toggle=basculer."},
            },
            "required": ["entity", "action"],
        },
    },
    {
        "name": "ha_set_temperature",
        "description": "Règle la consigne d'un thermostat Home Assistant par son nom. Utilise pour « mets le chauffage du salon à 20 ».",
        "input_schema": {
            "type": "object",
            "properties": {
                "entity": {"type": "string", "description": "Nom du thermostat, en texte libre."},
                "temperature": {"type": "number", "description": "Température cible en degrés Celsius."},
            },
            "required": ["entity", "temperature"],
        },
    },
    {
        "name": "ha_network_status",
        "description": "Compte les appareils en ligne/hors ligne sur le réseau (entités device_tracker Home Assistant — routeur, UniFi, etc.). Utilise pour « combien d'appareils en ligne ? », « y a-t-il des appareils inconnus connectés ? ». Requête globale, pas de nom d'entité à donner (différent de ha_state).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "weather_now",
        "description": "Météo actuelle à Toulouse (ou la ville configurée en .env). Utilise pour « quel temps fait-il ? », « il fait combien dehors ? ».",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "system_diagnostics",
        "description": "État du PC qui héberge Jarvis : CPU, RAM, disque, coût API du mois. Utilise pour « comment va le PC ? », « l'ordinateur rame ? », « combien ça m'a coûté ce mois-ci ? ».",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "web_search",
        "description": (
            "Cherche sur le web (Brave Search) — titres, liens, extraits. Utilise pour toute "
            "information récente, actuelle, ou que tu ne connais pas avec certitude : dernière "
            "version d'un logiciel, actualité, définition d'un terme récent, disponibilité d'un "
            "produit... Ne réponds JAMAIS de mémoire à une question qui dépend de la date "
            "d'aujourd'hui ou d'un événement récent — ta connaissance a une date de coupure, "
            "cherche d'abord. Pour approfondir un résultat précis, utilise ensuite fetch_page "
            "sur son lien."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Termes de recherche."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "fetch_page",
        "description": (
            "Lit le contenu texte complet d'une page web (article nettoyé de la navigation/"
            "pubs/scripts) à partir de son URL — utilise EXACTEMENT un lien retourné par "
            "web_search, ou une URL que Monsieur a donnée directement. Utilise pour « résume "
            "cette page/cet article », ou pour répondre à une question précise dont web_search "
            "seul (juste des extraits courts) ne suffit pas. Peut échouer sur une page purement "
            "en JavaScript, un PDF, ou un contenu payant — dans ce cas dis-le, n'invente rien."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL complète de la page à lire."},
            },
            "required": ["url"],
        },
    },
]

NAMES = {t["name"] for t in BRAIN_TOOLS}


def to_claude_tools() -> list:
    return [dict(t) for t in BRAIN_TOOLS]


def _plural(count: int, word: str) -> str:
    """Sous-titre de carte : « 3 événements », « 1 fichier ». Uniquement
    cosmétique — le texte lu à voix haute ne passe pas par ici."""
    return f"{count} {word}" + ("s" if count > 1 else "")


def _music_actions(playing: bool) -> list[dict]:
    """Boutons de la carte "music" — appellent /api/tools/execute (voir
    server.py::execute_tool), donc directement spotify_control sans repasser
    par Claude. `playing` détermine si on propose pause ou reprise."""
    pause_action = {"action": "pause"} if playing else {"action": "resume"}
    pause_label = "Pause" if playing else "Lecture"
    pause_icon = "pause" if playing else "play"
    return [
        {"label": "Précédent", "icon": "skip-prev", "tool": "spotify_control", "args": {"action": "previous"}},
        {"label": pause_label, "icon": pause_icon, "tool": "spotify_control", "args": pause_action},
        {"label": "Suivant", "icon": "skip-next", "tool": "spotify_control", "args": {"action": "next"}},
    ]


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


def _format_ha_entities(entities: list[dict], limit_note: bool = False) -> str:
    if not entities:
        return "Aucune entité trouvée, Monsieur."
    if len(entities) == 1 and "error" in entities[0]:
        return entities[0]["error"]
    lines = []
    for e in entities:
        if "error" in e:
            lines.append(f"- [erreur : {e['error']}]")
            continue
        attrs = ", ".join(f"{k}={v}" for k, v in e.get("attributes", {}).items()) if e.get("attributes") else ""
        extra = f" ({attrs})" if attrs else ""
        lines.append(f"- {e['name']} [{e['entity_id']}] : {e['state']}{extra}")
    if limit_note and len(entities) >= 50:
        lines.append("[… liste tronquée, précise un domaine pour affiner]")
    return "\n".join(lines)


def _format_search_results(results: list[dict]) -> str:
    if not results:
        return "Aucun résultat, Monsieur."
    if len(results) == 1 and "error" in results[0]:
        return results[0]["error"]
    lines = []
    for r in results:
        if "error" in r:
            lines.append(f"- [erreur : {r['error']}]")
            continue
        lines.append(f"- {r['title']} — {r['url']}\n  {r['snippet']}")
    return "\n".join(lines)


def execute(name: str, args: dict):
    if name == "calendar_events":
        if not google_calendar.configured():
            return "Google Calendar n'est pas configuré, Monsieur — aucun compte connecté."
        if not store.list_public("google_calendar"):
            return "Aucun compte Google connecté — ajoute-en un depuis la Console (Intégrations), Monsieur."
        period = args.get("range", "today")
        time_min, time_max = google_calendar.range_for(period)
        events = google_calendar.list_events(time_min, time_max)
        cards.emit("agenda", _RANGE_TITLES.get(period, "Agenda"),
                   {"events": events, "range": period},
                   subtitle=_plural(len(events), "événement"))
        return _format_events(events)

    if name == "drive_search":
        if not google_drive.configured():
            return "Google Drive n'est pas configuré, Monsieur — aucun compte connecté."
        if not store.list_public("google_drive"):
            return "Aucun compte Google Drive connecté — ajoute-en un depuis la Console (Intégrations), Monsieur."
        files = google_drive.search(args.get("query") or None)
        cards.emit("files", args.get("query") or "Fichiers récents", {"files": files},
                   subtitle="Drive · " + _plural(len(files), "fichier"))
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
        cards.emit("document", result["name"],
                   {"text": text, "mime_type": result["mime_type"],
                    "truncated": result["truncated"]},
                   subtitle="Google Drive")
        if result["truncated"]:
            text += f"\n\n[… contenu tronqué, {result['name']} est plus long que ce qui a été lu ici]"
        return f"— {result['name']} ({result['mime_type']}) —\n{text}"

    if name == "drive_create":
        if not store.list_public("google_drive"):
            return "Aucun compte Google Drive connecté — ajoute-en un depuis la Console (Intégrations), Monsieur."
        result = google_drive.create_file(args.get("name", ""), args.get("content", ""), args.get("account"))
        if "error" in result:
            return result["error"]
        cards.emit("document", result["name"],
                   {"text": args.get("content", ""), "mime_type": "text/plain", "truncated": False},
                   subtitle="Créé sur Drive")
        return f"Créé : {result['name']}" + (f" — {result['link']}" if result.get("link") else "")

    if name == "drive_update":
        if not args.get("id"):
            return "Id de fichier manquant, Monsieur — appelle d'abord drive_search."
        result = google_drive.update_file(args["id"], args.get("content", ""))
        if "error" in result:
            return result["error"]
        cards.emit("document", result["name"],
                   {"text": args.get("content", ""), "mime_type": "text/plain", "truncated": False},
                   subtitle="Modifié sur Drive")
        return f"Contenu remplacé : {result['name']}"

    if name == "drive_delete":
        if not args.get("id"):
            return "Id de fichier manquant, Monsieur — appelle d'abord drive_search."
        result = google_drive.trash_file(args["id"])
        if "error" in result:
            return result["error"]
        cards.emit("document", result["name"], {"text": "Mis à la corbeille.", "mime_type": "", "truncated": False},
                   subtitle="Corbeille Drive · récupérable ~30 jours")
        return f"Mis à la corbeille : {result['name']} (récupérable ~30 jours depuis Drive)."

    if name == "gmail_search":
        if not google_gmail.configured():
            return "Gmail n'est pas configuré, Monsieur — aucun compte connecté."
        if not store.list_public("gmail"):
            return "Aucun compte Gmail connecté — ajoute-en un depuis la Console (Intégrations), Monsieur."
        messages = google_gmail.search(args.get("query") or None)
        cards.emit("mail", args.get("query") or "Derniers mails",
                   {"messages": messages, "service": "Gmail"},
                   subtitle="Gmail · " + _plural(len(messages), "message"))
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
        cards.emit("mail_detail", result["subject"] or "(sans objet)",
                   {"from": result["from"], "to": result.get("to", ""),
                    "date": result.get("date", ""), "text": text, "service": "Gmail"},
                   subtitle="De " + result["from"])
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
        cards.emit("mail", args.get("query") or "Derniers mails",
                   {"messages": messages, "service": "Zoho Mail"},
                   subtitle="Zoho Mail · " + _plural(len(messages), "message"))
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
        cards.emit("mail_detail", result["subject"] or "(sans objet)",
                   {"from": result["from"], "to": result.get("to", ""),
                    "date": result.get("date", ""), "text": text, "service": "Zoho Mail"},
                   subtitle="De " + result["from"])
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
        cards.emit("music", result["track"], result, subtitle=result["artists"],
                   actions=_music_actions(result["playing"]))
        return f"{result['track']} — {result['artists']} ({result['album']}), {state}."

    if name == "spotify_play":
        if not store.list_public("spotify"):
            return "Aucun compte Spotify connecté — ajoute-en un depuis la Console (Intégrations), Monsieur."
        result = spotify.play(args.get("query", ""))
        if "error" in result:
            return result["error"]
        cards.emit("music", result["name"],
                   {"track": result["name"], "artists": "", "playing": True},
                   subtitle="Lecture lancée · " + result["type"], actions=_music_actions(True))
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
        cards.emit("contacts", args.get("query", "") or "Contacts", {"contacts": contacts},
                   subtitle=_plural(len(contacts), "contact"))
        return _format_contacts(contacts)

    if name == "jellyfin_search":
        if not store.list_public("jellyfin"):
            return "Aucun serveur Jellyfin connecté — ajoute-en un depuis la Console (Intégrations), Monsieur."
        items = jellyfin.search(args.get("query", ""))
        error = _jellyfin_error(items)
        if not error:
            cards.emit("media", args.get("query", "") or "Médiathèque", {"items": items},
                       subtitle="Jellyfin · " + _plural(len(items), "titre"))
        return error or _format_jellyfin_items(items)

    if name == "jellyfin_now_playing":
        if not store.list_public("jellyfin"):
            return "Aucun serveur Jellyfin connecté — ajoute-en un depuis la Console (Intégrations), Monsieur."
        sessions = jellyfin.now_playing()
        return _jellyfin_error(sessions) or _format_jellyfin_sessions(sessions)

    if name == "jellyfin_continue_watching":
        if not store.list_public("jellyfin"):
            return "Aucun serveur Jellyfin connecté — ajoute-en un depuis la Console (Intégrations), Monsieur."
        items = jellyfin.continue_watching()
        error = _jellyfin_error(items)
        if not error:
            cards.emit("media", "Reprendre la lecture", {"items": items},
                       subtitle="Jellyfin · " + _plural(len(items), "titre"))
        return error or _format_jellyfin_items(items)

    if name == "jellyfin_recently_added":
        if not store.list_public("jellyfin"):
            return "Aucun serveur Jellyfin connecté — ajoute-en un depuis la Console (Intégrations), Monsieur."
        items = jellyfin.recently_added()
        error = _jellyfin_error(items)
        if not error:
            cards.emit("media", "Ajouts récents", {"items": items},
                       subtitle="Jellyfin · " + _plural(len(items), "titre"))
        return error or _format_jellyfin_items(items)

    if name == "tisseo_next":
        if not tisseo.configured():
            return "Tisséo n'est pas configuré, Monsieur — aucune clé API renseignée."
        if not store.list_public("tisseo"):
            return "Aucun arrêt favori enregistré — ajoute-en un depuis la Console (Intégrations), Monsieur."
        departures = tisseo.next_departures(args.get("stop"))
        if not (departures and "error" in departures[0]):
            cards.emit("transport", args.get("stop") or "Prochains passages",
                       {"departures": departures}, subtitle="Tisséo")
        return _format_departures(departures)

    if name == "directions":
        if not ors.configured():
            return "OpenRouteService n'est pas configuré, Monsieur — aucune clé API renseignée."
        result = ors.directions(args.get("origin", ""), args.get("destination", ""), args.get("mode"))
        if "error" in result:
            return result["error"]
        hours = result["duration_min"] // 60
        minutes = result["duration_min"] % 60
        duration = f"{hours} h {minutes:02d}" if hours else f"{minutes} min"
        cards.emit("route", f"{result['origin']} → {result['destination']}",
                   dict(result, duration_label=duration),
                   subtitle=f"{result['distance_km']} km · {duration}")
        return (
            f"{result['distance_km']} km, environ {duration} en {result['mode']}, "
            f"de {result['origin']} à {result['destination']}."
        )

    if name == "ha_state":
        if not store.list_public("home_assistant"):
            return "Aucune instance Home Assistant connectée — ajoute-en une depuis la Console (Intégrations), Monsieur."
        entities = home_assistant.get_state(args.get("entity", ""))
        if not (entities and "error" in entities[0]):
            cards.emit("home", args.get("entity", "") or "Maison", {"entities": entities},
                       subtitle="Home Assistant")
        return _format_ha_entities(entities)

    if name == "ha_list_all":
        if not store.list_public("home_assistant"):
            return "Aucune instance Home Assistant connectée — ajoute-en une depuis la Console (Intégrations), Monsieur."
        entities = home_assistant.list_all(domain=args.get("domain"))
        if not (entities and "error" in entities[0]):
            cards.emit("home", args.get("domain") or "Toute la maison", {"entities": entities},
                       subtitle="Home Assistant · " + _plural(len(entities), "entité"))
        return _format_ha_entities(entities, limit_note=True)

    if name == "ha_control":
        if not store.list_public("home_assistant"):
            return "Aucune instance Home Assistant connectée — ajoute-en une depuis la Console (Intégrations), Monsieur."
        result = home_assistant.control(args.get("entity", ""), args.get("action", ""))
        if "error" in result:
            return result["error"]
        verbs = {"on": "allumé/verrouillé/armé", "off": "éteint/déverrouillé/désarmé", "toggle": "basculé"}
        return f"{result['name']} : {verbs.get(result['action'], result['action'])}."

    if name == "ha_set_temperature":
        if not store.list_public("home_assistant"):
            return "Aucune instance Home Assistant connectée — ajoute-en une depuis la Console (Intégrations), Monsieur."
        result = home_assistant.set_temperature(args.get("entity", ""), float(args.get("temperature", 20)))
        if "error" in result:
            return result["error"]
        return f"{result['name']} réglé à {result['temperature']}°C."

    if name == "ha_network_status":
        if not store.list_public("home_assistant"):
            return "Aucune instance Home Assistant connectée — ajoute-en une depuis la Console (Intégrations), Monsieur."
        result = home_assistant.network_status()
        if "error" in result:
            return result["error"]
        online, offline = result["online"], result["offline"]
        lines = [f"{len(online)} en ligne, {len(offline)} hors ligne."]
        if online:
            lines.append("En ligne : " + ", ".join(online))
        return "\n".join(lines)

    if name == "weather_now":
        w = weather.get()
        if not w or w["temp"] is None:
            return "Les données météo ne sont pas disponibles pour l'instant, Monsieur."
        desc = weather.description(w["code"])
        cards.emit("weather", f"{round(w['temp'])}°C", {
            "temp": w["temp"], "description": desc, "wind": w["wind"], "city": config.WEATHER_CITY,
        }, subtitle=desc.capitalize())
        return f"Il fait {round(w['temp'])} degrés à {config.WEATHER_CITY}, {desc}, Monsieur."

    if name == "system_diagnostics":
        d = diagnostics.snapshot()
        cards.emit("diagnostics", "État du système", d, subtitle=f"CPU {d['cpu']}% · RAM {d['mem']}%")
        text = (
            f"CPU à {d['cpu']}%, RAM à {d['mem']}%, disque à {d['disk']}%. "
            f"{d['month_calls']} appels API ce mois-ci, {d['month_cost_usd'] * 0.92:.2f} euros, Monsieur."
        )
        if d["local_rate"] is not None:
            text += f" {d['local_rate']}% des commandes traitées en local ce mois-ci."
        return text

    if name == "web_search":
        if not brave_search.configured():
            return "La recherche web n'est pas configurée, Monsieur — aucune clé API renseignée."
        results = brave_search.search(args.get("query", ""))
        if not (len(results) == 1 and "error" in results[0]):
            cards.emit("web_results", args.get("query", "") or "Recherche web", {"results": results},
                       subtitle=_plural(len(results), "résultat"))
        return _format_search_results(results)

    if name == "fetch_page":
        url = args.get("url", "")
        if not url:
            return "URL manquante, Monsieur."
        result = brave_search.fetch_page(url)
        if "error" in result:
            return result["error"]
        text = result["text"]
        cards.emit("document", url, {"text": text, "mime_type": "text/html", "truncated": result["truncated"]},
                   subtitle="Page web")
        if result["truncated"]:
            text += "\n\n[… contenu tronqué, la page est plus longue que ce qui a été lu ici]"
        return text

    return f"Outil brain inconnu : {name}"

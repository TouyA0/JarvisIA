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

import time

from brain import cards, config, diagnostics, preferences, weather
from brain.integrations import android_tv, brave_search, google_calendar, google_contacts, google_drive, google_gmail, home_assistant, jellyfin, ors, spotify, store, tisseo, zoho_mail

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
        "name": "jellyfin_resume_on_tv",
        "description": (
            "Reprend sur la télé du salon un épisode/film que Monsieur a commencé sans finir "
            "sur Jellyfin — pour « reprends mon épisode sur la télé », « continue la série là "
            "où j'en étais, sur le grand écran ». Cherche le titre dans la liste "
            "jellyfin_continue_watching (pas besoin d'appeler cet outil séparément avant), "
            "puis demande à la session Jellyfin déjà ouverte sur la télé de lancer la lecture "
            "à la bonne position (contrôle à distance, pas un simple lancement d'appli). Si "
            "l'appli Jellyfin n'est pas encore ouverte sur la télé, la lance d'abord puis "
            "réessaie une fois automatiquement — best effort, l'appli met parfois plus de "
            "temps à s'enregistrer comme session active : si ça échoue encore, dis-le "
            "simplement à Monsieur plutôt que de répéter la tentative."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Titre (ou fragment) de l'épisode/film/série à reprendre, tel que dans « reprendre la lecture »."},
            },
            "required": ["title"],
        },
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
    {
        "name": "tv_status",
        "description": (
            "Donne l'état réel de la télé du salon : écran allumé/éteint, application au "
            "premier plan, et ce qui joue actuellement (titre, artiste/chaîne, lecture/pause, "
            "position). Utilise pour « qu'est-ce qui joue ? », « la télé est allumée ? », "
            "« on en est où dans l'épisode/la vidéo ? » — avant ça, aucun moyen de répondre "
            "sans deviner."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "tv_volume",
        "description": (
            "Règle ou lit le son de la télé du salon (stick Android TV). Passe `direction` pour "
            "monter/baisser/couper (« monte/baisse le son de la télé », « coupe le son »), ou "
            "`level` (0-100) pour un volume absolu (« mets le son à 30 % »). Sans argument : "
            "renvoie juste le niveau actuel."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["up", "down", "mute"], "description": "Sens du réglage relatif."},
                "level": {"type": "integer", "minimum": 0, "maximum": 100, "description": "Volume absolu souhaité, en pourcentage (0-100)."},
            },
        },
    },
    {
        "name": "tv_key",
        "description": (
            "Envoie une touche de navigation ou de contrôle média à la télé (haut/bas/gauche/"
            "droite/valider/retour/accueil/lecture-pause/suivant/précédent/avance rapide/retour "
            "rapide/stop). Utilise pour naviguer dans un menu à la voix, contrôler la lecture "
            "(« piste/épisode suivant », « stoppe la lecture »), ou après tv_screen_dump pour te "
            "déplacer vers un élément plutôt que d'y taper directement. STOP déclenche une "
            "confirmation à l'écran dans la Console web avant d'agir (peut couper ce que "
            "quelqu'un regarde) — si refusée ou expirée, dis-le simplement, ne réessaie pas seul."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "enum": [
                        "DPAD_UP", "DPAD_DOWN", "DPAD_LEFT", "DPAD_RIGHT", "DPAD_CENTER",
                        "BACK", "HOME", "ENTER", "PLAY_PAUSE",
                        "NEXT", "PREVIOUS", "FAST_FORWARD", "REWIND", "STOP",
                    ],
                    "description": (
                        "Touche à envoyer. DPAD_CENTER = valider/OK. NEXT/PREVIOUS = piste ou "
                        "épisode suivant/précédent. FAST_FORWARD/REWIND = avance/retour rapide. "
                        "STOP = arrête la lecture."
                    ),
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "tv_seek",
        "description": (
            "Avance ou recule dans la lecture en cours sur la télé du salon, par un nombre de "
            "secondes approximatif (« recule de 30 secondes », « avance d'une minute »). Best "
            "effort — dépend du support de l'appli pour les touches de saut standard Android : si "
            "rien ne se passe, essaie tv_key avec FAST_FORWARD/REWIND. Pour un bouton précis dans "
            "l'appli (« saute le générique »), pas de raccourci générique : utilise tv_screen_dump "
            "puis tv_tap sur l'élément voulu."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {"type": "string", "enum": ["forward", "backward"], "description": "Sens du saut."},
                "seconds": {"type": "integer", "minimum": 1, "description": "Durée approximative à sauter, en secondes (défaut 10)."},
            },
            "required": ["direction"],
        },
    },
    {
        "name": "tv_launch_app",
        "description": (
            "Lance une application ou un contenu précis sur la télé du salon via lien profond. "
            "Pour une app seule : nom en texte libre ('youtube', 'spotify', 'netflix', 'disney+') "
            "ou nom de package Android. Pour un contenu précis DÉJÀ IDENTIFIÉ (ex. une vidéo "
            "YouTube trouvée via web_search, un titre Netflix dont tu connais l'id) : passe l'URI "
            "complète directement, ex. 'vnd.youtube://ID_VIDEO' ou "
            "'https://www.netflix.com/title/ID'. Best effort — certaines apps (Disney+ notamment) "
            "ignorent le lien profond et n'ouvrent que leur écran d'accueil. Pour les apps connues, "
            "le résultat inclut un champ 'verified' (true/false/null) basé sur l'appli réellement "
            "au premier plan après le lancement : si verified est false ou null, un champ 'text' "
            "explique quoi faire — NE RETENTE PAS le même lancement, bascule directement sur "
            "tv_screen_dump pour repérer l'icône/le champ de recherche de l'appli, tv_tap dessus, "
            "puis tv_type_text avec le titre recherché.\n"
            "IMPORTANT — appli multi-comptes (YouTube, Netflix…) : si un fait mémorisé précise "
            "quel compte/profil Monsieur veut sur cette appli, NE considère PAS la tâche terminée "
            "juste après le lancement. Appelle tv_screen_dump pour voir quel compte est affiché "
            "(nom/avatar visible parmi les éléments) ; si ce n'est pas celui attendu, cherche "
            "l'élément de sélection/changement de compte dans la liste (souvent l'avatar ou 'Compte') "
            "et tape dessus avec tv_tap, puis re-dump pour confirmer avant de répondre à Monsieur."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {"type": "string", "description": "Nom d'app, URI de lien profond, ou nom de package."},
            },
            "required": ["target"],
        },
    },
    {
        "name": "send_to_tv",
        "description": (
            "Transfère une vidéo ou une page vers la télé du salon à partir d'une URL — pour "
            "« envoie cette vidéo sur la télé », « mets ça sur la télé », « bascule ça sur le "
            "grand écran ». Appelle d'abord get_browser_url si Monsieur n'a pas donné l'URL "
            "explicitement (« cette vidéo », « cette page »). Pour YouTube, extrait "
            "automatiquement l'ID de la vidéo et l'horodatage (&t=) pour reprendre exactement "
            "où Monsieur en était. Pour toute autre page (Netflix, Prime Video, un lien "
            "quelconque), transmet l'URL directement à la télé, qui la résout vers "
            "l'application installée compatible."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL de la page/vidéo à envoyer sur la télé (ex. celle renvoyée par get_browser_url)."},
            },
            "required": ["url"],
        },
    },
    {
        "name": "tv_resume_on_pc",
        "description": (
            "Donne l'URL et la position pour reprendre sur le PC ce qui joue actuellement sur "
            "la télé du salon — pour « reprends ça sur le PC », « je continue sur mon "
            "ordinateur ». Lit la session média active de la télé (titre, position). Quand "
            "c'est reconstructible (YouTube), renvoie directement l'URL exacte avec "
            "l'horodatage : appelle ensuite open_url (outil PC) avec cette URL. Sinon (autres "
            "apps), renvoie titre/artiste/position à la place — utilise web_search pour "
            "retrouver le lien avant d'appeler open_url, n'invente jamais une URL."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "tv_apps_list",
        "description": "Liste les applications installées sur la télé du salon. Utilise avant tv_launch_app si tu n'es pas sûr qu'une app précise soit installée.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "tv_screen_dump",
        "description": (
            "Lit ce qui est affiché à l'écran de la télé sous forme de liste d'éléments "
            "(texte + position exacte, sans image) — utilise ça pour trouver un bouton, un champ "
            "de recherche, ou un résultat à sélectionner quand tv_launch_app n'a pas mené "
            "directement au bon endroit. Enchaîne avec tv_tap sur les coordonnées d'un élément, "
            "ou tv_type_text pour écrire dans un champ. Si ça échoue ('aucun élément exploitable'), "
            "utilise tv_screenshot en dernier recours.\n"
            "SOUS-TITRES / PISTE AUDIO (« mets les sous-titres », « passe en VO », « piste "
            "française ») : il n'existe AUCUNE commande générique ADB pour ça — chaque appli "
            "(Netflix, Disney+, Prime Video, YouTube…) a son propre menu. Marche à suivre : "
            "pendant la lecture, envoie DPAD_UP ou DPAD_DOWN via tv_key (ou tv_tap au centre de "
            "l'écran) pour faire apparaître les contrôles de lecture, puis tv_screen_dump pour "
            "repérer l'icône/le libellé du menu audio-sous-titres (souvent 'Audio et sous-titres', "
            "une bulle de dialogue, ou un engrenage) et tv_tap dessus ; re-dump pour lister les "
            "langues/pistes proposées, tv_tap sur celle demandée, puis re-dump une dernière fois "
            "pour confirmer avant de répondre à Monsieur. Si tv_screen_dump ne renvoie rien "
            "d'exploitable à une étape, passe par tv_screenshot pour ce même écran."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "tv_tap",
        "description": "Appuie à un endroit précis de l'écran de la télé (coordonnées obtenues via tv_screen_dump ou tv_screenshot).",
        "input_schema": {
            "type": "object",
            "properties": {
                "x": {"type": "integer", "description": "Coordonnée horizontale en pixels."},
                "y": {"type": "integer", "description": "Coordonnée verticale en pixels."},
            },
            "required": ["x", "y"],
        },
    },
    {
        "name": "tv_type_text",
        "description": "Écrit du texte dans le champ actuellement sélectionné/focus sur la télé (ex. une barre de recherche ouverte via tv_tap). Appelle tv_tap sur le champ avant si besoin.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Texte à taper."},
            },
            "required": ["text"],
        },
    },
    {
        "name": "tv_screenshot",
        "description": (
            "Prend une capture d'écran de la télé du salon — dernier recours uniquement, quand "
            "tv_screen_dump ne renvoie rien d'exploitable (interface non standard). Plus lent : "
            "regarde l'image, décide où taper (tv_tap), n'utilise pas ça en boucle plus de "
            "quelques fois de suite."
        ),
        "input_schema": {"type": "object", "properties": {}},
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


_JELLYFIN_TV_LAUNCH_DELAY_SECONDS = 4  # C4 — laisse l'appli Jellyfin le temps de
# s'enregistrer comme session active côté serveur avant de retenter resume_on_session()
# (best effort : pas de moyen de sonder "session prête", voir jellyfin.py).


def _tv_actions() -> list[dict]:
    """Boutons de la carte "tv" (T5) — même mécanique que _music_actions
    ci-dessus : chaque bouton appelle /api/tools/execute, donc directement
    tv_key/tv_volume sans repasser par la voix. Rendus par CardActions
    (CardView.jsx), pas par Tv (renderers.jsx) qui ne fait qu'afficher la
    capture/le statut."""
    return [
        {"label": "Accueil", "icon": "home", "tool": "tv_key", "args": {"command": "HOME"}},
        {"label": "Retour", "icon": "back", "tool": "tv_key", "args": {"command": "BACK"}},
        {"label": "Haut", "icon": "chevron-up", "tool": "tv_key", "args": {"command": "DPAD_UP"}},
        {"label": "Bas", "icon": "chevron-down", "tool": "tv_key", "args": {"command": "DPAD_DOWN"}},
        {"label": "Gauche", "icon": "chevron-left", "tool": "tv_key", "args": {"command": "DPAD_LEFT"}},
        {"label": "Droite", "icon": "chevron-right", "tool": "tv_key", "args": {"command": "DPAD_RIGHT"}},
        {"label": "OK", "icon": "check", "tool": "tv_key", "args": {"command": "DPAD_CENTER"}},
        {"label": "Précédent", "icon": "skip-prev", "tool": "tv_key", "args": {"command": "PREVIOUS"}},
        {"label": "Lecture", "icon": "play", "tool": "tv_key", "args": {"command": "PLAY_PAUSE"}},
        {"label": "Suivant", "icon": "skip-next", "tool": "tv_key", "args": {"command": "NEXT"}},
        {"label": "Stop", "icon": "stop", "tool": "tv_key", "args": {"command": "STOP"}},
        {"label": "Vol -", "icon": "chevron-down", "tool": "tv_volume", "args": {"direction": "down"}},
        {"label": "Vol +", "icon": "chevron-up", "tool": "tv_volume", "args": {"direction": "up"}},
        {"label": "Muet", "icon": "x", "tool": "tv_volume", "args": {"direction": "mute"}},
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

    if name == "jellyfin_resume_on_tv":
        if not store.list_public("jellyfin"):
            return "Aucun serveur Jellyfin connecté — ajoute-en un depuis la Console (Intégrations), Monsieur."
        query = args.get("title", "")
        item = jellyfin.find_resume_item(query)
        if not item:
            return (
                f"Rien dans « reprendre la lecture » ne correspond à {query!r}, Monsieur — "
                "vérifie avec jellyfin_continue_watching."
            )

        result = jellyfin.resume_on_session(item["id"], item.get("resume_position_ticks", 0))
        if result.get("error") == "no_session":
            if not android_tv.configured():
                return (
                    f"« {item['name']} » trouvé, mais aucune session Jellyfin active sur la télé "
                    "et la télé du salon n'est pas configurée (ANDROID_TV_HOST manquant), Monsieur "
                    "— ouvre l'appli Jellyfin sur la télé toi-même."
                )
            android_tv.launch_app("org.jellyfin.androidtv")
            time.sleep(_JELLYFIN_TV_LAUNCH_DELAY_SECONDS)
            result = jellyfin.resume_on_session(item["id"], item.get("resume_position_ticks", 0))

        if result.get("error"):
            return result["error"]

        title = item["name"] if not item.get("series") else f"{item['series']} — {item['name']}"
        cards.emit("tv", title, {}, subtitle=f"Repris sur {result['device']}", actions=_tv_actions())
        return f"Reprise sur {result['device']} : {title}."

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
        city = preferences.get_weather()["city"]
        desc = weather.description(w["code"])
        cards.emit("weather", f"{round(w['temp'])}°C", {
            "temp": w["temp"], "description": desc, "wind": w["wind"], "city": city,
        }, subtitle=desc.capitalize())
        return f"Il fait {round(w['temp'])} degrés à {city}, {desc}, Monsieur."

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

    if name == "tv_status":
        if not android_tv.configured():
            return "La télé du salon n'est pas configurée, Monsieur — ANDROID_TV_HOST manquant dans .env."
        result = android_tv.status()
        if "error" in result:
            return result["error"]
        cards.emit("tv", "Télé du salon", result, subtitle="Statut", actions=_tv_actions())
        if result["screen_on"] is False:
            return "L'écran de la télé est éteint, Monsieur."
        parts = []
        parts.append("écran allumé" if result["screen_on"] else "état de l'écran inconnu")
        if result["foreground_app"]:
            parts.append(f"application au premier plan : {result['foreground_app']}")
        media = result["media"]
        if media and (media.get("title") or media.get("package")):
            title = media.get("title") or media.get("package")
            media_desc = title
            if media.get("artist"):
                media_desc += f" — {media['artist']}"
            if media.get("state"):
                media_desc += f" ({media['state']})"
            if media.get("position_ms") is not None:
                secs = media["position_ms"] // 1000
                media_desc += f", à {secs // 60}:{secs % 60:02d}"
            parts.append(media_desc)
        else:
            parts.append("aucune lecture en cours détectée")
        return ", ".join(parts) + ", Monsieur."

    if name == "tv_volume":
        if not android_tv.configured():
            return "La télé du salon n'est pas configurée, Monsieur — ANDROID_TV_HOST manquant dans .env."
        result = android_tv.volume(args.get("direction"), args.get("level"))
        if "error" in result:
            return result["error"]
        if "level_percent" in result:
            return f"Volume : {result['level_percent']} %."
        return f"Volume : {result['direction']}."

    if name == "tv_key":
        if not android_tv.configured():
            return "La télé du salon n'est pas configurée, Monsieur — ANDROID_TV_HOST manquant dans .env."
        result = android_tv.send_key(args.get("command", ""))
        if "error" in result:
            return result["error"]
        return f"Touche envoyée : {result['command']}."

    if name == "tv_seek":
        if not android_tv.configured():
            return "La télé du salon n'est pas configurée, Monsieur — ANDROID_TV_HOST manquant dans .env."
        result = android_tv.seek(args.get("direction", ""), args.get("seconds", 10))
        if "error" in result:
            return result["error"]
        verb = "avancée" if result["direction"] == "forward" else "reculée"
        return f"Lecture {verb} de {result['seconds']} secondes."

    if name == "tv_launch_app":
        if not android_tv.configured():
            return "La télé du salon n'est pas configurée, Monsieur — ANDROID_TV_HOST manquant dans .env."
        result = android_tv.launch_app(args.get("target", ""))
        if "error" in result:
            return result["error"]
        cards.emit("tv", result["target"], {}, subtitle="Lancé sur la télé", actions=_tv_actions())
        return f"Lancé sur la télé : {result['target']}."

    if name == "send_to_tv":
        if not android_tv.configured():
            return "La télé du salon n'est pas configurée, Monsieur — ANDROID_TV_HOST manquant dans .env."
        result = android_tv.send_to_tv(args.get("url", ""))
        if "error" in result:
            return result["error"]
        cards.emit("tv", result["target"], {}, subtitle="Envoyé depuis le PC", actions=_tv_actions())
        return f"Envoyé sur la télé : {result['target']}."

    if name == "tv_resume_on_pc":
        if not android_tv.configured():
            return "La télé du salon n'est pas configurée, Monsieur — ANDROID_TV_HOST manquant dans .env."
        result = android_tv.now_playing_url()
        if "error" in result:
            return result["error"]
        if result.get("url"):
            pos = f" à {result['position_seconds']}s" if result.get("position_seconds") else ""
            return f"Titre : {result.get('title') or 'inconnu'}{pos}. URL à ouvrir sur le PC : {result['url']}"
        return result["text"]

    if name == "tv_apps_list":
        if not android_tv.configured():
            return "La télé du salon n'est pas configurée, Monsieur — ANDROID_TV_HOST manquant dans .env."
        result = android_tv.list_apps()
        if "error" in result:
            return result["error"]
        return "Applications installées :\n" + "\n".join(f"- {p}" for p in result["packages"])

    if name == "tv_screen_dump":
        if not android_tv.configured():
            return "La télé du salon n'est pas configurée, Monsieur — ANDROID_TV_HOST manquant dans .env."
        result = android_tv.ui_dump()
        return result.get("error") or result["text"]

    if name == "tv_tap":
        if not android_tv.configured():
            return "La télé du salon n'est pas configurée, Monsieur — ANDROID_TV_HOST manquant dans .env."
        result = android_tv.tap(args.get("x", 0), args.get("y", 0))
        if "error" in result:
            return result["error"]
        return f"Appui effectué à ({result['x']},{result['y']})."

    if name == "tv_type_text":
        if not android_tv.configured():
            return "La télé du salon n'est pas configurée, Monsieur — ANDROID_TV_HOST manquant dans .env."
        result = android_tv.type_text(args.get("text", ""))
        if "error" in result:
            return result["error"]
        return f"Texte tapé : {result['text']}."

    if name == "tv_screenshot":
        if not android_tv.configured():
            return "La télé du salon n'est pas configurée, Monsieur — ANDROID_TV_HOST manquant dans .env."
        result = android_tv.screenshot()
        if "error" in result:
            return result["error"]
        cards.emit("tv", "Télé du salon",
                   {"image_b64": result["image_b64"], "media_type": result["media_type"]},
                   subtitle="Capture à distance", actions=_tv_actions())
        return result

    return f"Outil brain inconnu : {name}"

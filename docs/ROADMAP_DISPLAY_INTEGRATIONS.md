# J.A.R.V.I.S. — Roadmap Intégrations & Affichage riche

Complète `ROADMAP.md` (F14/F15/F17 y sont déjà esquissés) et
`ROADMAP_MULTIDEVICE.md` (brain + web console). Ce doc se concentre sur deux
choses liées : **brancher Jarvis sur mes comptes externes** (Notion, Google
Drive, Spotify, Gmail, Zoho Mail…) et **lui donner un vrai langage visuel**
pour restituer ce qu'il va chercher — cartes, modales, captures, flux vidéo —
au lieu de tout dire à voix haute ou de tout enfouir dans le HUD texte.

Légende effort : ▲ = un soir · ▲▲ = un week-end · ▲▲▲ = plusieurs jours/semaines

---

## 0. Principe directeur

Aujourd'hui Jarvis a un seul canal de sortie riche : le HUD PyQt (bulles de
texte + petits widgets custom). Avec le brain + web console déjà en place
(`ROADMAP_MULTIDEVICE.md`), on a une deuxième surface, plus adaptée à de
l'affichage structuré : navigateur = HTML/CSS/React, donc facile d'y poser
des cartes riches (agenda, mail, fichier, lecteur Spotify, image).

**Décision d'archi : les intégrations vivent dans le `brain`, pas dans
l'agent desktop.** Un compte Google/Notion/Spotify/Zoho est unique pour moi,
pas par appareil — les jetons OAuth doivent être stockés une seule fois côté
serveur (`brain/`), et n'importe quel agent (desktop, mobile à venir) ou la
web console peut demander « qu'est-ce que j'ai aujourd'hui ? » et obtenir la
même réponse. Le HUD desktop reste le canal vocal/rapide ; la web console
devient le canal d'affichage riche.

---

## 1. Intégrations externes

| # | Service | Accès | Cas d'usage vocal/texte | Écriture ? | Effort |
|---|---------|-------|--------------------------|-----------|--------|
| I1 | **Google Calendar** ✓ *(fait)* | OAuth2 (Calendar API, lecture), multi-comptes | « qu'est-ce que j'ai aujourd'hui/cette semaine ? », alerte 10 min avant un événement (à venir), briefing matinal (F6, à venir) | lecture seule ; création jamais implémentée pour l'instant | ▲▲ |
| I2 | **Notion (calendrier + pages)** | Notion API (intégration interne, token) | si l'agenda réel vit dans une base Notion plutôt que Google Calendar : lire une base « Calendrier », lister les pages d'un projet, chercher une note | écriture (cocher une tâche, ajouter une ligne) seulement sur confirmation | ▲▲ |
| I3 | **Google Drive** ✓ *(fait, lecture + écriture confirmée)* | OAuth2 (Drive API, scope `drive` complet) | recherche, lecture (Docs/Sheets/Slides/PDF/texte), ouverture (open_url), création/remplacement/corbeille — les 3 dernières via bannière de confirmation Console (brain/integrations/confirm.py) | écriture possible mais toujours confirmée à l'écran ; suppression = corbeille, jamais définitive | ▲▲ |
| I4 | **Gmail** ✓ *(fait)* | OAuth2 (gmail.readonly + gmail.compose) | recherche (syntaxe Gmail native), lecture, brouillon (sans confirmation), envoi via bannière de confirmation (gmail_search/gmail_read/gmail_draft/gmail_send) | brouillon libre, envoi toujours confirmé à l'écran | ▲▲ |
| I5 | **Zoho Mail** ✓ *(fait, API Zoho pas IMAP)* | OAuth2 Zoho (accounts.READ + messages.READ/CREATE), multi-datacenter | recherche, lecture, composition — zoho_search/zoho_read/zoho_compose | composition toujours confirmée (brouillon ET envoi confondus, frontière API Zoho moins nette que Gmail — voir README) | ▲▲ |
| I6 | **Spotify** ✓ *(fait, texte — pas de carte pochette)* | OAuth2 Web API | spotify_now_playing/spotify_play/spotify_control/spotify_volume — « mets ma playlist détente » résout via playlists perso puis catalogue public | contrôle lecture = action directe, aucune confirmation | ▲▲ |
| I7 | **Google Contacts** ✓ *(fait)* | OAuth2 (People API) | contacts_search — « le numéro de X », résolution de nom pour Gmail/Zoho ; filtre local plutôt que l'index searchContacts (souvent en retard après un ajout récent) | lecture seule | ▲ |
| I8 | **GitHub notifications** (bonus, si pertinent pour toi) | REST API (token) | « des PR en attente ? », « des issues qui me sont assignées ? » | lecture seule | ▲ |
| I9 | **Discord** (bonus, écarté) | nécessiterait un bot (pas d'accès aux DM, seulement les serveurs invités) — proposé, décliné par Monsieur (pas l'usage voulu) | — | — | — |
| I10 | **Jellyfin** ✓ *(fait)* | serveur perso, clé API — pas d'OAuth, connexion directe (base_url + clé + utilisateur optionnel) | jellyfin_search/jellyfin_now_playing/jellyfin_continue_watching/jellyfin_recently_added | lecture seule ; pas de contrôle de lecture à distance | ▲ |
| I11 | **Tisséo (transports Toulouse)** ✓ *(fait)* | API publique gratuite, clé simple — pas d'OAuth, pas de facturation (Google Maps évoqué puis écarté pour cette raison) | tisseo_next — arrêts favoris multiples (un "compte" = un arrêt), fusionnés au listing | lecture seule ; confiance technique modérée sur les noms de paramètres exacts | ▲ |
| I12 | **Itinéraires (OpenRouteService)** ✓ *(fait)* | alternative gratuite à Google Maps (écarté, facturation obligatoire) — clé simple, pas d'OAuth, pas de "compte" (aucune persistance nécessaire) | directions — distance + temps de trajet voiture/vélo/à pied, géocodage OpenStreetMap, repli sur adresse domicile configurée | lecture seule ; moins précis que Google sur le trafic temps réel | ▲ |
| I13 | **Home Assistant** ✓ *(fait)* | domotique, token longue durée — pas d'OAuth, connexion directe (base_url + token) | ha_state/ha_control/ha_set_temperature — résolution d'entité par nom (friendly_name), contrôle direct générique (homeassistant.turn_on/off/toggle) | contrôle direct sauf serrures/alarme (ouverture/désarmement confirmés — verrouiller/armer jamais) | ▲▲ |

**Notion vs Google Calendar** : si ton agenda réel est dans Notion Calendar,
commence par I2 seul (une seule source de vérité). Si tu utilises aussi
Google Calendar en parallèle, I1 en plus permet une vue fusionnée — mais
évite de brancher les deux dès le départ, ça double le travail de rendu pour
un gain flou. Décide selon où vit réellement ton planning aujourd'hui.

### Architecture d'intégration commune

- ✓ *(fait)* `brain/integrations/<service>.py` — client OAuth + wrapper API,
  un module par service, même forme que `agents/desktop/services/weather.py`
  (cache, gestion d'erreur, pas de clé en dur). `google_calendar.py` en
  place, OAuth « à la main » via `requests` (pas de SDK Google, inutile pour
  3 appels REST).
- ✓ *(fait, sous une forme un peu différente)* `brain/integrations/crypto.py`
  + `store.py` — stockage chiffré (Fernet, clé auto-générée dans
  `data/integrations.key`) des refresh tokens dans `data/integrations.json`,
  générique à tous les services futurs (un seul fichier, pas un par
  service).
- ✓ *(fait pour Google Calendar)* Chaque intégration expose des **tools** au
  même titre que `agents/desktop/tools/` aujourd'hui, mais côté brain
  (`brain/tools.py`, fusionné avec les tools PC dans
  `brain/core/agent.py::ask_with_tools`) : `calendar_events` existe,
  `drive_search`, `mail_unread`, `spotify_play`… suivront pareil. Pour
  l'instant la réponse reste du texte formaté, pas encore une **carte**
  (voir §2, pas construit) — à faire quand une 2e intégration (mails ou
  Drive) rendra le texte brut insuffisant.
- ✓ *(fait)* Panneau **Intégrations** dans la Console web
  (`Integrations.jsx` + `useIntegrations.js`) : lister/connecter/déconnecter
  les comptes directement depuis le site, sans toucher à `.env` à la main
  une fois les identifiants Google Cloud renseignés une fois pour toutes
  (voir `README.md`).
- **Lecture seule par défaut partout.** Toute action d'écriture (envoyer un
  mail, créer un événement, déplacer un fichier) passe par la même bulle de
  confirmation visuelle que les commandes PowerShell destructrices
  aujourd'hui (`tools/safety.py`) — c'est déjà le bon pattern, on le
  réutilise.

---

## 2. Système d'affichage riche — les « cartes » ✓ *(fait)*

Le vrai chantier structurant derrière ta demande : donner à Jarvis un
**format de réponse visuelle unique**, que chaque intégration/outil peut
remplir, et que la web console (et dans une moindre mesure le HUD) sait
rendre de façon cohérente — au lieu de réinventer un widget par feature.

### 2.1 Protocole ✓ *(fait — `brain/cards.py`)*

Implémenté avec un champ de plus que prévu (`subtitle`) et un `id`
attribué par le brain. Deux chemins de sortie plutôt qu'un :
`GET /api/cards` (les 30 dernières, pour repeupler l'écran après un
rafraîchissement) et `WS /ws/cards`, qui **diffuse à toutes les
Consoles ouvertes** — pas seulement à celle qui a posé la question.
C'est ce qui permet de demander son agenda à voix haute au PC fixe et
de le voir s'afficher sur l'écran d'à côté. Le même canal transporte
les tours de conversation (`kind: "exchange"`), pour que le pupitre
affiche aussi ce qui vient d'être dit ailleurs.


Une réponse d'outil peut inclure, en plus du texte parlé, un objet `card` :

```json
{
  "type": "calendar_day",
  "title": "Aujourd'hui",
  "data": { "events": [...] },
  "actions": [{ "label": "Voir la semaine", "tool": "calendar_week" }]
}
```

Transporté sur le même WebSocket brain ↔ agents ↔ web console qui existe
déjà (`ROADMAP_MULTIDEVICE.md`). Le HUD desktop affiche un résumé compact +
« ouvrir dans la console » ; la web console rend le composant React complet.

### 2.2 Types de cartes

Quatorze types construits (`web/src/components/cards/renderers.jsx`) ; les
émissions vivent dans `brain/tools.py` (+ `brain/core/agent.py` pour
screenshot/file_preview, déclenchées par le résultat d'un outil PC plutôt
que par un tool brain), à côté du texte que Claude et la voix continuent
d'utiliser — la carte double l'information, elle ne la remplace pas.


| Type | Contenu | Alimenté par |
|------|---------|--------------|
| `agenda` ✓ | événements du jour/de la semaine, heure, lieu | I1 |
| `mail` / `mail_detail` ✓ | expéditeur, objet, aperçu ; corps complet en détail | I4/I5 |
| `files` / `document` ✓ | nom + lien cliquable ; contenu lu en aperçu ; **écriture aussi cartée** (create/update/delete) | I3 |
| `music` ✓ *(avec contrôles)* | pochette, titre, artiste, barre de progression, **boutons précédent/pause-lecture/suivant sur la carte elle-même** (`/api/tools/execute`, générique à tout type de carte) | I6 |
| `screenshot` ✓ *(avec export)* | image capturée, cliquable pour l'agrandir, **copier/enregistrer** | `tools/screen.py`, affichée automatiquement dès qu'un outil PC renvoie une image |
| `file_preview` ✓ | contenu d'un fichier local lu à distance (`read_file_content`), même mécanique que screenshot | `brain/core/agent.py` |
| `video_stream` | flux live (webcam ou partage d'écran) — **seul point encore non commencé**, classé ▲▲▲ (plusieurs jours), volontairement laissé pour une session dédiée | §4 |
| `confirmation` | HUD (`ui/dialogs.py`, bulle Qt) ✓ ; web ✓ (`ConfirmationBanner.jsx` + `brain/integrations/confirm.py`) — **reste un canal séparé du protocole `cards.py`, décision assumée** : le fusionner referait un mécanisme de sécurité déjà éprouvé pour un gain cosmétique | `tools/safety.py` (desktop) / `confirm.py` (brain) |
| `transport` / `route` ✓ | prochains passages ; distance et durée de trajet | I11 / I12 |
| `media` / `contacts` / `home` ✓ | titres Jellyfin, fiches contact, état des entités | I10 / I7 / I13 |
| `weather` ✓ | température, description, vent — `brain/weather.py` (Open-Meteo, dupliqué du desktop pour ne pas en dépendre) | nouveau tool `weather_now` |
| `diagnostics` ✓ | CPU/RAM/disque, coût API du mois — instantané à la demande, pas de polling continu comme le HUD | nouveau tool `system_diagnostics`, `brain/diagnostics.py` |

**Rendu** : Hud.jsx (pupitre) et **Console.jsx** (fil de conversation) affichent
désormais tous les deux les cartes — ce n'était vrai que pour le Hud
jusqu'ici. **Historique réel** : chaque carte est aussi journalisée sur
disque (`data/logs/cards-AAAA-MM.jsonl`, images retirées), consultable
au-delà des 30 dernières via `GET /api/cards/history` et la nouvelle
section "Historique des affichages" de l'écran Système.

### 2.3 Pourquoi c'est prioritaire

Sans ce socle, chaque intégration (I1 à I9) réinvente son propre bout d'UI
et le HUD PyQt devient un fourre-tout. Avec le socle : ajouter Spotify plus
tard = un nouveau type de carte + un composant React, pas une refonte.

---

## 3. Capture d'écran — l'afficher, pas juste l'analyser

Aujourd'hui `tools/screen.py` capture une zone/l'écran et l'envoie à Claude
en interne (vision), mais **l'image n'est jamais montrée** à l'utilisateur —
seule la réponse texte de Claude apparaît dans le HUD.

- **F-screenshot-1** ✓ *(fait)* — après une capture (Vision ciblée ou demande
  explicite « montre-moi une capture »), pousser une carte `screenshot` vers
  la web console (et une miniature cliquable dans le HUD) en plus de la
  réponse vocale.
- **F-screenshot-2** ▲ — bouton « copier » / « enregistrer » sur la carte (l'agrandissement au clic existe, pas encore l'export).
- Ça règle directement ton exemple : « si je lui demande une capture
  d'écran faut qu'il puisse me l'afficher direct ».

---

## 4. Capture vidéo en temps réel

Deux cas d'usage différents à ne pas confondre :

- **Partage d'écran live** (« montre-moi ton écran en continu », debug à
  distance, suivi d'une longue tâche PC) — flux MJPEG ou WebRTC depuis
  l'agent desktop vers le brain vers la web console. Techniquement : capture
  écran en boucle (déjà fait ponctuellement dans `screen.py`) → encodage
  JPEG → push périodique sur un canal dédié, ou WebRTC si on veut du vrai
  temps réel fluide.
- **Webcam** (présence, futur reconnaissance visuelle façon JARVIS/Tony
  Stark) — plus anecdotique, à ne considérer qu'après le reste ; gros sujet
  vie privée si un jour on veut de la détection de présence automatique
  (opt-in strict, jamais par défaut).

| # | Feature | Détail | Effort |
|---|---------|--------|--------|
| V1 | Partage d'écran live (pull, sur demande) ✓ *(fait)* | Focus.jsx → « Voir l'écran en direct » : polling ~800ms sur `POST /api/devices/{id}/stream/frame` (pas de WebRTC/canal dédié — plus simple, suffisant pour du visuel, pas du temps réel 30fps) ; nouveau tool agent léger `capture_frame` (960px, absent de PC_TOOLS — jamais exposé à Claude), séparé de `take_screenshot`/`activity.record` pour ne pas noyer le journal | ▲▲ |
| V2 | Enregistrement court à la demande | « enregistre les 30 prochaines secondes d'écran » → mp4 sauvegardé + carte `video_stream` en lecture | ▲▲ |
| V3 | Webcam ponctuelle | « regarde-moi » → une frame webcam analysée en vision, pas de flux permanent | ▲ |
| V4 | Webcam live / présence | hors scope tant que non demandé explicitement — vie privée | ▲▲▲, à éviter par défaut |

---

## 5. Autres idées qui collent au même chantier

- **Panneau « Comptes connectés »** dans la web console — état de chaque
  intégration (connecté/expiré), bouton reconnecter, scopes accordés. Sans
  ça, un token qui expire silencieusement = feature qui « marche plus » sans
  explication.
- **Fil d'actualité personnel unifié** — une carte qui agrège mails non lus
  + événements du jour + notifications importantes (Discord/GitHub) en une
  vue, alimentée par F6 (briefing matinal) déjà prévu dans `ROADMAP.md`.
- **Recherche unifiée** — « cherche le fichier/mail/event qui parle de X »
  interroge Drive + Gmail + Calendar en parallèle et retourne une carte
  mixte par source.
- **Mode présentation / dashboard ambiant** — extension du « mode ambiant »
  déjà noté en F29 (`ROADMAP.md`). Première marche posée : l'écran
  d'accueil de la Console est le **pupitre** (`web/src/components/Hud.jsx`)
  — réacteur, heure, mode en cours, appareils en ligne, et les cartes qui
  s'y empilent. Le panorama silencieux (météo + agenda du jour + santé
  système, sans qu'on ait rien demandé) est fait : `GET /api/ambient`
  (`brain/server.py`), en cache, lu par `useAmbient.js` et rendu par les
  cartes existantes tant que le pupitre est au repos. Reste à faire : un
  vrai mode plein écran sans navigation.
- **Historique des cartes** — les cartes envoyées (mails lus, captures,
  événements consultés) restent consultables dans le panneau transmissions
  existant (F31), pas juste éphémères.

---

## 6. Roadmap — TOP 5 recommandé

| Prio | Feature | Pourquoi | Effort |
|------|---------|----------|--------|
| ★1 | ~~**Socle cartes (§2)**~~ ✓ fait | Tout le reste en dépend ; sans lui chaque intégration réinvente son UI | ▲▲ |
| ★2 | **I1/I2 — Agenda (Google Calendar ou Notion, un seul des deux)** | Utilité quotidienne immédiate, alimente aussi le briefing matinal F6 | ▲▲ |
| ★3 | ~~**F-screenshot-1 — Afficher les captures**~~ ✓ fait | Gain immédiat, quasi gratuit vu que `screen.py` existe déjà | ▲ |
| ★4 | **I4/I5 — Mails (lecture seule d'abord)** | Deuxième besoin quotidien le plus cité par toi | ▲▲ |
| ★5 | **I6 — Spotify** | Petit scope, très visible/satisfaisant (carte pochette + contrôle) | ▲▲ |

Ensuite, dans l'ordre naturel : I3 (Drive), panneau comptes connectés (§5),
V1 (partage d'écran live), puis le reste des bonus (I7-I9, V2-V4).

---

## 7. Pièges à éviter

- **Brancher les 6 intégrations d'un coup** — une seule bien faite (carte +
  lecture seule + gestion d'erreur token expiré) vaut mieux que six
  bancales. Le socle §2 doit être validé sur la première avant de dupliquer.
- **Écriture par défaut** — tout ce qui modifie un compte externe (envoyer
  un mail, créer un événement, supprimer un fichier) doit rester derrière
  une confirmation explicite, jamais une action « pendant que j'y suis ».
- **Un token qui expire en silence** — sans le panneau « comptes connectés »
  (§5), une intégration cassée ressemble à un bug alors que c'est juste un
  refresh token à renouveler.
- **Webcam live par défaut** (V4) — feature à fort risque vie privée, à ne
  construire que si explicitement redemandé plus tard, jamais activée par
  défaut.
- **Réinventer l'UI HUD pour chaque carte** — le HUD PyQt reste le canal
  vocal/compact ; l'affichage riche va dans la web console (déjà prévue
  comme « dashboard » dans `ROADMAP_MULTIDEVICE.md`), pas dans un nouveau
  widget PyQt par intégration.

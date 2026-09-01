# J.A.R.V.I.S. — Just A Rather Very Intelligent System

Assistant vocal personnel façon Iron Man, 100 % Windows :

- **Wake word** « Jarvis » — modèle TFLite entraîné localement, zéro cloud
- **Oreilles** — Whisper (Speaches, Docker local) avec STT spéculatif (latence perçue ~0 ms)
- **Voix** — Piper (Speaches), streaming phrase par phrase, interruptible à la voix (barge-in)
- **Cerveau hybride** — conversation via Ollama local (gratuit, privé), pilotage du PC via
  l'API Claude (tool-use + **vision réelle des captures d'écran**)
- **Vision ciblée** — sélection d'une zone d'écran façon outil Capture, puis question
  vocale ou écrite dessus (« c'est quoi cette erreur ? »)
- **Minuteurs & rappels** — « minuteur 5 minutes », « rappelle-moi de… dans 20 min »,
  compte à rebours dans le HUD, carillon + annonce vocale à l'échéance
- **HUD cinématique** — fenêtre octogonale, arc reactor à bobines, balayage radar,
  panneaux chanfreinés Stark, icônes vectorielles, sparkline CPU temps réel,
  bulles de conversation horodatées avec temps de réponse, coût API en direct
- **Icône arc reactor** partout : barre des tâches, tray (couleur selon l'état),
  languette de repli

## Démarrage

```
start_jarvis.bat        # démarre tout : Docker/Speaches, Ollama, le brain (Console web), puis Jarvis
# ou, tout étant déjà lancé :
python jarvis.py
```

Raccourcis globaux :
- **Ctrl+Alt+J** — afficher le HUD et donner le focus à la saisie texte
- **Ctrl+Alt+V** — Vision ciblée (sélection de zone + question)

## Vision ciblée

Trois façons de la déclencher :
1. **Ctrl+Alt+V** n'importe où dans Windows
2. le bouton **⌖** du HUD
3. à la voix : « Jarvis, **regarde ça** », « **analyse cette zone** »… — la suite de la
   phrase devient directement la question (« regarde ça, c'est quoi cette erreur ? »)

Le bureau est figé, vous tracez un rectangle (Échap pour annuler). Si aucune question
n'accompagnait le déclenchement, Jarvis dit « Je vous écoute » et prend la question à
la voix (ou au clavier en mode MIC OFF). Sans question du tout, il décrit la zone.

## Commandes vocales utiles

| Dire… | Effet |
|---|---|
| « que sais-tu faire ? » / « aide » | fiche mémo dans le HUD + résumé vocal |
| « minuteur 5 minutes » / « 1 heure 30 » | minuteur avec compte à rebours header |
| « rappelle-moi de sortir le pain dans 20 minutes » | rappel avec message |
| « combien de temps reste-t-il ? » / « annule le minuteur » | gestion minuteurs |
| « combien tu m'as coûté ce mois-ci ? » | coût API du mois en euros |
| « prends note que… » | note datée dans data/notes/ |
| « mémorise que… » | fait durable en mémoire long terme |
| « mets le volume à 40 % » · « quel temps fait-il ? » | réglages et infos locales |

## Arborescence

Le projet évolue vers une architecture multi-appareils : un **cerveau**
central (à venir, sur le PC fixe), une **interface web** (à venir, servie
par le cerveau), et un ou plusieurs **agents** par appareil. Aujourd'hui,
seul l'agent desktop existe — c'est l'assistant complet décrit plus haut,
qui tourne 100 % en local sur le PC fixe.

```
Jarvis/
├─ jarvis.py                 ← point d'entrée de l'agent desktop
├─ brain/                    ← serveur central : décision, mémoire, routage multi-appareils
│  └─ core/                  ← [à venir] extraction de agents/desktop/brain/ une fois le serveur en place
├─ web/                      ← [à venir] interface web (dashboard, chat, centre de contrôle des appareils)
├─ agents/
│  ├─ desktop/                ← agent Windows (PC fixe / portable) — c'est l'app actuelle
│  │  ├─ config.py             ← toute la configuration (+ surcharges .env)
│  │  ├─ state.py              ← événements partagés (stop_speaking, stop_agent…)
│  │  ├─ runtime.py            ← orchestrateur : boot, boucle d'écoute, routage
│  │  ├─ audio/
│  │  │  ├─ capture.py         ← flux micro persistants (auto-réouverture)
│  │  │  ├─ vad.py             ← Silero VAD
│  │  │  ├─ wakeword.py        ← détection « Jarvis » (TFLite)
│  │  │  ├─ stt.py             ← Whisper spéculatif
│  │  │  └─ tts.py             ← Piper + barge-in + enveloppe audio pour le HUD
│  │  ├─ brain/                ← logique de décision (migrera vers brain/core/ avec le serveur)
│  │  │  ├─ prompts.py         ← personnalité + instructions agent
│  │  │  ├─ router.py          ← aiguillage (fast paths locaux vs LLM)
│  │  │  ├─ chat.py            ← streaming Ollama → repli Claude
│  │  │  ├─ agent.py           ← agent Claude à outils (vision incluse)
│  │  │  ├─ vision.py          ← Vision ciblée (question sur une zone d'écran)
│  │  │  ├─ memory.py          ← faits durables (« mémorise que… »)
│  │  │  ├─ modes.py           ← modes contextuels (travail, détente…)
│  │  │  ├─ commands.py        ← commandes apprises (fast path 0 ms)
│  │  │  ├─ usage.py           ← suivi tokens/coût API
│  │  │  └─ history.py         ← historique de conversation
│  │  ├─ tools/                ← outils de pilotage PC exposés à Claude
│  │  │  ├─ registry.py        ← schémas + dispatch
│  │  │  ├─ safety.py          ← commandes destructrices, contenu non fiable
│  │  │  ├─ system.py          ← PowerShell, fichiers, presse-papier
│  │  │  ├─ screen.py          ← capture (image pour Claude), OCR, URL navigateur
│  │  │  ├─ input_ctl.py       ← clavier, souris, URL
│  │  │  └─ assist.py          ← demande d'aide, apprentissage de commandes
│  │  ├─ services/
│  │  │  ├─ weather.py         ← météo Open-Meteo (sans clé, cache 30 min)
│  │  │  ├─ diagnostics.py     ← CPU/RAM/disque/réseau/latence réels pour le HUD
│  │  │  ├─ timers.py          ← minuteurs et rappels vocaux (+ chip compte à rebours)
│  │  │  ├─ routines.py        ← routines vocales (« routine matin »)
│  │  │  ├─ notes.py           ← prise de notes datées (« prends note que… »)
│  │  │  ├─ convlog.py         ← journal des conversations (JSONL mensuel)
│  │  │  ├─ hotkey.py          ← Ctrl+Alt+J / Ctrl+Alt+V globaux
│  │  │  └─ bootsound.py       ← son de mise sous tension synthétisé
│  │  ├─ ui/
│  │  │  ├─ theme.py           ← palette Iron Man + transitions de couleur
│  │  │  ├─ icons.py           ← icônes vectorielles (boutons, arc reactor d'app)
│  │  │  ├─ widgets.py         ← arc reactor, panneaux chanfreinés, onde, conversation
│  │  │  ├─ hud.py             ← fenêtre principale octogonale + façade thread-safe
│  │  │  ├─ dialogs.py         ← confirmations/aide (Qt, thématisés)
│  │  │  ├─ snip.py            ← sélecteur de zone d'écran (Vision ciblée)
│  │  │  ├─ tray.py            ← icône de zone de notification (Qt natif)
│  │  │  └─ preview_render.py  ← rendu PNG du HUD sans afficher de fenêtre
│  │  ├─ wakeword/             ← entraînement du modèle wake word
│  │  ├─ voice/                ← modèle de voix Piper personnalisé (optionnel)
│  │  └─ build_preview/        ← sorties de rendu du HUD (généré, ignoré par git)
│  ├─ mobile/                 ← [à venir] agent compagnon téléphone
│  └─ protocol/                ← [à venir] schéma de messages partagé brain ↔ agents
├─ data/                     ← état persistant partagé (mémoire, modes, commandes,
│                                routines, usage, contexte, notes/, logs/)
├─ legacy/                   ← ancienne version monolithique (référence)
└─ docs/
```

## Flux d'une question vocale

```
« Jarvis » (TFLite local)
   → transcription Whisper (spéculative pendant le silence)
      → routage :
         1. changement de mode        (local, 0 ms)
         2. routine vocale            (local)
         3. « mémorise que… »         (local)
         4. « prends note que… »      (local)
         5. commande apprise          (local, 0 ms)
         6. heure/date/IP/volume %/météo (local)
         7. conversation → Ollama (repli Claude), streaming phrase par phrase
            pilotage PC  → agent Claude + outils (vision d'écran réelle)
   → synthèse Piper, interruptible à la voix à tout moment
```

## Configuration (.env à la racine)

| Clé | Défaut | Rôle |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | pilotage PC + repli conversationnel |
| `CLAUDE_MODEL` | `claude-haiku-4-5-20251001` | modèle Claude |
| `OLLAMA_URL` / `OLLAMA_MODEL` | `http://localhost:11434/api/chat` / `qwen3:14b` | cerveau local |
| `OLLAMA_KEEP_ALIVE` | `30m` | maintien du modèle en VRAM |
| `SPEACHES_STT_URL` / `SPEACHES_TTS_URL` | `http://localhost:8000/...` | STT/TTS local |
| `STT_MODEL` / `TTS_MODEL` / `TTS_VOICE` | whisper-small / piper siwis | modèles audio |
| `INTERRUPT_PROFILE` | auto | forcer `casque` ou `haut-parleur` (barge-in) |
| `WEATHER_LAT` / `WEATHER_LON` / `WEATHER_CITY` | Toulouse | météo |
| `BOOT_SOUND` | `1` | son de mise sous tension |
| `GLOBAL_HOTKEY` | `1` | Ctrl+Alt+J (HUD) et Ctrl+Alt+V (Vision ciblée) |
| `BRAIN_ENABLED` | `0` | connecte ce PC au brain en tâche de fond (multi-appareils, voir `docs/ROADMAP_MULTIDEVICE.md`) — nécessite d'avoir appairé l'appareil au préalable via `python -m agents.desktop.agent_client` |
| `BRAIN_URL` | `ws://127.0.0.1:8420/ws/agent` | adresse du brain, si `BRAIN_ENABLED=1` |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | — | intégration Google Calendar (panneau **Intégrations** de la Console web), voir ci-dessous |
| `GOOGLE_REDIRECT_URI` | `http://127.0.0.1:8420/api/integrations/google/callback` | à ne changer que si le brain n'écoute pas sur `127.0.0.1:8420` |

### Google (Calendar, Drive, Gmail, Contacts)

Panneau **Intégrations** de la Console web (`ROADMAP_DISPLAY_INTEGRATIONS.md`)
— comptes multiples supportés par service, résultats fusionnés
automatiquement. Un seul Client ID/Secret Google sert pour tous les
services (Calendar, Drive, et les suivants sur le même modèle) — mise en
place une fois, ~5 min :

1. [Google Cloud Console](https://console.cloud.google.com/) → nouveau
   projet (ou existant) → **APIs & Services** → activer **Google Calendar
   API**, **Google Drive API**, **Gmail API** ET **People API** (les
   quatre, même si tu ne comptes utiliser qu'un service pour l'instant —
   inactive, l'API bloque juste silencieusement les appels le jour où tu
   voudras un autre).
2. **APIs & Services → OAuth consent screen** → type *External* (ou
   *Internal* si Workspace), ajoute-toi comme utilisateur de test si l'app
   reste en mode test (largement suffisant pour un usage perso) — ajoute
   bien **chaque** compte Gmail que tu comptes connecter, Calendar et Drive
   confondus, sinon Google bloque avec une erreur 403 (« accès bloqué »).
3. **APIs & Services → Identifiants → Créer des identifiants → ID client
   OAuth**, type **Application Web**. Dans *URI de redirection autorisés*,
   colle exactement `http://127.0.0.1:8420/api/integrations/google/callback`
   (ou la valeur de `GOOGLE_REDIRECT_URI` si tu l'as changée) — un seul URI
   pour tous les services Google, le brain route en interne selon lequel a
   été demandé.
4. Ouvre la Console web → **Intégrations** → déplie **Paramètres Google** en
   bas à droite → colle le *Client ID* et le *Client Secret* → **Enregistrer**.
   (Alternative équivalente : les mettre dans `.env` —
   `GOOGLE_CLIENT_ID=...` / `GOOGLE_CLIENT_SECRET=...` — et redémarrer le
   brain ; le réglage saisi dans la Console reste prioritaire si les deux
   existent.)
5. Toujours dans **Intégrations** → **Connecter** sous Google Calendar,
   Google Drive, Gmail et/ou Google Contacts → choisis le compte Google →
   accepte. Répète
   pour chaque compte et chaque service à connecter — tout se passe depuis
   le site, aucun fichier à éditer après l'étape 4. Un même compte Google
   demande une connexion séparée par service (jetons indépendants, scopes
   différents).

Seules les étapes 1-3 (créer le client OAuth dans Google Cloud Console) ne
peuvent pas se faire depuis Jarvis : Google n'expose aucune API pour ça,
c'est un geste unique et obligatoire dans leur propre console, quelle que
soit l'application tierce.

Une fois connecté, depuis la Console web (le chat y dispatche déjà le
pilotage PC vers l'agent à outils) :
- « Jarvis, qu'est-ce que j'ai aujourd'hui ? » (et demain/cette semaine) → agenda
- « Jarvis, cherche le fichier X dans mon Drive » / « mes derniers fichiers Drive » → recherche
- « Jarvis, résume/trouve l'info sur Y dans le document Z » → recherche puis lecture
  du contenu (Docs/Sheets/Slides Google, PDF, texte brut — pas les images/vidéos)
- « Jarvis, ouvre-moi ce fichier » → ouvre le lien dans un onglet du navigateur (open_url)
- « Jarvis, crée un fichier sur mon Drive avec... » / « remplace le contenu de X par... » /
  « supprime/mets à la corbeille X » → écriture, avec une **bannière de confirmation**
  qui apparaît dans la Console (n'importe quelle vue) avant toute exécution ; sans
  réponse sous 90s ou en cas de refus, rien n'est fait. La suppression n'est jamais
  définitive (corbeille Drive, récupérable ~30 jours).
- « Jarvis, j'ai des mails importants/non lus ? », « résume le mail de X » → recherche
  (syntaxe Gmail native : is:unread, from:, subject:, newer_than:7d…) puis lecture
- « Jarvis, réponds à ce mail... » / « écris un mail à X pour... » → crée un
  **brouillon** (jamais envoyé automatiquement, aucune confirmation nécessaire pour
  un brouillon) ; « envoie-le » → confirmation obligatoire (destinataire + sujet
  affichés) avant l'envoi réel, irréversible
- « Jarvis, le numéro de X ? » / « l'email de X ? » → recherche dans les contacts
  connectés (lecture seule, aucune écriture possible)

Le scope Drive demandé est `drive` (lecture ET écriture, pas seulement
`drive.readonly`) — nécessaire pour agir sur n'importe quel fichier trouvé
par la recherche, pas seulement ceux créés par Jarvis. La sécurité vient de
la confirmation systématique, pas d'un scope restreint : même logique que
`run_powershell` côté desktop (accès large, confirmation sur ce qui compte).
Un compte connecté **avant** ce changement (scope lecture seule) doit être
reconnecté depuis Intégrations pour obtenir les droits d'écriture.

Ça ne fonctionne pas encore depuis la boucle vocale locale (le pilotage PC
vocal reste volontairement 100 % local aujourd'hui, voir
`docs/ROADMAP_MULTIDEVICE.md`) — sujet pour une prochaine étape si utile.

### Zoho Mail

Fournisseur distinct de Google (compte, identifiants, écran de config
séparés dans la Console — panneau **Intégrations**, bloc **Paramètres
Zoho**) :

1. [Console API Zoho](https://api-console.zoho.com/) (ou `.eu`/`.in`/`.com.au`/
   `.jp`/`.ca` selon le datacenter de ton compte Zoho — **la région compte**,
   se tromper fait échouer toute la connexion) → **Add Client** → **Server-based
   Applications**.
2. Dans *Authorized Redirect URIs*, colle exactement
   `http://127.0.0.1:8420/api/integrations/zoho/callback` (ou la valeur de
   `ZOHO_REDIRECT_URI` si changée).
3. Ouvre la Console web → **Intégrations** → déplie **Paramètres Zoho** →
   colle *Client ID*, *Client Secret*, choisis la **région** correspondant à
   ton compte → **Enregistrer**.
4. **Connecter** sous Zoho Mail → connecte-toi à ton compte Zoho → accepte.

Une fois connecté, depuis la Console web :
- « Jarvis, j'ai des mails sur Zoho ? », « résume le mail de X » → recherche puis lecture
- « Jarvis, écris un mail à X sur Zoho... » → compose un message — **confirmation à
  l'écran systématique**, y compris pour ce qui ressemblerait à un simple brouillon

**Points de vigilance technique** : contrairement à Gmail (API très stable
et bien documentée), Zoho Mail réserve deux pièges —
1. **Domaine d'API à part** : Zoho Mail n'est pas servi sous le domaine
   générique `api_domain` renvoyé par l'échange OAuth (celui-là pointe vers
   `www.zohoapis.<région>`, le gateway commun aux autres produits Zoho) —
   il a son propre domaine `mail.zoho.<région>`, reconstruit côté Jarvis à
   partir de la région choisie en Paramètres Zoho (confirmé en pratique,
   pas juste supposé).
2. La frontière exacte "brouillon" / "envoi direct" de l'API Zoho est moins
   nette que celle de Gmail dans sa documentation. Par prudence,
   `zoho_compose` confirme systématiquement à l'écran avant d'agir, même
   dans les cas où un simple brouillon suffirait avec Gmail.

Si la connexion ou l'envoi échoue malgré tout, le message d'erreur inclut
la réponse brute de Zoho pour diagnostiquer vite.

### Spotify

Fournisseur distinct, identifiants séparés (panneau **Intégrations**, bloc
**Paramètres Spotify**), pas de région à gérer :

1. [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
   → connecte-toi avec ton compte Spotify → **Create app**.
2. *App name*/*App description* : libres. *Redirect URI* : colle exactement
   `http://127.0.0.1:8420/api/integrations/spotify/callback`. Coche l'API
   **Web API**. Accepte les conditions → **Save**.
3. Sur la page de l'app créée → **Settings** → *Client ID* visible
   directement, *Client secret* derrière **View client secret**.
4. Console web → **Intégrations** → déplie **Paramètres Spotify** → colle
   les deux → **Enregistrer** → **Connecter** sous Spotify.

Une fois connecté, depuis la Console web :
- « Jarvis, c'est quoi ce titre ? » / « qu'est-ce qui joue ? » → lecture en cours
- « Jarvis, mets ma playlist détente » / « joue X de Y » → cherche d'abord dans
  tes playlists personnelles, sinon dans le catalogue public, lance la lecture
- « Jarvis, mets en pause » / « suivant » / « son à 40% » → contrôle direct,
  aucune confirmation (lancer/couper de la musique n'a rien d'irréversible)

**Prérequis à chaque usage** : un appareil Spotify doit déjà être actif
quelque part (app ouverte sur le téléphone, le PC, une enceinte connectée…)
— sans ça Spotify refuse toute commande de lecture, Jarvis le dit clairement
plutôt que d'échouer en silence.

### Jellyfin

Serveur personnel, pas de fournisseur tiers — **pas d'OAuth**, une simple
clé API. Panneau **Intégrations** → bloc **Jellyfin** :

1. Dans ton tableau de bord Jellyfin (en tant qu'admin) → **Tableau de
   bord** → **Clés API** → **+** → nomme-la (« Jarvis » par ex.) → copie la
   clé générée.
2. Console web → Intégrations → déplie **Jellyfin** → renseigne l'URL du
   serveur (ex. `http://192.168.1.50:8096`, l'adresse locale suffit si le
   brain tourne sur le même réseau), colle la clé API, et — si ton serveur
   a plusieurs comptes utilisateurs — précise le nom de celui à utiliser
   (reprise de lecture et nouveautés sont scopées par utilisateur ; sans
   ce champ, Jarvis prend le premier compte trouvé) → **Connecter**.

Une fois connecté, depuis la Console web :
- « Jarvis, j'ai quoi comme films avec X ? », « cherche la série Y » → recherche bibliothèque
- « Jarvis, qu'est-ce qui joue sur Jellyfin ? » → sessions actives, tous appareils
- « Jarvis, qu'est-ce que j'étais en train de regarder ? » → reprise de lecture
- « Jarvis, qu'est-ce qu'il y a de nouveau sur Jellyfin ? » → derniers ajouts

Lecture seule — pas de contrôle de lecture à distance (pause/lancer sur un
appareil précis) pour l'instant, contrairement à Spotify.

### Tisséo (transports Toulouse)

Gratuit, sans facturation (contrairement à Google Maps, envisagé puis
écarté pour cette raison) — une clé API simple, pas d'OAuth :

1. Envoie un email à **opendata@tisseo.fr** en demandant une clé API pour
   l'API temps réel (usage personnel) — pas de portail self-service, mais
   la demande n'est pas filtrée : la clé est fournie gratuitement, l'email
   sert juste à établir un contact côté Tisséo. Documentation développeur
   complète sur le [portail Open Data de Toulouse Métropole](https://data.toulouse-metropole.fr/explore/dataset/api-temps-reel-tisseo/).
2. Console web → Intégrations → déplie **Tisséo** → colle la clé API →
   **Enregistrer la clé**.
3. Toujours dans ce bloc, saisis le nom d'un arrêt (ex. « Jean Jaurès ») →
   **Ajouter comme arrêt favori**. Répète pour chaque arrêt à suivre
   (domicile, travail…) — ils apparaissent comme des cartes séparées à
   gauche et sont fusionnés au listing des prochains passages.

Une fois configuré, depuis la Console web :
- « Jarvis, quand passe le prochain bus ? » → prochains passages, tous arrêts
  favoris fusionnés (ou un seul si tu en nommes un précis)

**Confiance technique modérée** : l'API Tisséo est moins documentée dans ce
que je connais que Google/Spotify — si la recherche d'arrêt ou les horaires
échouent, le message d'erreur inclut la réponse brute de l'API pour
corriger vite le nom d'un paramètre au besoin.

### Itinéraires (OpenRouteService)

Alternative gratuite à Google Maps — écarté pour son exigence de carte
bancaire (voir `docs/ROADMAP_DISPLAY_INTEGRATIONS.md`). Clé API simple,
pas d'OAuth, pas de facturation :

1. Inscription gratuite sur [openrouteservice.org](https://openrouteservice.org)
   (bouton Sign Up) → une fois connecté, va sur le
   [tableau de bord](https://openrouteservice.org/dev/#/home) → section
   **Tokens**, en bas de page → demande un token gratuit → copie la clé
   générée.
2. Console web → Intégrations → déplie **Itinéraires (OpenRouteService)** →
   colle la clé → **Enregistrer la clé**.
3. Toujours dans ce bloc, renseigne ton **adresse domicile** →
   **Enregistrer le domicile** — sert d'origine par défaut quand tu ne
   donnes que la destination (optionnel : sans elle, Jarvis demande
   l'adresse de départ).

Une fois configuré, depuis la Console web :
- « Jarvis, combien de temps pour aller à X ? » → part de ton domicile enregistré
- « Jarvis, combien de temps de Y à X ? » → origine précisée, ignore le domicile
- « Jarvis, la distance jusqu'à Y ? » → idem, vélo/à pied sur demande (voiture par défaut)

Basé sur OpenStreetMap — bon pour un usage courant, mais moins précis que
Google sur le trafic temps réel aux heures de pointe.

### Home Assistant

Domotique — pas d'OAuth, un token longue durée. Panneau **Intégrations** →
bloc **Home Assistant** :

1. Dans Home Assistant, clique sur ton profil (photo en bas à gauche) →
   descends jusqu'à **Jetons d'accès de longue durée** → **Créer un jeton**
   → nomme-le (« Jarvis » par ex.) → copie le jeton (affiché une seule
   fois, à sauvegarder tout de suite).
2. Console web → Intégrations → déplie **Home Assistant** → renseigne
   l'URL de l'instance (ex. `http://192.168.1.x:8123`, adresse locale si
   le brain est sur le même réseau) → colle le jeton → **Connecter**.

Une fois connecté, depuis la Console web :
- « Jarvis, est-ce que la lumière du salon est allumée ? », « quelle température
  dans la chambre ? » → lecture d'état (nom en texte libre, pas d'entity_id à donner)
- « Jarvis, allume/éteins la lumière du salon » → contrôle direct, aucune confirmation
- « Jarvis, mets le chauffage du salon à 20 » → réglage thermostat

**Sécurité** : déverrouiller une serrure ou désarmer l'alarme déclenche une
**bannière de confirmation** avant d'agir (ça rend la maison moins sûre) —
verrouiller/armer, en revanche, jamais de confirmation (ça ne fait que
sécuriser). Tout le reste (lumières, prises, volets, chauffage…) reste un
contrôle direct sans friction, comme Spotify.

> Voix personnalisée : le dossier `voice/` contient `jarvis-high.onnx` (Piper).
> Pour l'utiliser, enregistrez-la dans votre instance Speaches puis pointez
> `TTS_MODEL`/`TTS_VOICE` dessus dans `.env`.

## Sécurité

- **Commandes destructrices** (rm, format, shutdown…) → bulle de confirmation
  visuelle obligatoire avant exécution.
- **Contenu externe** (écran, OCR, fichiers, presse-papier, URL) → marqué non
  fiable ; toute commande PowerShell qui suit dans le même tour d'agent exige
  une confirmation humaine (anti-injection de prompt).
- Une commande apprise n'est jamais mémorisée si elle est destructrice.

## Personnalisation

- `data/modes.json` — modes contextuels et leurs consignes
- `data/routines.json` — routines (`speak`, `speak_time`, `speak_weather`,
  `set_mode`, `powershell`, `open_url`)
- `data/commands.json` — commandes instantanées (aussi apprises automatiquement)
- `data/context.json` — contexte permanent injecté dans le prompt

## Développement

```
python -m agents.desktop.ui.hud             # démo du HUD seul (états simulés)
python -m agents.desktop.ui.preview_render  # rendu PNG de chaque état → agents/desktop/build_preview/
```

La v1 monolithique reste consultable dans `legacy/`.

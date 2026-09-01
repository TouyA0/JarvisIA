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

### Google (Calendar, Drive)

Panneau **Intégrations** de la Console web (`ROADMAP_DISPLAY_INTEGRATIONS.md`)
— comptes multiples supportés par service, résultats fusionnés
automatiquement. Un seul Client ID/Secret Google sert pour tous les
services (Calendar, Drive, et les suivants sur le même modèle) — mise en
place une fois, ~5 min :

1. [Google Cloud Console](https://console.cloud.google.com/) → nouveau
   projet (ou existant) → **APIs & Services** → activer **Google Calendar
   API** ET **Google Drive API** (les deux, même si tu ne comptes utiliser
   qu'un des deux services pour l'instant — inactive, l'API bloque juste
   silencieusement les appels le jour où tu voudras l'autre).
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
5. Toujours dans **Intégrations** → **Connecter** sous Google Calendar et/ou
   Google Drive → choisis le compte Google → accepte. Répète pour chaque
   compte et chaque service à connecter — tout se passe depuis le site,
   aucun fichier à éditer après l'étape 4. Un même compte Google demande une
   connexion séparée par service (jetons indépendants, scopes différents).

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

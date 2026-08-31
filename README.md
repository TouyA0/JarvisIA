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

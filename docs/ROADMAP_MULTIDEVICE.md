# J.A.R.V.I.S. multi-appareils — Roadmap de mise en place

Complète `ROADMAP.md` (qui couvre les features de l'assistant lui-même :
voix, mémoire, proactivité…). Ce document couvre uniquement **le chantier
d'architecture** : passer d'un agent desktop monolithique à un cerveau
central + interface web + agents multi-appareils.

Le visuel est déjà fait : `docs/site web design/Jarvis.dc.html` (système de
design complet + 5 écrans HTML/CSS statiques). Cette roadmap part de ce
visuel comme cible et détaille tout ce qu'il reste à construire derrière.

Légende effort : ▲ = un soir · ▲▲ = un week-end · ▲▲▲ = plusieurs jours/semaines

---

## 0. Ce que le design impose déjà comme cible

Le fichier design contient 5 écrans, qui définissent le périmètre fonctionnel
attendu — chaque phase ci-dessous construit vers l'un d'eux :

| Écran design | Ce qu'il faut derrière |
|---|---|
| **01 Console** | chat central, barre de commande vocale/texte, statut système en direct |
| **02 Centre d'appareils** | registre d'appareils connectés (nom, type, statut), appairage d'un nouvel appareil |
| **03 Focus appareil** | vue détaillée d'un appareil : aperçu live (screenshot), contrôle distant, capteurs, journal d'activité |
| **04 Routines & automatisations** | routines qui enchaînent des actions sur plusieurs appareils |
| **05 Mobile** | les 3 premiers écrans réadaptés (pas juste redimensionnés) pour usage au pouce |

Palette/typo déjà figées dans le design (OKLCH, Space Grotesk + IBM Plex
Sans/Mono) — à extraire en design tokens réutilisables plutôt que
recopiées à la main écran par écran.

---

## Phase 0 — Fondations transverses ▲▲ · ✅ fait

Tout le reste en dépend, à faire en premier.

- **Protocole `agents/protocol/`** ✅ — `messages.py` : 5 messages Pydantic
  (`DeviceRegister`, `RegisterAck`, `DeviceStatus`, `CommandDispatch`,
  `CommandResult`) + `parse_message()`. `auth.py` : génération de token
  d'appairage (`secrets.token_urlsafe`) — la vérification côté brain
  arrive avec `brain/devices.py` en Phase 1.
- **Auth minimale** ✅ — un token opaque par agent, pas de comptes. Le
  brain valide à la connexion (`RegisterAck.ok`), à implémenter Phase 1.
- **Choix techniques front** ✅ — **React + Vite** pour `web/`.
- **Choix techniques back** ✅ — **FastAPI + uvicorn + websockets**, deps
  posées dans `brain/requirements.txt` (séparé de `requirements.txt` qui
  reste les deps de l'agent desktop).

## Phase 1 — Brain minimal (serveur central) ▲▲▲ · 🟡 partiellement fait

Sur le PC fixe, un process qui tourne en continu.

- ✅ `brain/server.py` : FastAPI, teste OK (`/api/health` répond, routes
  `/ws/chat` et `/ws/agent` enregistrées, serveur démarre réellement via
  uvicorn). Sert `web/` en statique — pas encore branché, `web/` est
  toujours vide (Phase 2).
- ✅ `brain/devices.py` : registre en mémoire des agents connectés
  (`DeviceRegistry`), dispatch de commande avec corrélation par
  `request_id` — écrit mais **rien ne l'appelle encore**, voir plus bas.
- ✅ **Migration partielle de la logique de décision** vers `brain/core/` :
  `chat.py`, `prompts.py`, `history.py`, `usage.py`, `memory.py`,
  `modes.py`, `convlog.py`. Ces modules ne touchaient déjà que
  config/API/fichiers — aucune dépendance à l'audio ou à l'UI locale,
  migration directe. `brain/config.py`, `brain/state.py`, `brain/clients.py`
  créés en support. L'agent desktop continue de tourner exactement comme
  avant (imports mis à jour, rien de cassé — compile + testé).
- 🔲 **Restent dans `agents/desktop/brain/` (report Phase 3 assumé)** :
  `router.py`, `commands.py`, `agent.py`, `vision.py`. Ces quatre modules
  appellent `agents/desktop/tools/*` en direct (PowerShell, clavier/souris,
  écran) — les transformer en dispatch réseau vers `brain/devices.py`
  suppose que l'agent desktop sache déjà répondre à un `CommandDispatch`,
  ce qui est le travail de la Phase 3. Pas de sens à le faire dans le
  désordre : `brain/devices.py.dispatch()` existe et est prêt, mais reste
  non branché jusque-là.
- 🔲 **Dette connue à traiter en Phase 3** : `brain/core/memory.py`
  importe `agents.desktop.brain.commands.is_learn_command` (fonction pure
  de matching texte) — dépendance dans le mauvais sens, tolérée pour
  l'instant (import différé, ne casse rien tant que les deux packages
  sont sur la même machine), à corriger en scindant `commands.py` entre
  matching (→ `brain/core`) et exécution locale (→ `agents/desktop`).
- 🔲 **Auth réelle** : `brain/server.py` accepte aujourd'hui n'importe quel
  token non vide (`TODO` explicite dans le code) — la vérification contre
  un registre persistant (`data/devices.json`) reste à faire, avant
  d'ouvrir le brain à autre chose que du test en local.
- ✅ `data/` reste la source de vérité (mémoire, modes, usage…) ; `brain/`
  la possède désormais pour tout ce qui a migré.
- Un seul agent supporté au départ (le desktop) pour valider le
  brain avant de généraliser — confirmé par la scope ci-dessus.

## Phase 2 — Web UI : Console ▲▲ · ✅ fait

- ✅ Scaffolding front : React + Vite (`web/`), tokens couleur/typo extraits
  du design dans `web/src/styles/tokens.css` (palette OKLCH, Space
  Grotesk + IBM Plex Sans/Mono — copiés, pas réinventés).
- ✅ `brain/server.py` mis à jour : proxy Vite (`/api`, `/ws` → :8420 en
  dev) configuré dans `web/vite.config.js`.
- ✅ Écran **01 Console** codé (`web/src/components/Console.jsx`) : dock,
  topbar avec statut cerveau, hub radial animé (breathe/spin), barre de
  commande fonctionnelle. Rail de droite (état système / aperçu appareil /
  activité) volontairement pas codé — décoratif dans le design, dépend
  du multi-appareils (Phase 4), pas de sens de le figer maintenant.
- ✅ **Testé de bout en bout dans un vrai navigateur** : question tapée →
  `useChat.js` (WebSocket) → `brain/server.py` (`/ws/chat`) →
  `brain/core/chat.py` (Ollama indisponible → repli Claude, confirmé en
  usage réel) → réponse streamée affichée dans l'UI. Capture d'écran
  vérifiée, rendu conforme au design.
- Rien côté pilotage PC ni voix à ce stade, comme prévu — uniquement la
  chaîne web ↔ brain.

## Phase 3 — Agent desktop en client réseau ▲▲▲ · 🟡 partiellement fait

- ✅ `agents/desktop/agent_client.py` : client WebSocket complet — identité
  stable persistée (`data/device_id.json`), enregistrement (`device.register`),
  heartbeat périodique, écoute `command.dispatch`, exécute via
  `agents/desktop/tools/registry.py` (le même registry qu'utilise déjà
  l'agent Claude local — aucun outil réécrit), renvoie `command.result`.
  Reconnexion automatique si le brain redémarre ou est injoignable.
- ✅ `brain/server.py` : `GET /api/devices` (liste des appareils connectés)
  et `POST /api/devices/{id}/dispatch` (envoie une commande, attend le
  résultat) — deviendra le point d'entrée du bouton « exécuter » de Focus
  appareil en Phase 4.
- ✅ **Testé en conditions réelles, pas juste compilé** : brain lancé,
  agent desktop connecté et visible dans `/api/devices`, commande
  `read_clipboard` dispatchée du brain vers l'agent à travers le réseau,
  résultat réel reçu en retour. Cas d'erreur vérifié (appareil inconnu →
  404). Déconnexion propre vérifiée (l'appareil disparaît du registre).
- 🔲 **Décision d'intégration NON prise** : `agent_client.py` est un canal
  **parallèle et optionnel** — il ne remplace pas encore `runtime.py`.
  `router.py`/`commands.py`/`agent.py` continuent d'exécuter les outils en
  local comme avant, la boucle vocale n'est pas touchée. La question de
  savoir SI et COMMENT faire router ces trois modules à travers ce canal
  (au lieu d'appeler `agents.desktop.tools.registry` en direct) reste
  ouverte — voir la section suivante pour pourquoi elle est reportée
  volontairement plutôt que tranchée dans le désordre.
- 🔲 HUD PyQt6 : question de le garder/retirer non tranchée, comme prévu.
- 🔲 Lancement auto au démarrage de Windows (F39) : pas fait, reste
  pertinent une fois l'agent réellement en usage quotidien.

### Suite : `runtime.py` connecté au brain, en tâche de fond ✅

Plutôt que de transformer `router.py`/`commands.py`/`agent.py` pour
qu'ils appellent le dispatch réseau à la place de l'exécution locale
(ce qui aurait ajouté de la latence pour zéro bénéfice tant qu'il n'y a
qu'un seul appareil, PC fixe = celui qui écoute), l'intégration retenue
est plus simple et sans risque : `runtime.py` lance
`agent_client.run()` dans un **thread daemon supplémentaire**, en plus
de la boucle vocale existante — pas à sa place.

- `agents/desktop/runtime.py::_start_brain_link()` — démarre le client
  brain dans un thread à part (`asyncio.run()` dans son propre thread,
  la boucle Qt/audio existante reste inchangée). N'essaie **jamais** si
  l'appareil n'est pas déjà appairé (le flux d'appairage attend une
  saisie clavier — inconcevable dans un thread caché du HUD). Gardé
  **désactivé par défaut** (`config.BRAIN_ENABLED`, `.env`) : le brain ne
  fait pas encore partie de `start_jarvis.bat`, donc aucun changement de
  comportement tant qu'on n'active pas explicitement.
- `agent_client.py` : bruit de reconnexion réduit (un seul message par
  coupure au lieu d'un toutes les 5s) — nécessaire maintenant qu'il
  tourne en silence à l'année plutôt que dans un terminal de test.
- **Testé en conditions réelles** (sans passer par le HUD Qt, en appelant
  `_start_brain_link()` directement — la fonction ne dépend pas de Qt) :
  les trois branches vérifiées — désactivé → aucun thread ; activé sans
  appairage → message d'aide, aucun thread ; activé + appairé + brain
  lancé → connexion réelle confirmée en ligne côté `/api/devices` avec
  les bonnes capacités pendant que le thread tourne.
- 🔲 **Reste non fait, sciemment** : `router.py`/`commands.py`/`agent.py`
  n'appellent toujours pas le dispatch réseau — ils continuent d'exécuter
  localement. Le PC fixe est maintenant à la fois exécutant vocal local
  ET agent joignable à distance, mais rien ne route encore une commande
  d'un appareil vers un AUTRE — ça n'a de sens qu'avec un deuxième agent
  réel (portable ou mobile) à cibler, qui n'existe pas encore.
- 🔲 Le sujet `state.stop_speaking`/`state.stop_agent` (interruption à
  distance) reste ouvert mais n'était pas nécessaire pour cette
  intégration — seulement pour un futur bouton « stop » côté web.

### Suite : voix et web unifiées sur la même conversation ✅

Jusqu'ici, la voix (ce process) et la Console web (`brain/server.py`)
tournaient chacune leur propre instance de `brain.core.chat`/`history` —
deux conversations, deux mémoires, jamais synchronisées (limite notée
explicitement plus haut). Résolu sans dupliquer aucune logique de
décision : la voix parle maintenant au **même** `/ws/chat` que la
Console web (Phase 2), donc au même historique.

- `agents/desktop/brain/remote_chat.py` (nouveau) — même contrat que
  `brain.core.chat.ask_stream` (générateur synchrone de phrases), mais
  passe par `/ws/chat` via `websockets.sync.client` au lieu d'appeler
  `brain.core.chat` en local. Repli automatique sur le chat local si le
  brain est désactivé, injoignable, ou si la connexion tombe après coup
  (même logique de non-mélange de réponses que le repli Ollama → Claude
  existant : on annonce l'interruption plutôt que d'enchaîner une
  réponse d'une autre source).
- `brain/server.py::ws_chat` renvoie désormais la source
  (`ollama`/`claude`) dans `chat.done`, pour que le badge modèle du HUD
  reste correct même en passant par le réseau.
- `runtime.py` appelle `remote_chat.ask_stream` à la place de
  `brain.core.chat.ask_stream` pour la conversation pure (pas pour le
  pilotage PC, qui reste local — voir plus haut).
- **Testé en conditions réelles, les 3 branches** : désactivé → zéro
  tentative réseau, direct au chat local ; activé + brain injoignable →
  échec détecté immédiatement (`WinError 10061`), repli local propre ;
  activé + brain lancé → réponse réelle reçue via `/ws/chat`, source
  correctement remontée. Testé à part, sans passer par le process
  `jarvis.py` réel de Quentin pour ne pas le perturber.
- Portée volontairement limitée à la conversation pure : le pilotage PC
  (`router.py`/`commands.py`/`agent.py`) exécute toujours en local,
  inchangé.

## Phase 4 — Centre d'appareils & Focus appareil ▲▲▲ · 🟡 partiellement fait

- ✅ **Vrai appairage, plus de token accepté à l'aveugle** (résout le TODO
  de sécurité laissé en Phase 1) :
  - `agents/protocol/messages.py` — `RegisterAck.issued_token` ajouté.
  - `brain/pairing.py` — codes à usage unique (format `XXX-XXX`, 5 min,
    en mémoire uniquement).
  - `brain/device_store.py` — appareils appairés persistés
    (`data/devices.json`, token définitif par appareil).
  - `brain/server.py` — `/ws/agent` accepte un code d'appairage (échangé
    contre un token permanent) OU un token déjà connu ; refuse tout le
    reste. `POST /api/pairing/code`, `GET /api/devices` (fusionne
    connectés + connus hors ligne), `DELETE /api/devices/{id}` (révoque).
  - `agents/desktop/agent_client.py` — demande le code au premier
    lancement (`JARVIS_PAIRING_CODE` ou saisie clavier), sauvegarde le
    token émis, se reconnecte ensuite sans rien redemander ; distingue
    proprement « brain injoignable » (retente) de « token révoqué »
    (s'arrête avec un message clair plutôt que boucler dans le vide).
- ✅ Écran **02 Centre d'appareils** (`web/src/components/Devices.jsx`) :
  liste des appareils (statut, capacités, bouton Oublier) + panneau
  d'appairage (génération de code, instructions). `Dock`/`Frame`/`Reactor`
  extraits en composants partagés (Console les utilise aussi désormais).
  Rafraîchi par polling (`useDevices.js`, 3s) — pas de WebSocket dédié,
  suffisant pour un écran de gestion.
- ✅ **Testé en conditions réelles, cycle complet** : code généré dans le
  navigateur → collé dans un vrai `agent_client.py` lancé en parallèle →
  apparaît « en ligne » dans l'UI → reconnexion automatique vérifiée
  (token sauvegardé, aucune ressaisie) → révocation testée (`Oublier`
  dans l'UI → l'agent se fait couper, détecte le refus, s'arrête avec un
  message clair au lieu de boucler). Capture d'écran vérifiée.
- ✅ **Écran 03 Focus appareil** (`web/src/components/Focus.jsx`) —
  accessible depuis un bouton « Focus » sur chaque carte d'appareil
  (Centre d'appareils), pas depuis le dock seul (n'a de sens qu'une fois
  un appareil choisi). Fonctionnalités **réelles**, pas de maquette :
  - **Capturer** — dispatch réel de `take_screenshot` vers l'agent,
    image reçue et affichée. Testé en vrai : capture d'écran effective
    du PC reçue via le brain et affichée dans le navigateur.
  - **Journal** — `brain/activity.py` (nouveau) enregistre chaque
    dispatch (outil, succès/échec, horodatage) par appareil, exposé via
    `GET /api/devices/{id}/activity`. Testé : l'entrée `take_screenshot`
    apparaît bien après une capture.
  - **Verrouiller** — dispatch `run_powershell` (verrouillage Windows),
    confirmation JS avant envoi. **Non testé en direct** volontairement
    — l'aurait fait sur la machine réellement utilisée pour ce test,
    donc l'aurait verrouillée sous mes propres yeux. Le mécanisme
    sous-jacent (dispatch → `run_powershell`) est déjà prouvé par les
    tests Phase 3.
  - **Volontairement absents** : flux vidéo live (le design en montre
    un, mais rien ne le permet aujourd'hui — juste une capture à la
    demande), section Capteurs (micro distant/localisation — concepts
    mobile, aucun sens pour un agent desktop), bouton Transférer (aucune
    infra de transfert de fichier entre appareils).
- 🔲 **Routage contextuel** (« ouvre ça sur mon portable ») — pas fait,
  dépend du même chantier que la fin de la Phase 3 : `router.py`/
  `commands.py`/`agent.py` n'appellent toujours pas le dispatch réseau,
  donc il n'y a rien à cibler contextuellement pour l'instant.

## Phase 5 — Routines cross-device ▲▲ · ✅ fait (périmètre manuel)

- ✅ `brain/routines.py` (nouveau, côté brain — pas une extension de
  `agents/desktop/services/routines.py`, qui reste mono-appareil et
  vocal, système séparé exprès) : routines = séquences d'étapes
  `{device_id, tool, args}`, stockées dans
  `data/cross_device_routines.json`, exécutées via
  `brain/devices.py::registry.dispatch()` (Phase 3), journalisées via
  `brain/activity.py` (Phase 4). S'arrête à la première étape en échec.
- ✅ Écran **04 Routines** (`web/src/components/Routines.jsx`) : liste
  des routines avec progression en direct pendant l'exécution, builder
  (nom + étapes, appareil + action par étape). Actions volontairement
  **curatées** (Capturer, Verrouiller, Ouvrir une URL) — pas de console
  PowerShell libre dans le builder, une routine s'exécute d'un clic sans
  reconfirmation étape par étape, donc pas de commande arbitraire à ce
  niveau (même logique de prudence que Focus appareil).
- ✅ **Testé en conditions réelles** : routine à 2 étapes créée
  (Capturer × 2, sur l'appareil desktop appairé), lancée depuis le
  navigateur, progression `2 / 2` observée, confirmée aussi dans le
  journal d'activité côté brain (2 `take_screenshot` réussis). Suppression
  testée. Le step « Verrouiller » a été codé mais **jamais lancé** en
  test — même prudence que pour Focus appareil, pour ne pas verrouiller
  la machine de test.
- 🔲 **Déclencheur manuel uniquement** — pas de déclencheur automatique
  (horaire, vocal, arrivée sur un lieu). Le design en montre (« Focus
  travail » activé/désactivé façon interrupteur), mais un interrupteur
  qui ne déclenche rien tout seul serait un mensonge dans l'interface —
  volontairement pas construit. Nécessiterait un scheduler et/ou un
  branchement dans la boucle vocale (Phase 9), aucun des deux n'existe.

## Phase 6 — Accès distant + mobile web ▲▲ · ✅ fait

- ✅ **Web responsive, pas un simple reflow** : `useIsMobile.js` (seuil
  768px, `matchMedia`) pilote une vraie réorganisation, pas juste des
  colonnes qui rétrécissent. `Dock.jsx` passe en barre basse (comme
  l'écran 05 du design) au lieu de barre latérale. `Frame.jsx` passe en
  plein écran (fini la fenêtre flottante à coins arrondis). Les panneaux
  latéraux (appairage dans Devices, builder dans Routines, infos/journal
  dans Focus) passent sous le contenu principal au lieu d'à côté.
  Console n'a rien demandé de spécifique (déjà fluide).
- ✅ **Testé en conditions réelles** : viewport 375×812 (mobile) — dock en
  bas confirmé (positions x variables/y fixe), cartes appareil pleine
  largeur (grille 2 colonnes → 1), builder Routines pleine largeur, zéro
  débordement horizontal sur les 4 écrans. Viewport 1280×800 (desktop) —
  sidebar verticale confirmée intacte, aucune régression.
- ✅ **Accès distant** — fait, sans Tailscale : Quentin avait déjà un VPN
  WireGuard vers un Raspberry Pi sur le même réseau que le PC fixe,
  avec `AllowedIPs` incluant déjà le sous-réseau maison côté client.
  Réutilisé tel quel plutôt que d'ajouter une nouvelle brique — cohérent
  avec « ne pas exposer le brain publiquement » (il n'a pas
  d'authentification sur `/ws/chat`, pas prêt pour internet).
  **Deux vrais blocages trouvés et corrigés en testant en conditions
  réelles** (téléphone en 4G, wifi coupé, VPN activé) :
  - Windows bloquait les connexions entrantes sur le port 8420 —
    résolu avec une règle de pare-feu (`New-NetFirewallRule`), qui doit
    être lancée dans un PowerShell **administrateur** (sinon échec
    silencieux « Access is denied »).
  - **Le vrai bogue** : le brain que j'avais lancé pendant mes tests du
    jour tournait avec `--host 127.0.0.1` (habitude prise pendant les
    tests locaux) au lieu de `0.0.0.0` — donc injoignable depuis le
    réseau quoi qu'il arrive, pare-feu ou pas. `brain/config.py` a
    pourtant `0.0.0.0` comme défaut ; le problème venait uniquement des
    commandes manuelles tapées pendant la session de test, pas du code.
    À retenir : toujours lancer avec `python -m brain.server` (utilise
    les bons défauts) ou `--host 0.0.0.0` explicite, jamais
    `--host 127.0.0.1` si un accès réseau est prévu.
- Testé : Console web chargée et fonctionnelle depuis un téléphone en
  4G, VPN activé, aucun wifi partagé avec le PC fixe.

## Phase 7 — Agent mobile ▲▲▲

- `agents/mobile/` : companion app (React Native ou app native légère)
  qui se connecte au brain comme un agent à part entière — nécessaire
  pour tout ce qu'un navigateur ne peut pas faire (notifications
  système, capture d'écran du téléphone, exécution en arrière-plan).
- Périmètre minimal réaliste : recevoir des notifications poussées par le
  brain + remonter un statut basique. Le contrôle complet (façon agent
  desktop) est un chantier à part, à ne pas sous-estimer sur iOS
  (contraintes Apple sur l'exécution en arrière-plan).

## Phase 8 — Montre connectée (exploratoire, pas avant le reste) ▲▲▲

- Pas une vraie UI web : companion minimaliste (Wear OS/Apple Watch) qui
  parle à l'API du brain pour des interactions courtes (statut,
  réponses/notifications courtes, dictée vocale). À revisiter une fois
  les phases 1-6 stables — inutile d'y penser avant.

## Phase 9 — Voix dans le navigateur ▲▲▲ · 🟡 première version faite

Identifiée le 2026-08-15 : condition réelle pour que le HUD PyQt6 puisse
un jour disparaître au profit du seul web. Cadrée puis codée le même
jour, avec deux décisions prises avec Quentin avant d'écrire du code :

- **Détection** : ni mot d'éveil continu (fragile dans un onglet), ni
  bouton « maintenir pour parler » — une **fenêtre d'écoute armée** de
  10 min pendant laquelle le navigateur transcrit en continu et cherche
  « Jarvis » dans le texte (proposition de Quentin).
- **STT/TTS** : réutiliser **Speaches** (Whisper + Piper), déjà utilisé
  par l'agent desktop — pas de nouvelle dépendance, reste chez toi
  (LAN ou Tailscale). Décidé plutôt que l'API Web Speech (aurait envoyé
  l'audio à Google, contraire au principe local-first) ou un STT WASM
  embarqué (rien de prouvé dans ce projet).

### Ce qui a été construit

- ✅ `brain/speech.py` + `brain/config.py` (config Speaches côté brain,
  mêmes valeurs que l'agent desktop) — `transcribe()`/`synthesize()`,
  jamais d'exception (un segment illisible ne casse pas la fenêtre
  d'écoute).
- ✅ `brain/server.py` — `POST /api/speech/transcribe` (upload audio →
  texte), `POST /api/speech/synthesize` (texte → MP3).
- ✅ `web/src/lib/fuzzyWakeWord.js` — recherche « Jarvis » tolérante.
  **Bug réel trouvé par Quentin au premier essai** : le seuil initial
  (distance de Levenshtein ≤ 2) était bien trop large — des mots
  français courants (« jamais », « jadis ») tombaient dans cette marge
  et déclenchaient le mot d'éveil sur n'importe quelle phrase. Resserré
  à ≤ 1 (quasi-exact) + liste explicite des déformations Whisper
  réellement observées (« Javi », distance 2) plutôt que d'élargir la
  tolérance générale pour ce seul cas. Revalidé : « jamais »/« jadis »
  ignorés, « Javi »/« Jarvis » toujours détectés.
- ✅ `web/src/lib/useVoice.js` — fenêtre armée, enregistrement par
  segments de 4s (MediaRecorder), boucle transcription → recherche du
  mot → capture de la commande qui suit, `pause()`/`resume()` pour ne
  pas réécouter pendant que Jarvis répond ou parle (pas de barge-in,
  volontairement — sujet à part).
- ✅ Bouton micro dans `Console.jsx` — armé/désarmé au clic, statut
  visible (écoute / transcription / Jarvis parle), réponse vocale
  synthétisée et jouée automatiquement **uniquement** si la question
  venait de la voix (le texte tapé ne déclenche jamais de lecture).
- 🐛 **Bug trouvé et corrigé pendant les tests** : `python-multipart`
  manquant faisait planter le brain entier au démarrage dès l'ajout de
  l'upload de fichier — ajouté à `brain/requirements.txt`.

### Testé en conditions réelles (sans microphone, ici)

- ✅ Aller-retour Speaches complet : synthèse Piper → transcription
  Whisper, en ligne de commande ET via un vrai `fetch()` depuis le
  navigateur (proxy Vite inclus) — MP3 réel reçu et lisible.
- ✅ `fuzzyWakeWord.js` validé en Node avec de la vraie sortie Whisper
  déformée (« Javi » détecté, extraction correcte de la commande qui
  suit ; phrases sans rapport correctement ignorées).
- ✅ Robustesse UI : accès micro refusé (bloqué dans cet environnement de
  test) → message d'erreur affiché, pas de plantage, bouton revient à
  l'état inactif proprement.
- ✅ Non-régression : une question tapée continue de fonctionner
  normalement et ne déclenche **jamais** de synthèse vocale.

**Retour utilisateur (Quentin) après premier essai réel** : aucun moyen
de savoir si le micro écoute, transcrit, ou a compris quoi que ce soit —
tout était invisible (juste un tooltip au survol). Corrigé le même jour :
`useVoice.js` expose maintenant `lastTranscript` (dernier segment
transcrit, même sans « Jarvis » dedans) et `wakeWordHeard` (flash
« ✓ Jarvis détecté » 2s) ; `Console.jsx` affiche un bandeau **toujours
visible** (pas un tooltip) au-dessus de la barre de commande avec le
statut en clair + « entendu : « … » ». Validé avec un flux audio
synthétique (silence) envoyé au vrai pipeline d'enregistrement : compte
à rebours, statut, et « entendu : « (silence) » » confirmés à l'écran.

### Abandonné : détection par transcription + comparaison de texte

L'approche ci-dessus (transcrire en continu, chercher « Jarvis » dans le
texte) a été **remplacée** le jour même après un vrai faux-positif en
usage réel : « jamais » déclenchait le mot d'éveil sur n'importe quelle
phrase (distance de Levenshtein trop permissive — voir le bug documenté
plus haut). Un premier resserrement du seuil a réduit le problème sans
le résoudre : le défaut est structurel, pas un réglage — comparer du
*texte* n'a rien à voir avec reconnaître un *son*. Quentin a demandé
pourquoi ne pas réutiliser directement le vrai modèle du PC. Réponse
honnête : raccourci pris pour livrer vite avec ce qui existait déjà
(Speaches), sans assez peser le coût de fiabilité. Remplacé dans la
foulée par la vraie détection acoustique ci-dessous.

### Le vrai modèle, porté dans le navigateur ✅

Même modèle exact que le PC (`agents/desktop/wakeword/jarvis_wakeword.tflite`),
tournant en local dans le navigateur — plus aucun texte à comparer, plus
aucun audio envoyé au réseau tant que « Jarvis » n'est pas vraiment
détecté (exactement le principe qu'on avait posé en Phase 0, avant de le
contourner pour la voix web).

- ✅ **Conversion du modèle** : TFLite → ONNX (`tf2onnx`), validée
  bit-identique au modèle original sur 10 échantillons réels (écart
  `0.000000`).
- ✅ **Port fidèle du prétraitement** (`web/src/lib/wakeWordFeatures.js`) :
  FFT, banc de filtres mel (échelle Slaney), passage en dB, DCT — les
  mêmes formules exactes que `librosa.feature.mfcc`, réécrites en JS pur
  (FFT radix-2 maison, aucune dépendance). **Validé numériquement**
  contre la vraie sortie librosa (Python) sur 10 échantillons : écart
  absolu max `0.00006` (bruit de calcul flottant, négligeable).
- ✅ **Pipeline complet bout en bout** (audio → MFCC JS → modèle ONNX)
  validé en Node.js avec `onnxruntime-node` : sur les 10 mêmes
  échantillons (5 « Jarvis », 5 négatifs), les scores obtenus en
  JavaScript sont identiques aux scores Python/TFLite originaux à
  `0.00000` près — positifs comme négatifs.
- ✅ `web/src/lib/wakeWordDetector.js` — charge le modèle ONNX
  (`onnxruntime-web`, backend WASM), même seuils que le PC (score ≥ 0.90,
  2 détections consécutives, cooldown 2s, filtre RMS avant même de
  lancer l'inférence).
- ✅ `web/public/wakeword-worklet.js` + `useWakeWordDetector.js` —
  capture micro continue via `AudioWorklet` (hors thread principal),
  fenêtre glissante de 1.5s, scoring toutes les ~128ms — même cadence
  que `agents/desktop/audio/wakeword.py`.
- ✅ `useVoice.js` réécrit : la détection ne dépend plus de Whisper ni du
  brain. Une fois « Jarvis » détecté localement, la commande qui suit
  est enregistrée et envoyée à `/api/speech/transcribe` (Speaches via le
  brain) — ce bout-là reste inchangé, c'est le bon usage de la
  transcription réseau (transcrire une vraie commande, pas deviner un
  mot d'éveil).
- ✅ **Plus de fenêtre à durée limitée** : comme rien ne part au réseau
  tant que le mot n'est pas détecté, plus besoin du compte à rebours de
  10 min — ça écoute tant que c'est armé, comme sur PC.
- 🐛 **Bug de taille d'asset trouvé et corrigé** : l'import par défaut
  d'`onnxruntime-web` embarquait un binaire WASM de 26 Mo (variante
  WebGPU/JSEP) dans le bundle Vite. Corrigé en important le sous-module
  `onnxruntime-web/wasm` + une condition de résolution Vite dédiée
  (`onnxruntime-web-use-extern-wasm`) pour ne charger que le binaire WASM
  simple (13 Mo, un seul téléchargement, mis en cache par le navigateur
  ensuite).
- 🐛 **Bug de serveur de dev trouvé et corrigé** : le serveur de dev Vite
  refuse par conception l'import dynamique de fichiers `public/`
  (`ort-wasm-*.mjs`), ce dont `onnxruntime-web` a besoin pour charger son
  runtime — erreur uniquement en dev (`npm run dev`), pas en production.
  Corrigé en branchant enfin `brain/server.py` pour servir `web/dist` en
  statique (prévu depuis la Phase 2, jamais fait) : `npm run build` dans
  `web/`, puis tout se sert depuis `http://localhost:8420`, plus besoin
  du serveur de dev séparé pour tester cette fonctionnalité.

**Testé en conditions réelles, avec de vrais enregistrements — pas
seulement en isolation :**

- ✅ Un vrai extrait audio « Jarvis » (`samples_jarvis/jarvis_01.wav`),
  joué dans le navigateur comme si c'était le micro (technique de
  substitution audio, faute de vrai micro dans cet environnement de
  test) → **détection déclenchée**, capture de la commande qui suit
  activée.
- ✅ **Contre-épreuve** : un vrai négatif (`samples_negatifs/negatif_01.wav`),
  joué trois fois de suite → **aucune détection**, aucun déclenchement.
- ✅ Une simple tonalité pure (220 Hz) → score proche de zéro, cohérent
  avec les scores négatifs mesurés en Python (aucune ressemblance
  spectrale avec de la parole).

### Suite : deux vrais bugs remontés par Quentin en usage réel, corrigés

**1. Réponses génériques (« Dûment noté, Monsieur » en boucle).** Cause :
la commande était enregistrée sur une durée **fixe** de 4s après la
détection, sans tenir compte du fait qu'on enchaîne naturellement
« Jarvis, [question] » sans pause — le début de la question pouvait être
coupé, Whisper transcrivait du vide/du bruit, et le LLM répondait par
une confirmation générique faute de comprendre. Corrigé en remplaçant la
capture à durée fixe par une **capture pilotée par le silence** (même
principe que `agents/desktop/audio/stt.py` côté PC — pas de VAD neuronal
ici, un seuil RMS suffit une fois qu'on sait qu'on est juste après un
« Jarvis » confirmé) : `useWakeWordDetector.js::captureCommand()` attend
le début de la parole (jusqu'à ~2.9s), capture jusqu'à ~380ms de silence
ou 9s max, avec un pré-tampon pour ne pas couper le tout début.
`encodeWav.js` encode le résultat en WAV PCM (remplace l'ancien
enregistrement MediaRecorder/webm à durée fixe).

**2. Détection moins fiable que sur PC.** Cause probable : le navigateur
applique par défaut un traitement du signal (suppression de bruit, écho,
gain automatique) avant même que le code ne reçoive l'audio — ça déforme
le signal par rapport à l'audio brut sur lequel le modèle a été
entraîné. Corrigé en désactivant explicitement ces options dans
`getUserMedia` (`echoCancellation`/`noiseSuppression`/`autoGainControl`
à `false`).

**Testé en conditions réelles** (scénario qui posait justement problème :
« Jarvis » enchaîné immédiatement par la question, sans pause, via
lecture d'un extrait réel + une commande synthétisée à la suite, sans
silence entre les deux) : commande correctement capturée et transcrite
(« Quelle heure est-il ? »), réponse cohérente reçue (« Il est 16h47,
Monsieur. ») — plus de confirmation générique.

### Suite : faux positifs sur des bruits brefs (clics de clavier)

**3. Se déclenche sur un clic de clavier.** Sur PC, une seconde
vérification (Silero VAD, un vrai modèle de détection de parole) confirme
qu'il y a réellement de la voix avant de déclencher
(`agents/desktop/audio/wakeword.py::listen()`) — jamais portée dans le
navigateur. Sans elle, le modèle wake word seul se déclenche parfois sur
un bruit bref, puisqu'il n'a pas été entraîné à rejeter spécifiquement ce
type de bruit (le jeu d'entraînement plafonne volontairement le bruit
synthétique à 35 % des négatifs, voir `wakeword/entrainer.py`).

Corrigé sans porter Silero (autre modèle, hors scope) : exige qu'un son
assez fort dure au moins 200ms d'affilée avant de valider une détection
— un clic est une impulsion de quelques ms, un mot parlé dure des
centaines de ms. Plus grossier qu'un vrai VAD, mais cible exactement ce
cas.

**Bug trouvé en écrivant ce correctif** : le premier seuil choisi
(0.01) était calibré sur une voix de synthèse Piper (forte), pas sur un
vrai micro — un vrai enregistrement de « Jarvis » mesure ~0.0027 de RMS
brut, sous ce seuil. Résultat : plus aucune détection ne passait, y
compris les vraies. Mesuré sur `samples_jarvis/jarvis_01.wav` puis
recalibré à 0.0018 (entre le bruit de fond à 0.0012 et la parole réelle à
~0.0027) — **même seuil réutilisé pour la capture de commande**, qui
avait le même problème latent (testée jusque-là uniquement avec une voix
de synthèse, jamais avec un vrai micro discret).

**Testé en conditions réelles, contre-épreuve incluse** : 20 clics
synthétiques d'affilée (impulsion bruyante ~25ms, volume comparable à de
la parole) → aucun déclenchement. Le vrai extrait « Jarvis » rejoué
immédiatement après → détection toujours correcte (non-régression
vérifiée après le recalibrage du seuil).

### Suite : se redéclenchait tout seul juste après une vraie détection

**4. « Dûment noté » persistant + redéclenchement fantôme.** Après
correction des bugs 1-3, Quentin confirme que la détection capte bien ce
qu'il dit — mais l'affichage « entendu » revient à « rien entendu après
Jarvis » une fraction de seconde après avoir montré la bonne transcription.
Deux bugs de timing distincts, empilés :

- **a) Course entre fin de capture et mise en pause.** `captureCommand()`
  repassait le détecteur en mode scoring dès que la capture se terminait
  — mais la vraie mise en pause (déclenchée après la *transcription*,
  dans `useVoice.js`) n'intervenait que plus tard. Pendant cet
  entre-deux (le temps de l'appel réseau vers Whisper), le détecteur
  rescorait déjà avec l'écho de la commande encore dans sa fenêtre.
  Corrigé : `captureCommand()` met maintenant le détecteur en pause
  **dès la fin de la capture elle-même**, pas après coup — et
  `useVoice.js` doit explicitement appeler `resume()` dans les deux
  culs-de-sac (rien dit, transcription vide) puisque plus rien ne le
  fait automatiquement pour eux.
- **b) Fenêtre glissante jamais vidée à la reprise.** Une fois le bug (a)
  corrigé, un second est apparu : `resume()` (appelé après que Jarvis a
  fini de répondre) ne vidait pas la fenêtre glissante de 1.5s — l'audio
  d'avant la pause (fin du mot d'éveil, voire la commande) y restait, et
  se faisait rescorer instantanément à la reprise, redéclenchant parfois
  une détection fantôme. Corrigé : `resume()` vide maintenant la fenêtre,
  l'historique de bruit et les compteurs avant de réactiver le scoring.

**Testé en conditions réelles** : séquence complète « Jarvis » + question
enchaînée sans pause, réponse correcte reçue, **puis surveillé 15
secondes sans qu'aucun redéclenchement fantôme n'apparaisse** (contre une
réapparition quasi immédiate de « rien entendu » avant ce correctif).

### Suite : réponses génériques (« Dûment noté, Monsieur. ») à de vraies questions

En testant la voix en conditions réelles, Quentin a remarqué que Jarvis
répondait par des accusés de réception vagues (« Dûment noté, Monsieur. »,
« C'est en cours. ») même à des questions directes (« tu m'entends ? »),
au lieu d'y répondre vraiment — visible surtout côté modèle local Ollama
(`qwen3:14b`), moins avec Claude.

**Diagnostic** : `brain/core/prompts.py::SYSTEM_PROMPT` listait « Dûment
noté. » parmi les formulations de confirmation, sans distinguer le cas
« Monsieur donne une instruction/info à retenir » (confirmation
appropriée) du cas « Monsieur pose une question et attend une réponse »
(confirmation = échec). Un modèle plus petit qu'Ollama généralise mal
cette nuance implicite.

**Corrigé** : ajout d'une règle explicite dans `RÈGLES DE COMMUNICATION`
distinguant question et instruction, plus un exemple concret (« tu
m'entends ? » → « Cinq sur cinq, Monsieur. Je vous entends
parfaitement. ») dans `EXEMPLES DE RÉPONSES PARFAITES`. Brain redémarré
pour vider le cache du prompt (`_system_prompt_cache`).

**Testé en conditions réelles**, brain relancé et Ollama chargé (source
confirmée `ollama` sur chaque réponse, pas juste le fallback Claude) :

| Question | Avant | Après |
|---|---|---|
| « Est-ce que tu m'entends bien » | « Dûment noté, Monsieur. » | « Cinq sur cinq, Monsieur. Je vous entends parfaitement. » |
| « Tu es là » | générique | réponse directe |
| « Tu m'entends » | générique | « Cinq sur cinq... » |
| « Quelle heure est-il » | correct | inchangé (pas de régression) |
| « Mémorise que j'aime le café » | « Dûment noté, Monsieur. ... » | inchangé — la confirmation reste utilisée à bon escient pour une vraie instruction |

Cas limite noté sans y toucher : « Ça fonctionne bien » (affirmation sans
point d'interrogation) reçoit encore une réponse de type « C'est en
cours » — ambigu (peut se lire comme une affirmation, pas forcément une
question), pas traité comme une régression.

### Ce qui reste à valider — nécessite ta vraie voix, donc toi

- 🔲 Détection et capture de commande avec ta vraie voix, en conditions
  d'usage réelles (les tests ci-dessus rejouent des enregistrements,
  proche mais pas identique à parler en direct).
- 🔲 Latence perçue en usage réel (le calcul tourne dans le navigateur,
  potentiellement plus lent qu'un PC selon l'appareil — à surveiller
  surtout sur un téléphone plus tard).
- 🔲 Lecture audio automatique de la réponse : les navigateurs bloquent
  parfois `audio.play()` déclenché en dehors d'un clic direct
  (politiques « autoplay »). Le code échoue proprement si bloqué (pas de
  plantage), mais reste silencieux sans te prévenir pourquoi — à
  vérifier en usage réel.
- 🔲 Comportement si tu parles pendant que Jarvis répond (pas de
  barge-in : il faut attendre la fin avant que l'écoute reprenne).

### Mise en place (une fois — deux fichiers ne sont pas versionnés)

`web/public/models/jarvis_wakeword.onnx` (gitignoré comme tous les
`*.onnx`/`*.tflite` du projet, même logique que le modèle wake word du
PC) et `web/public/ort/` (runtime tiers, pas du code projet) doivent
exister avant de lancer le build. S'ils manquent (première installation,
nouveau clone) :

```
pip install tf2onnx onnx
python -m tf2onnx.convert --tflite agents/desktop/wakeword/jarvis_wakeword.tflite --output web/public/models/jarvis_wakeword.onnx --opset 13

cd web && npm install
cp node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.wasm public/ort/
cp node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.mjs public/ort/
```

### Pour tester

```
cd web && npm run build
```
puis va sur `http://localhost:8420` (le brain sert maintenant la Console
directement — plus besoin de `npm run dev` séparé pour cette
fonctionnalité, qui ne marche pas en mode dev Vite, voir bug ci-dessus).

---

## Phase 10 — Pilotage PC depuis le web ▲▲▲ · ✅ fait (Steps 0-3)

Jusqu'ici, la Console web ne fait que de la conversation
(`brain/core/chat.py`, aucun tool-use) : taper « ouvre Chrome » dans le
chat web ne fait rien, alors que le mécanisme de dispatch réseau existe
déjà et marche (Phase 3/4, utilisé aujourd'hui uniquement par les
boutons figés de l'écran Focus — Capturer/Verrouiller). Objectif :
brancher le chat web (et donc l'accès distant, Phase 6) sur le vrai
pilotage PC en langage naturel, en réutilisant l'infra existante
(schéma d'outils, dispatch réseau, historique) plutôt qu'en dupliquant
la boucle Claude qui existe déjà côté desktop
(`agents/desktop/brain/agent.py`).

Découpé en étapes testables une par une (voir le détail du découpage
dans la session qui a mené ce chantier) : Step 0 (verrou d'accès) →
Step 1 (boucle d'outils côté brain) → Step 2 (branchement `/ws/chat`) →
Step 3 (retour visuel web).

### Step 0 — Verrou d'accès sur tout le brain ✅

Décidé avant de brancher quoi que ce soit de sensible : le brain
(Console, chat, dispatch réseau) n'avait **aucune authentification** —
seul le VPN limitait qui pouvait l'atteindre. Une fois le chat capable
de déclencher du pilotage PC en langage libre (pas juste 2 boutons
figés), ce vide devenait plus sensible qu'avant.

- `brain/config.py` — `CONSOLE_PASSWORD` (`.env`, vide = auth
  désactivée, pratique en dev local).
- `brain/server.py` — middleware HTTP `_require_console_auth` :
  `Authorization: Bearer <mdp>` obligatoire sur `/api/*` (sauf
  `/api/health`, laissé ouvert pour les sondes de démarrage) ;
  `/ws/chat` vérifie `?token=` au handshake (un navigateur ne peut pas
  poser de header custom sur une connexion WebSocket), ferme avec le
  code applicatif `4401` si absent/invalide. `/ws/agent` non touché — a
  déjà sa propre auth par token (Phase 4).
- `web/src/lib/consoleAuth.js` (nouveau) — pas de vérification
  proactive au chargement (si `CONSOLE_PASSWORD` est vide côté brain,
  rien ne change pour l'utilisateur) : purement réactif au premier 401
  reçu, quelle que soit la requête. `web/src/components/AuthGate.jsx` —
  écran plein écran, un champ, pas de compte : le mot de passe sert
  lui-même de token, comme le token d'appareil existant. Un mot de passe
  embarqué dans le bundle JS n'aurait rien protégé (visible par
  quiconque ouvre les devtools) — celui-ci n'est jamais présent dans le
  code livré, seulement saisi à l'usage et gardé en `localStorage`.
- Tous les appels réseau du web (`useDevices`, `useFocusDevice`,
  `useChat`, `useVoice`, `Routines`, synthèse/transcription vocale,
  génération de code d'appairage) passent maintenant par `authFetch()` /
  `wsAuthQuery()` au lieu de `fetch`/`WebSocket` bruts.
- **Testé en conditions réelles** : sans token → `401` confirmé sur
  `/api/devices` (curl) ; mauvais token → `401` confirmé ; `/api/health`
  reste `200` sans token ; `/ws/chat` sans token → fermé avec le code
  `4401` (vérifié avec un client WebSocket direct, hors navigateur).
  Côté navigateur : chargement de la Console → écran de connexion
  affiché ; mauvais mot de passe → refusé, écran de connexion
  réaffiché proprement (token effacé automatiquement) ; bon mot de
  passe → Console fonctionnelle normalement (confirmé par Quentin).
  Piège trouvé en testant : `python -m brain.server` ne recharge rien à
  chaud — un simple changement de code ne suffit pas, il faut vraiment
  tuer puis relancer le process (process resté actif depuis avant le
  changement, testé par erreur une première fois sans effet).

### Step 1 — `brain/core/agent.py` (boucle d'outils côté brain) ✅

Miroir async de `agents/desktop/brain/agent.py::ask_with_tools`, mais
qui dispatche les outils sur le réseau
(`brain.devices.registry.dispatch()`) au lieu de les exécuter en local.
Réutilise tel quel le schéma d'outils
(`agents.desktop.tools.registry.to_claude_tools()`, import différé —
voir commentaire dans le code : un brain qui tournerait un jour ailleurs
que sur ce PC ne doit pas planter au démarrage à cause de modules
Windows-only importés juste pour leur schéma), les instructions agent
(`brain.core.prompts.AGENT_INSTRUCTIONS`) et l'historique partagé
(`brain.core.history` — déjà utilisé par le chat web, la nouvelle boucle
en hérite pour de vrai puisqu'elle tourne dans le même process).

### Step 2 — Brancher `/ws/chat` sur le pilotage PC ✅

`agents/desktop/brain/router.py::is_pc_command()` (fonction pure,
réutilisée telle quelle) décide si une question part vers
`agent.ask_with_tools` (nouveau) ou `chat.ask_stream` (existant).
`brain/devices.py::pick_default_device()` (nouveau) : un seul appareil
réel aujourd'hui → ciblage implicite (capacité `"exec"`), pas de
sélecteur ; renvoie `None` si aucun ou plusieurs appareils, auquel cas
la Console reçoit un message explicite plutôt qu'un silence. Statuts
intermédiaires (`chat.status`, ex. « OUTIL : take_screenshot ») envoyés
pendant qu'un outil tourne.

### Step 3 — Retour visuel Console web ✅

`useChat.js` gère `chat.status` (nouvel état `activity`), `Console.jsx`
l'affiche dans la bulle de réponse pendant l'exécution, dans le même
esprit que `VoiceStatusBar` (Phase 9).

### Testé en conditions réelles (Steps 1-3)

Brain relancé (nécessaire : `python -m brain.server` ne recharge rien à
chaud, déjà noté au Step 0), `jarvis.py` connecté (`BRAIN_ENABLED=1`,
visible dans `/api/health`). Depuis la vraie Console web : « prends une
capture d'écran » tapé dans le chat → statut « OUTIL :
take_screenshot » visible pendant l'exécution → réponse finale
cohérente décrivant réellement le contenu de l'écran (VS Code, fichier
`.env` ouvert, Docker actif...), confirmant que l'image est bien
transmise à Claude via le dispatch réseau. Pas d'image affichée dans le
chat lui-même — attendu : seul l'écran Focus (Phase 4) affiche une
capture comme image, le chat reste texte-only par conception.

### Volontairement hors de ce chantier

- **Arrêt à distance** (bouton stop côté web) — nécessite un vrai
  protocole d'interruption réseau, pas juste le `threading.Event` local
  actuel (`state.stop_agent`). Reste ouvert, comme noté depuis la
  Phase 3.
- **Sélection explicite de l'appareil cible** — n'a de sens qu'avec un
  vrai deuxième appareil (mobile/portable), toujours pas le cas.
- **Garde-fou « tainted » sur le dispatch réseau** — `run_powershell`
  garde son blocage/dialogue de confirmation pour toute commande
  détectée destructive quel que soit le canal d'origine (réseau
  compris), donc pas un trou béant ; juste imparfait sur le cas précis
  « commande anodine + contenu piégé lu juste avant » côté réseau. Pas
  bloquant pour ce chantier.

---

## Ce qu'il ne faut PAS faire (pièges, dans la continuité de `ROADMAP.md`)

- Ne pas faire transiter l'audio brut par le brain **pour l'agent
  desktop** — latence et complexité inutiles, son pipeline vocal reste
  local (wake word TFLite, Whisper spéculatif). Exception assumée et
  décidée avec Quentin en Phase 9 : un navigateur ne peut pas faire de
  wake word/STT local aussi facilement, donc la Console web envoie
  l'audio au brain (qui relaie à Speaches, en local ou via Tailscale) —
  seule la voix web fait ce choix, pas le PC.
- Ne pas construire l'agent mobile natif avant que la Phase 6 (accès web
  distant) soit stable — le navigateur couvre déjà 80 % du besoin
  immédiat pour beaucoup moins d'effort.
- Ne pas ajouter de vrai système de comptes/permissions tant que c'est un
  usage strictement personnel — un token par agent suffit.
- Ne pas dupliquer la logique de décision entre `brain/core/` et les
  agents une fois la Phase 3 faite — un agent exécute, il ne décide pas.

---

## Ordre recommandé

Phase 0 → 1 → 2 → 3 → 4 → 5 → 6 → 9 → 10 faites (voix web et pilotage PC
depuis le web compris). Restent 7 et 8 en option, plus tard, pas
urgentes — rien d'autre d'important en attente. Chaque
phase est démontrable seule avant de passer à la suivante — pas besoin
d'attendre la fin du chantier pour avoir quelque chose d'utilisable :
dès la Phase 2, tu peux déjà taper à Jarvis depuis un navigateur
(parler, pas encore — Phase 9).

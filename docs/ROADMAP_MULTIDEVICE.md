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

## Phase 5 — Routines cross-device ▲▲

- Écran **04 Routines** : les routines existent déjà côté agent
  (`services/routines.py`) mais mono-appareil. Étendre le format pour
  qu'une routine puisse cibler plusieurs `device_id` dans une même
  séquence.
- Éditeur de routine dans le web (au moins CRUD basique), pas seulement
  vocal.

## Phase 6 — Accès distant + mobile web ▲▲

- **Tailscale** (ou équivalent WireGuard) sur le PC fixe et le téléphone :
  accès à l'interface web du brain depuis l'extérieur du réseau local,
  sans exposer de port publiquement.
- Écran **05 Mobile** : appliquer les variantes responsive du design (pas
  du simple reflow) à la Console, au Centre d'appareils et au Focus
  appareil.
- À ce stade, le téléphone peut déjà *piloter* Jarvis via le navigateur —
  c'est suffisant pour beaucoup d'usages avant même d'avoir un agent
  natif dessus.

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

---

## Ce qu'il ne faut PAS faire (pièges, dans la continuité de `ROADMAP.md`)

- Ne pas faire transiter l'audio brut (micro) par le brain — latence et
  complexité inutiles, tout le pipeline vocal reste local à l'agent qui
  possède le micro.
- Ne pas construire l'agent mobile natif avant que la Phase 6 (accès web
  distant) soit stable — le navigateur couvre déjà 80 % du besoin
  immédiat pour beaucoup moins d'effort.
- Ne pas ajouter de vrai système de comptes/permissions tant que c'est un
  usage strictement personnel — un token par agent suffit.
- Ne pas dupliquer la logique de décision entre `brain/core/` et les
  agents une fois la Phase 3 faite — un agent exécute, il ne décide pas.

---

## Ordre recommandé

Phase 0 → 1 → 2 → 3 → 4 → 5 → 6 → (7 et 8 en option, plus tard, pas
urgentes). Chaque phase est démontrable seule avant de passer à la
suivante — pas besoin d'attendre la fin du chantier pour avoir quelque
chose d'utilisable : dès la Phase 2, tu peux déjà parler à Jarvis depuis
un navigateur.

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

## Phase 2 — Web UI : Console ▲▲

- Scaffolding front (Vite + framework choisi), extraction des tokens
  couleur/typo du design en variables CSS/thème partagé.
- Écran **01 Console** codé en composants réels, branché sur
  `brain/server.py` en WebSocket : chat texte fonctionnel de bout en bout
  (toi → web → brain → Claude/Ollama → réponse streamée → web).
- Pas encore de voix ni de multi-appareils à ce stade — juste valider que
  la chaîne web ↔ brain marche et que le rendu colle au design.

## Phase 3 — Agent desktop en client réseau ▲▲▲

- `agents/desktop/runtime.py` devient un client WebSocket : il se connecte
  au brain au démarrage, s'enregistre (`device.register`), écoute
  `command.dispatch`, exécute via `agents/desktop/tools/*` (déjà prêt :
  system, screen, input_ctl…), renvoie `command.result`.
- La boucle micro/wake word/TTS reste **locale** à l'agent desktop (pas de
  sens à faire transiter l'audio brut par le brain) ; seul le texte
  transcrit part vers le brain pour décision.
- Le HUD PyQt6 actuel devient optionnel : soit il reste comme interface
  native de secours sur le PC fixe, soit il est retiré au profit du web
  une fois la Console (Phase 2) au niveau. À trancher une fois la Phase 2
  utilisable au quotidien — pas de décision à prendre maintenant.
- Lancement auto au démarrage de Windows (F39 de `ROADMAP.md`, jamais fait)
  — le bon moment de le faire puisqu'on retouche le point d'entrée.

## Phase 4 — Centre d'appareils & Focus appareil ▲▲▲

- Écran **02 Centre d'appareils** : liste des agents connectés (vient du
  registre de la Phase 1), statut temps réel via WebSocket, flux
  d'appairage d'un nouvel appareil (génération + affichage d'un token/QR
  code à saisir côté agent).
- Écran **03 Focus appareil** : vue détaillée — capture d'écran à la
  demande (`agents/desktop/tools/screen.py` existe déjà, il faut
  l'exposer via le protocole), journal d'activité (réutilise
  `services/convlog.py` côté brain), contrôle distant (envoyer une
  commande à un agent précis).
- **Routage contextuel** : quand tu dis « ouvre cette page sur mon PC
  portable », le brain doit déduire `device_id` cible depuis la phrase —
  probablement un outil Claude dédié (`list_devices` + `target_device` en
  paramètre des tools existants) plutôt qu'une nouvelle mécanique de NLU.

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

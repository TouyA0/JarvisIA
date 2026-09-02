# J.A.R.V.I.S. — Audit télé, continuité entre appareils & reste à faire

Complète `ROADMAP.md` (features de l'assistant), `ROADMAP_MULTIDEVICE.md`
(architecture brain + agents) et `ROADMAP_DISPLAY_INTEGRATIONS.md`
(intégrations + cartes). Ce document part de la question « qu'est-ce qui
manque à Jarvis, pour la télé et au-delà ? » et couvre trois choses :

1. l'état **réel** du contrôle télé (arrivé aujourd'hui, non commité),
2. le chantier **continuité entre appareils** (transférer une vidéo,
   caster un écran, envoyer un fichier d'un appareil à l'autre),
3. tout le reste — nouveau, à peaufiner, ou dette encore ouverte.

Légende effort : ▲ = un soir · ▲▲ = un week-end · ▲▲▲ = plusieurs jours

Chaque affirmation ci-dessous a été **vérifiée dans le code**, pas
supposée : les points marqués « mesuré » ont été reproduits en exécutant
le code réel. Rien n'est présenté comme fait s'il ne l'est pas.

---

## 1. La télé aujourd'hui — état réel

`brain/integrations/android_tv.py` (**non commité**, non testé)
+ 9 outils dans `brain/tools.py` (dont `tv_status`, voir T3 résolu ci-dessous). ADB TCP direct via `adb-shell`, clé RSA
persistée, trois couches : touches/deep-links → `ui_dump` + `tap`/`type_text`
→ `screenshot` en dernier recours. C'est une bonne base, plus capable que
l'intégration Home Assistant « Android TV Remote » (qui ne sait pas rendre
l'écran).

**Ce qui marche** : volume ±/mute, 9 touches de navigation, lancement
d'app/deep-link, liste des packages, lecture structurée de l'écran, tap,
saisie de texte, capture d'écran (avec carte `screenshot` dans la Console).

### 1.1 Les cinq trous bloquants

| # | Trou | Détail vérifié | Effort |
|---|---|---|---|
| **T1** | **La télé est inatteignable à la voix** | `router.PC_COMMAND_KEYWORDS` ne contient ni « télé », ni « tv », ni « netflix », ni « youtube », ni « salon ». **Mesuré** sur le vrai `is_pc_command()` : « mets youtube sur la télé » → ❌, « mets netflix » → ❌, « pause sur la télé » → ❌, « coupe la télé » → ❌, « qu'est-ce qui passe sur la télé » → ❌. Seuls « allume la télé » et « baisse le son de la télé » passent — **par accident** (mots-clés domotique/PC). Et même quand ça passe, `runtime.py:102` route vers `agents/desktop/brain/agent.py`, qui n'a **que** les outils PC : aucun `tv_*` n'y est exposé. Conclusion : aujourd'hui, la télé n'est pilotable que depuis le chat de la Console web. | ▲ (mots-clés) / ▲▲ (vrai correctif, voir E9) |
| **T2** | **Aucune configuration depuis la Console** | `ANDROID_TV_HOST` en `.env` uniquement — pas de carte dans **Intégrations** (aucune référence à la télé dans `web/src/components/integrations/`), donc pas de bouton connecter, pas de test de connexion, pas de sonde de santé (`/api/integrations/health` l'ignore). Une télé injoignable ressemblera à un bug. | ▲ |
| ~~T3~~ | ~~Jarvis ne sait pas ce que la télé fait~~ **Résolu** | Nouvel outil `tv_status` (`android_tv.status()` dans `brain/integrations/android_tv.py`) : combine `dumpsys power` (écran allumé/éteint), `dumpsys activity activities` (app au premier plan) et `dumpsys media_session` (titre/artiste/état lecture/position de la session active) — parsing best effort, `None`/message générique plutôt qu'une valeur inventée si le format ne matche pas. | ▲ |
| **T4** | **Ni allumage ni extinction** | `_KEYCODES` n'expose pas `WAKEUP`/`SLEEP`/`POWER`. Sur un stick Android TV, `KEYCODE_WAKEUP` réveille le stick et allume généralement la télé par HDMI-CEC, `KEYCODE_SLEEP` fait l'inverse — deux lignes dans la liste blanche. Sans ça, « allume la télé » ne peut pas marcher, ce qui est la première chose qu'on demande. | ▲ |
| **T5** | **Aucune carte / aucune télécommande visuelle** | Pas de type de carte `tv` dans `web/src/components/cards/renderers.jsx` : seule la capture d'écran s'affiche (via la carte `screenshot` générique). Or une télécommande à boutons sur le téléphone est *plus rapide* que la voix pour naviguer, et la mécanique existe déjà (`/api/tools/execute`, utilisé par les boutons de la carte `music`). | ▲▲ |

### 1.2 Contrôle télé — le reste des manques

| # | Manque | Pourquoi ça compte | Effort |
|---|---|---|---|
| T6 | **Volume absolu** (« le son à 30 % ») | seuls up/down/mute existent ; `media volume --set N --stream 3` le fait, et permet aussi de *lire* le niveau | ▲ |
| T7 | **Touches média complètes** | pas de suivant/précédent/avance rapide/retour/stop, pas de `seek` (« recule de 30 secondes », « saute le générique ») | ▲ |
| T8 | **Sous-titres & piste audio** | « mets les sous-titres », « passe en VO » — pas de chemin générique, à faire app par app via `ui_dump` | ▲▲ |
| T9 | **Source HDMI / CEC** | basculer sur la console, le lecteur Blu-ray, la TNT — hors périmètre ADB, passerait par HA (CEC) ou une télécommande IR | ▲▲ |
| T10 | **Saisie de texte accentuée** | `type_text()` remplace les espaces par `%s` et supprime les guillemets, mais `input text` d'Android gère mal les caractères non-ASCII : « Amélie Poulain » risque de sortir déformé. À tester ; solution propre = passer par le presse-papier de l'appareil ou un IME dédié (ADBKeyboard) | ▲ |
| T11 | **Catalogue de deep-links maigre** | 6 apps dans `_APP_SCHEMES`, dont 4 « meilleure estimation » non testées. Manque surtout un **repli générique** : si le deep-link ne mène nulle part, ouvrir la recherche de l'app et taper le titre (l'agent sait déjà le faire avec `ui_dump`+`tap`, mais rien ne le lui impose) | ▲▲ |
| T12 | **Lancement par package peu fiable** | `am start -a VIEW -d "com.machin"` ne lance rien pour un package ; il faut `monkey -p <pkg> 1` ou résoudre l'activité principale. `list_apps()` renvoie des packages… que `launch_app()` ne sait pas vraiment lancer | ▲ |
| T13 | **Robustesse de la liaison ADB** | le port 5555 se désactive à chaque redémarrage du stick sur beaucoup d'appareils, et l'IP peut changer (DHCP). Aucune détection/message dédié, aucune découverte mDNS, pas de reconnexion planifiée — juste une reconnexion à la volée | ▲▲ |
| T14 | **Zéro test** | `tests/` ne contient rien pour la télé. `_parse_ui_dump()` et `_resolve_app()` sont des fonctions pures, testables en 20 lignes sans matériel | ▲ |
| T15 | **Aucune confirmation, accès quasi-shell** | `_shell()` est générique : la surface est bornée uniquement par les fonctions écrites au-dessus, ce qui est correct — mais rien n'est confirmé (éteindre la télé de quelqu'un qui regarde un film n'est pas anodin), et la doc du module dit elle-même de ne jamais exposer l'hôte hors LAN | ▲ |

### 1.3 🔴 À corriger tout de suite (sécurité)

`data/android_tv_adbkey` (clé privée RSA donnant un accès shell à la télé)
**n'est pas dans `.gitignore`** — vérifié avec `git check-ignore` : le
fichier serait commité au prochain `git add .`. Les autres secrets
(`data/integrations.key`, `data/devices.json`) sont bien ignorés, celui-ci
a été oublié. Deux lignes à ajouter :

```
data/android_tv_adbkey
data/android_tv_adbkey.pub
```

---

## 2. Continuité entre appareils — le chantier que tu décris

C'est le vrai sujet derrière « transférer une vidéo YouTube d'un appareil à
un autre, caster un écran ». Aujourd'hui **rien** de tout ça n'existe : le
brain sait dispatcher une commande vers *un* appareil, jamais faire passer
un contenu de l'un à l'autre.

### 2.1 Handoff de lecture

| # | Feature | Ce qui existe déjà pour la faire | Effort |
|---|---|---|---|
| **C1** | **« Envoie cette vidéo sur la télé »** (PC → télé) | Le plus gros rapport valeur/effort du document. Tout est déjà là : `get_browser_url` (outil PC existant) donne l'URL de l'onglet actif, il suffit d'en extraire l'ID YouTube + l'horodatage (`&t=`) et d'appeler `tv_launch_app("vnd.youtube://ID")`. Un seul outil `send_to_tv` à écrire, qui marche aussi pour Netflix/Prime (URL → deep-link) et pour une URL quelconque | ▲ |
| **C2** | **« Reprends ça sur le PC »** (télé → PC) | l'inverse : `dumpsys media_session` (voir T3) donne titre + position, puis `open_url` sur le PC à la bonne seconde. Dépend de T3 | ▲ |
| **C3** | **Depuis/vers le téléphone** | manque l'agent mobile (Phase 7). Contournement quasi gratuit : la Console est déjà une **PWA installable** — ajouter un `share_target` au manifeste permet de « partager » un lien YouTube depuis n'importe quelle app Android **vers Jarvis**, qui l'envoie ensuite où tu veux. C'est quelques lignes de manifeste + une route | ▲ |
| **C4** | **Reprise Jellyfin cross-appareil** | `jellyfin_continue_watching` existe déjà (lecture seule) mais **ne sait pas lancer** — « reprends mon épisode sur la télé » n'est pas faisable. Deux chemins : deep-link Jellyfin sur le stick, ou l'API Jellyfin `Sessions/{id}/Playing` (contrôle à distance d'une session, explicitement noté « pas fait » dans le README) | ▲▲ |
| **C5** | **Transfert de lecture Spotify** | l'API Spotify a `GET /me/player/devices` + `PUT /me/player` (transfert vers un appareil) — l'intégration actuelle ne les expose pas. « Passe la musique sur la télé / sur l'enceinte du salon » = 1 outil `spotify_transfer` | ▲ |

### 2.2 Caster / voir un écran sur un autre

| # | Feature | Réalité technique | Effort |
|---|---|---|---|
| **C6** | **Voir la télé depuis la Console/le téléphone** | Faisable dès maintenant : le pattern existe déjà pour le PC (`Focus.jsx` fait du polling ~800 ms sur `capture_frame`, cf. V1 dans `ROADMAP_DISPLAY_INTEGRATIONS.md`). Le rejouer avec `android_tv.screenshot()` donne une « vue télé » en direct dans le navigateur. Version fluide : `scrcpy` par-dessus la connexion ADB déjà en place (vraie vidéo, 30 fps) | ▲▲ |
| **C7** | **Caster l'écran du PC sur la télé** | ⚠️ à ne pas sur-promettre : un Chromecast/Google TV **ne fait pas de Miracast**, donc le « Se connecter » de Windows ne marchera pas. Chemins réalistes : (a) Home Assistant `media_player.play_media` vers l'entité Cast (voir C8) ; (b) un serveur HTTP local du brain qui sert un flux, ouvert sur la télé via VLC/Kodi ; (c) le cast d'onglet Chrome natif, non pilotable proprement. Recommandation : passer par (a), et traiter le mirroring plein écran comme du confort, pas comme la fonctionnalité principale | ▲▲▲ |
| **C8** | **Caster via Home Assistant — le raccourci manquant** | `brain/integrations/home_assistant.py::control()` ne gère que `turn_on/off/toggle` et `_call_service()` **n'accepte aucun `service_data`** : impossible d'appeler `media_player.play_media` ou `tts.speak`. En levant cette limite, on gagne d'un coup : caster une URL/vidéo/dashboard sur la télé, envoyer du son sur n'importe quelle enceinte Cast, faire parler Jarvis dans une autre pièce, contrôler la lecture de tous les `media_player` de la maison — sans écrire une seule intégration de plus | ▲▲ |
| **C9** | **Télécommande visuelle sur le téléphone** | cf. T5. Pour naviguer un menu, appuyer sur un bouton bat la voix — et c'est un usage quotidien évident du téléphone déjà connecté à la Console | ▲▲ |

### 2.3 Transfert de fichiers, presse-papier, notifications

| # | Feature | État | Effort |
|---|---|---|---|
| **C10** | **« Envoie ce fichier sur mon téléphone / la télé »** | inexistant — noté « aucune infra de transfert de fichier entre appareils » en Phase 4. Côté télé c'est gratuit (`device.push` d'adb-shell) ; côté général il faut un dépôt côté brain + un lien de téléchargement (la brique existe à moitié : `POST /api/vision/analyze` reçoit déjà des images) | ▲▲ |
| **C11** | **Presse-papier partagé** | `read_clipboard` existe côté PC, mais rien ne l'écrit ni ne le synchronise. « Copie ça sur mon autre PC », « colle-moi le lien du téléphone » — très demandé en usage réel, très peu de code | ▲ |
| **C12** | **Notifications quand la Console est fermée** | aujourd'hui `Hud.jsx:284` utilise l'API `Notification` du navigateur : ça ne marche **que si l'onglet est ouvert**. Sans service worker + Web Push (VAPID, `pywebpush`), un minuteur ou une alerte proactive ne t'atteindra jamais sur le téléphone. C'est le chaînon manquant de tout le travail « pousser la proactivité au web/téléphone » déjà fait côté brain | ▲▲ |
| **C13** | **Continuité de conversation visible** | commencer à la voix sur le PC et continuer sur le téléphone marche déjà (historique partagé depuis la Phase 3) — mais rien ne le *montre* : aucun indicateur « cette réponse vient du salon ». Petit polish, gros effet de cohérence | ▲ |

---

## 3. La télé comme surface de sortie de Jarvis

Aujourd'hui la télé est uniquement un appareil **piloté**. Le plus grand
écran de la maison ne montre jamais rien de Jarvis.

| # | Idée | Détail | Effort |
|---|---|---|---|
| **S1** | **« C'est qui cet acteur ? »** | La feature la plus « Jarvis » du document, et toutes les briques existent déjà : `tv_screenshot` (image) + le chemin vision de `brain/core/agent.py` (`_tool_result_content` sait envoyer une image à Claude) + `web_search`. « Jarvis, c'est quoi ce film ? », « il joue dans quoi d'autre ? », « résume-moi ce que j'ai raté ». Il ne manque que l'enchaînement et une carte de résultat | ▲▲ |
| **S2** | **Afficher les cartes sur la télé** | la Console est déjà une PWA responsive : installée sur le stick (navigateur sideloadé) ou affichée via Cast, elle devient un dashboard salon. Météo, agenda, minuteur, caméra — sur le grand écran | ▲▲ |
| **S3** | **Mode ambiant sur la télé** | extension de F29 / du panorama ambiant du pupitre : quand la télé est en veille, réacteur + heure + météo + prochain rendez-vous | ▲▲ |
| **S4** | **Jarvis parle par la télé** | TTS existant (`/api/speech/synthesize`) + lecture sur la télé (via HA `tts.speak`/Cast, cf. C8, ou lecture d'un fichier poussé en ADB). Débloque le briefing matinal dans le salon et les annonces multi-pièces | ▲▲ |
| **S5** | **Incrustation d'alerte** | « quelqu'un sonne », « ton minuteur est fini » par-dessus le film. Techniquement une notification Android sur le stick ou un overlay d'une petite app compagnon — le seul point de cette section qui demande une app installée | ▲▲▲ |
| **S6** | **Contexte « on regarde un film »** | un vrai mode (au sens `data/modes.json`) : la télé joue → Jarvis baisse sa voix, ne fait pas de briefing, pousse ses alertes en silencieux, propose « je mets en pause ? » avant de parler | ▲ |

---

## 4. Au-delà de la télé — ce qui manque à l'écosystème

### 4.1 Le trou structurel n°1 : la voix ne voit pas les intégrations

C'est, de loin, le manque le plus important du projet — plus important que
n'importe quelle feature ci-dessus, parce qu'il rend invisible **tout** le
travail d'intégration déjà fait.

Chemin réel, vérifié dans le code :

```
voix → runtime.py:102 → router.is_pc_command(question) ?
   ├─ OUI → agents/desktop/brain/agent.py  ← outils PC UNIQUEMENT
   │         (aucun tv_*, drive_*, gmail_*, ha_*, spotify_*…)
   └─ NON → remote_chat → brain /ws/chat → chat.ask_stream
             └─ _ask_local_with_tools : 13 outils seulement
                (SAFE_LOCAL_TOOL_NAMES, brain/core/agent.py:41)
```

Conséquence concrète : **à la voix**, Jarvis ne peut ni piloter la télé, ni
contrôler la domotique, ni écrire dans Drive, ni envoyer un mail, ni
contrôler Spotify, ni calculer un itinéraire. Pire, ces demandes tombent
souvent dans `is_pc_command` (« allume », « lumière », « musique »…) et
partent vers un agent qui n'a **que** PowerShell pour répondre — il fera
n'importe quoi plutôt que rien. Le README le reconnaît pour Google
(« ça ne fonctionne pas encore depuis la boucle vocale locale ») ; en
réalité c'est vrai pour toutes les intégrations sauf les 13 outils du
sous-ensemble local.

| # | Correctif | Détail | Effort |
|---|---|---|---|
| **E9** | **Unifier les deux chemins d'outils** | faire passer la voix par `brain/core/agent.py` (qui a déjà PC + brain fusionnés) au lieu de `agents/desktop/brain/agent.py`, avec repli local si le brain est éteint. C'est l'inverse du raccourci pris en Phase 3 (« routage réseau inutile tant qu'il n'y a qu'un appareil ») — sauf qu'aujourd'hui il ne s'agit plus de router vers un appareil, mais d'accéder aux outils du brain | ▲▲ |
| **E10** | **Sortir de la liste de mots-clés** | `PC_COMMAND_KEYWORDS` est une liste de ~150 mots qui grossit à chaque intégration et rate systématiquement les formulations nouvelles (mesuré sur la télé, §T1). Un routage par petit modèle local (une seule question : « faut-il des outils ? ») serait plus fiable et sans maintenance à chaque feature | ▲▲ |

### 4.2 Appareils qui manquent

| # | Appareil | État | Effort |
|---|---|---|---|
| E1 | **Agent mobile** | Phase 7, jamais commencée. Sans lui : pas de notification hors navigateur (C12), pas de localisation, pas de « lis-moi mes messages », pas de capture d'écran du téléphone | ▲▲▲ |
| E2 | **Deuxième PC / portable** | tout le routage contextuel (« ouvre ça sur mon portable ») est bâti mais jamais exercé : `pick_default_device()` renvoie `None` s'il y a plusieurs appareils, et la Console dit simplement qu'elle ne sait pas choisir. Un deuxième agent réel révélerait plusieurs trous d'un coup | ▲▲ |
| E3 | **Enceintes / multi-room** | dépend de C8 (HA `media_player`). Aucune notion de « pièce » aujourd'hui : ni les appareils, ni les routines, ni les cartes ne savent où elles sont | ▲▲ |
| E4 | **Montre** | Phase 8, exploratoire, à garder pour plus tard | ▲▲▲ |
| E5 | **Caméras / sonnette** | rien, alors que HA les expose déjà si tu en as ; combiné à S5 (incrustation télé) c'est un usage quotidien évident | ▲▲ |

### 4.3 Intelligence contextuelle

| # | Feature | Détail | Effort |
|---|---|---|---|
| E6 | **Présence / « qui est là »** | `ha_network_status` lit déjà les `device_tracker` — mais rien n'en fait un contexte : « je viens de rentrer » pourrait allumer la lumière, lancer la musique, annoncer les mails du jour | ▲▲ |
| E7 | **Déclencheurs de routines** | aujourd'hui : manuel + horaire (commit `25dff40`). Manquent les déclencheurs **événementiels** : arrivée/départ, télé allumée, PC verrouillé, mail d'un expéditeur précis, batterie faible, début d'un rendez-vous | ▲▲ |
| E8 | **Mémoire RAG (F8)** | toujours ouverte, toujours la feature la plus « intelligence » du projet : « de quoi on a parlé hier ? », « qu'est-ce que j'avais noté sur ce projet ? » sur mémoire + notes + logs + cartes (tous déjà sur disque en JSONL) | ▲▲▲ |
| E11 | **Recherche unifiée** | « cherche X » interroge Drive + Gmail + notes + historique en parallèle → une carte par source. Toutes les briques existent séparément | ▲▲ |
| E12 | **Notifications Windows (F16)** | seul item non fait de sa section dans `ROADMAP.md` — lire les toasts Discord/Teams et les annoncer | ▲▲▲ |
| E13 | **Le « ça » multi-tours** | « mets ça sur la télé » suppose de savoir ce qu'est « ça » (la vidéo dont on vient de parler, le fichier de la dernière carte). Rien ne relie les cartes affichées au contexte de la conversation suivante | ▲▲ |

---

## 5. Peaufinage — dette et petits gains encore ouverts

Repris de `ROADMAP.md` (uniquement ce qui reste **réellement** à faire) et
complété par ce que j'ai vu dans le code aujourd'hui.

### Vraiment prioritaire

- **P1 · Voix Jarvis custom (F1)** ▲ — `voice/jarvis-high.onnx` dort
  toujours dans le repo, jamais branché. Toujours ★1 de `ROADMAP.md`, et
  le plus gros gain d'immersion pour le moins d'effort du projet.
- **P2 · Wake word ONNX + bruits (F4)** ▲▲ — fiabilité de la porte
  d'entrée, −500 Mo, −3 s au démarrage. Le portage ONNX est **déjà fait
  pour le web** (Phase 9) : le PC est le seul à traîner TensorFlow.
- **P3 · Démarrage avec Windows (F39)** ▲ — « 2 minutes » depuis des mois ;
  tant que ce n'est pas fait, Jarvis n'est pas vraiment « toujours là ».

### Confort quotidien

- **P4 · Mode dictée (F20)** ▲▲ · **P5 · Gestion de fenêtres (F13)** ▲▲ ·
  **P6 · UI Automation par nom de bouton (F12)** ▲▲▲ — le pilotage PC reste
  aveugle aux noms d'éléments, donc fragile.
- **P7 · Multi-écrans (D6)** ▲▲ — capture/OCR/Vision ciblée ignorent
  toujours les écrans secondaires.
- **P8 · Journal quotidien auto (F10)** ▲ · **P9 · Résumé de tour agent
  (F11)** ▲ — l'agent reste amnésique entre deux tâches PC.
- **P10 · Vision locale via Ollama (F9)** ▲▲ — chaque capture coûte
  aujourd'hui des tokens Claude.
- **P11 · Graphe de coût (F34)** ▲ · **P12 · « Jarvis, rapport » (F38)** ▲.
- **P13 · Réglages in-app (F26)** — **partiellement fait** : l'écran
  Réglages ne couvre que météo + proactivité. Restent voix, modèles,
  seuils de barge-in, hôte de la télé (T2), hotkeys.
- **P14 · Mode ambiant (F29)** — pupitre + panorama faits, **plein écran
  sans navigation** toujours à faire (et cf. S3 pour la télé).

### Robustesse

- **P15 · Allowlist sécurité (F36/D8)** ▲▲ — la détection destructive
  reste une blocklist regex contournable.
- **P16 · Timeout PowerShell paramétrable (D7)** ▲ — 8 s en dur, une
  recherche disque légitime échoue en silence.
- **P17 · Reconnaissance du locuteur (F24)** ▲▲ — d'autant plus pertinent
  maintenant qu'il y a une télé : elle parle, et Jarvis l'écoute.
- **P18 · AEC / barge-in sur haut-parleurs (F22)** ▲▲▲ · **P19 · STT
  streaming (F23)** ▲▲▲ — les deux vraies limites de latence/fiabilité audio.
- **P20 · Couverture de tests** ▲▲ — 4 fichiers de tests pour l'ensemble du
  projet ; `brain/tools.py` (1 186 lignes) et `brain/server.py` (1 362
  lignes) mériteraient d'être découpés comme `Integrations.jsx` l'a été.
- **P21 · Enregistrement d'écran (V2)** ▲▲ · **P22 · Webcam ponctuelle
  (V3)** ▲ — les deux derniers points non commencés de la section vidéo.

---

## 6. Priorisation — ce que je ferais, dans l'ordre

| # | Quoi | Pourquoi en premier | Effort |
|---|---|---|---|
| 1 | **Gitignore de la clé ADB** (§1.3) | secret qui part au prochain commit | 1 min |
| 2 | **T3 + T4 + T6/T7** (état, allumage, volume/média) | sans état ni allumage, la télé n'est pas un appareil, c'est une télécommande borgne | ▲ |
| 3 | **E9 — la voix accède aux outils du brain** | débloque d'un coup télé + domotique + Drive + mails + Spotify à la voix. Le plus gros gain du document | ▲▲ |
| 4 | **C1 — « envoie cette vidéo sur la télé »** | exactement ta demande, et presque gratuit (`get_browser_url` existe) | ▲ |
| 5 | **T2 + T5 — carte Intégrations + télécommande** | rend la télé configurable et utilisable sans parler | ▲▲ |
| 6 | **C8 — HA `play_media`/`tts`** | débloque cast, multi-room et voix dans les autres pièces sans nouvelle intégration | ▲▲ |
| 7 | **S1 — « c'est qui cet acteur ? »** | la feature la plus spectaculaire, briques déjà présentes | ▲▲ |
| 8 | **C12 — Web Push** | sans ça, toute la proactivité poussée au téléphone reste invisible | ▲▲ |
| 9 | **P1 — la voix custom** | ★1 depuis le début, un soir de travail | ▲ |
| 10 | **C6 — voir la télé en direct dans la Console** | pattern déjà écrit pour le PC, à rejouer | ▲▲ |

---

## 7. Pièges à éviter (spécifiques à ce chantier)

- **Promettre le mirroring PC → télé** (C7) : un Chromecast/Google TV ne
  fait pas de Miracast. Annoncer « caster mon écran » et livrer un lecteur
  d'URL décevrait — cadrer l'attente dès le départ.
- **Empiler des mots-clés dans `PC_COMMAND_KEYWORDS`** pour rattraper T1 :
  ça marchera pour « télé » et ratera la formulation suivante. Le vrai
  correctif est E9/E10.
- **Faire de l'ADB la solution à tout** : c'est un accès shell complet sur
  un appareil grand public, à garder strictement sur le LAN, jamais
  redirigé, et à borner outil par outil comme c'est fait aujourd'hui.
- **Boucler sur `tv_screenshot`** : chaque capture est une image envoyée à
  Claude (coût + latence). `ui_dump` doit rester le chemin par défaut, la
  capture le dernier recours — c'est déjà écrit dans les descriptions
  d'outils, à surveiller en usage réel.
- **Construire l'agent mobile avant d'avoir épuisé la PWA** : share target
  (C3), Web Push (C12) et télécommande (C9) couvrent une grande partie du
  besoin téléphone pour une fraction de l'effort d'une app native.

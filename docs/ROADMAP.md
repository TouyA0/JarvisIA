# J.A.R.V.I.S. — Audit & Roadmap (MARK 2.2, août 2026)

Audit honnête de l'existant + toutes les pistes d'évolution, classées par
thème avec impact et effort estimés. Remplace `futur_feats.txt` (dont la
majorité est faite : streaming ✓, météo ✓, notes ✓, logs ✓, tray ✓,
redémarrage auto ✓, vision ✓, volume % ✓, icône ✓, routines ✓).

Légende effort : ▲ = un soir · ▲▲ = un week-end · ▲▲▲ = plusieurs jours/semaines

---

## 1. Limites actuelles (dette technique)

| # | Limite | Détail | Piste |
|---|--------|--------|-------|
| D1 | **Voix robotique** | Piper siwis générique — alors que `voice/jarvis-high.onnx` (voix custom) dort inutilisée | Voir F1 |
| D2 | **TensorFlow pour le wake word** | ~500 Mo installés, +2-3 s au démarrage, pour un simple interpréteur TFLite | Export ONNX + onnxruntime (F4) |
| D3 | **Wake word fragile** | Entraîné sans vrais bruits de fond ; seuil 0.90 + 2 hits consécutifs = compromis ratés/faux positifs | Réentraîner avec bruits (F4) |
| D4 | **Pas d'annulation d'écho** | Sur haut-parleurs, le barge-in repose sur des seuils durs ; Jarvis peut s'auto-interrompre ou rater une interruption | AEC WebRTC/speexdsp (F22) |
| D5 | **STT non streaming** | Whisper ne démarre qu'au premier silence (spéculatif) ; ~1-2 s incompressibles sur CPU | RealtimeSTT / distil-whisper (F23) |
| D6 | **Écran principal seulement** | screenshot, Vision ciblée et OCR ignorent les écrans secondaires | Multi-écrans (F3) |
| D7 | **Timeout PowerShell 8 s** | Une commande légitime longue (recherche disque large) échoue en silence | Timeout paramétrable par l'agent |
| D8 | **Sécurité = blocklist** | La détection destructive par regex est contournable (encodage, alias) ; pas de sandbox | Allowlist par catégories + confirmation par défaut hors allowlist |
| D9 | **Mémoire plate** | 80 faits max, pas de recherche sémantique, pas d'oubli intelligent | RAG local (F8) |
| D10 | **Tout le pilotage PC coûte des tokens Claude** | Même « ouvre Chrome » la première fois | Tool-use local Ollama (F7) |
| D11 | **Zéro test automatisé** | Les modules purs (router, timers, textutil, memory) sont pourtant très testables | pytest (F30) |
| D12 | **Historique agent amnésique** | Les tours d'outils ne sont pas conservés entre les questions (seul le texte l'est) | Résumé de tour dans l'historique |
| D13 | **Config éclatée** | .env + 5 JSON à éditer à la main | Panneau réglages in-app (F26) |
| D14 | **N'importe qui peut lui parler** | Pas de reconnaissance du locuteur | Empreinte vocale (F24) |

---

## 2. Roadmap — TOP 5 recommandé

| Prio | Feature | Pourquoi | Effort |
|------|---------|----------|--------|
| ★1 | **F1 — Voix Jarvis custom** | Le fichier est déjà dans `voice/` ; impact immersion maximal | ▲ |
| ~~★2~~ | ~~F5 — Proactivité (alertes système + briefing)~~ ✓ *(fait)* | — | — |
| ~~★3~~ | ~~F2 — Recherche web + résumé vocal~~ ✓ *(fait)* | — | — |
| ★4 | **F7 — Tool-use local Ollama** | Coût API → quasi zéro, latence réduite, vie privée | ▲▲ |
| ★5 | **F4 — Wake word ONNX + bruits** | Fiabilité de la porte d'entrée + boot 3 s plus rapide, -500 Mo | ▲▲ |

---

## 3. Toutes les features, par thème

### 🔊 Voix & audio

- **F1 · Brancher `voice/jarvis-high.onnx`** ▲ — deux options :
  a) l'enregistrer dans le cache Speaches ; b) plus simple et plus robuste :
  `pip install piper-tts` et synthétiser en local direct (supprime la
  dépendance Docker pour le TTS, garde Speaches pour le STT seul).
- **F21 · Bip d'écoute au wake word** ▲ — feedback sonore immédiat (~100 ms)
  avant même la transcription ; on sait qu'il a entendu.
- **F22 · Annulation d'écho (AEC)** ▲▲▲ — webrtc-audio-processing ou
  speexdsp : barge-in fiable sur haut-parleurs, suppression des profils durs.
- **F23 · STT streaming** ▲▲▲ — RealtimeSTT ou faster-whisper en flux :
  transcription pendant que tu parles, latence perçue nulle réelle.
- **F24 · Reconnaissance du locuteur** ▲▲ — resemblyzer : empreinte vocale de
  Quentin, Jarvis ignore les autres voix (et la télé).
- **F25 · Clonage de voix VF** ▲▲▲ — Coqui XTTS v2 clone une voix avec 6 s
  d'audio (la VF de Jarvis…). Attention : lourd sur CPU, ROCm/Windows délicat.

### 🧠 Cerveau & IA

- **F2 · Recherche web réelle** ✓ *(fait)* — outils `web_search` (Brave
  Search, gratuite 2000 req/mois) + `fetch_page` (extraction d'article via
  `trafilatura`) : l'agent cherche, lit, et résume à voix haute. Carte
  `web_results` (liens cliquables). Règle anti-hallucination ajoutée au
  prompt (7. HONNÊTETÉ RADICALE) pour forcer l'appel plutôt qu'une réponse
  de mémoire sur les questions datées/actu.
- **F5 · Proactivité** ✓ *(fait)* — `agents/desktop/services/proactive.py` :
  thread de règles qui surveille et PARLE seul, disque/RAM/batterie
  (seuils + cooldown par règle), suggestion de coucher à heure configurée.
  Rappels/minuteurs déjà faits séparément (`services/timers.py`).
- **F6 · Briefing matinal réel** ✓ *(fait, sans les titres d'actu)* — même
  module : heure + météo ✓ + agenda (F14 ✓) + mails non lus (F15 ✓), une
  fois par jour à heure configurée. Titres d'actu : F2 (recherche web) est
  fait, mais pas encore branché dans le briefing lui-même.
- **F7 · Tool-use local** ▲▲ *(phases 1 et 2 faites — rapport complet et
  résultats mesurés : voir artefact "Tool-Use Local" partagé en session,
  et `scripts/test_ollama_tools.py`)* — qwen3:14b tente en premier les
  outils sans confirmation (météo, diagnostics, agenda, mails en lecture,
  recherche web, Tisséo, Jellyfin), escalade silencieuse vers Claude en cas
  d'échec ou hors périmètre (`brain/core/agent.py::_ask_local_with_tools`,
  miroir `agents/desktop/brain/agent.py`). Effet de bord positif côté
  voix : ces sujets n'étaient auparavant PAS pilotables à la voix du tout
  (l'agent Claude vocal n'avait que les outils PC, jamais les outils brain)
  — ils le deviennent via ce chemin local. Phase 3 (extension du
  sous-ensemble, mesuré via la phase 4) restante.
- **F8 · Mémoire RAG** ▲▲▲ — embeddings locaux (`nomic-embed-text` via
  Ollama) sur mémoire + notes + logs de conversation → « qu'est-ce que
  j'avais noté sur le projet ICT ? », « de quoi on a parlé hier ? ».
- **F9 · Vision locale** ▲▲ — `qwen2.5vl` ou `llama3.2-vision` via Ollama
  pour la Vision ciblée et les screenshots : gratuit, privé, Claude en repli.
- **F10 · Journal quotidien auto** ▲ — le soir (ou routine soir), Claude
  résume la journée (notes + conversations) dans `data/journal/AAAA-MM-JJ.md`.
- **F11 · Résumé de tour agent** ▲ — après chaque tâche PC, stocker une ligne
  « ce qui a été fait » dans l'historique → continuité entre questions (D12).

### 📅 Intégrations quotidien

- **F14 · Agenda** ✓ *(fait)* — Google Calendar, voir `docs/ROADMAP_DISPLAY_INTEGRATIONS.md` (I1).
- **F15 · Emails** ✓ *(fait)* — Gmail + Zoho Mail, voir même doc (I4/I5).
- **F16 · Notifications Windows** ▲▲▲ — UserNotificationListener (WinRT) lit
  les toasts (Discord, Teams…) → Jarvis annonce les messages importants.
  Toujours pas fait — seul item de cette section encore ouvert.
- **F17 · Spotify** ✓ *(fait, code prêt)* — API Spotify, voir même doc (I6) ;
  bloqué en pratique par le compte Free de Monsieur (Premium requis côté
  Spotify), pas par le code.
- **F18 · Transports Toulouse** ✓ *(fait)* — Tisséo, voir même doc (I11).
- **F19 · Domotique** ✓ *(fait)* — Home Assistant REST, voir `docs/ROADMAP_DISPLAY_INTEGRATIONS.md` (I13).

### 🖥️ Contrôle PC avancé

- **F12 · UI Automation** ▲▲▲ — pywinauto/UIA : cliquer un bouton PAR SON NOM
  au lieu de coordonnées d'image. Fiabilité du pilotage x10.
- **F13 · Gestion de fenêtres** ▲▲ — « Chrome à gauche, Discord à droite »,
  « minimise tout sauf VS Code » (win32gui).
- **F20 · Mode dictée** ▲▲ — « Jarvis, dictée » : tout ce qui est dit est
  tapé dans l'app active jusqu'à « fin de dictée ».
- **F27 · Rangement auto** ▲▲ — « range mes téléchargements » : règles par
  extension/date, avec dry-run vocal avant exécution.
- **F28 · Historique d'écran (opt-in)** ▲▲▲ — OCR périodique local façon
  Screenpipe : « qu'est-ce que je lisais il y a une heure ? ». Gros sujet
  vie privée → chiffrer + rétention courte.

### 🎨 Interface

- **F26 · Panneau réglages in-app** ▲▲ — voix, seuils barge-in, modèles,
  ville météo, hotkeys… éditables depuis le HUD (fini le .env à la main).
- **F29 · Mode ambiant** ▲▲ — plein écran réacteur + horloge + météo quand
  AFK (écran de veille Stark).
- **F31 · Historique navigable** ▲ — scroll complet + recherche dans le
  panneau transmissions (les JSONL sont déjà là).
- **F32 · Sous-titres** ▲ — bandeau texte pendant que Jarvis parle (déjà
  affiché dans la bulle ; version overlay grand format).
- **F33 · Thèmes** ▲ — Mark 42 (rouge/or), War Machine (gris), Vision
  (pourpre) : la palette est déjà centralisée dans `theme.py`.
- **F34 · Graphe de coût** ▲ — coût API par jour dans le panneau diagnostics
  (l'historique mensuel existe dans `usage.json`).

### 🛡️ Robustesse & qualité

- **F30 · Tests pytest** ▲▲ — router, timers, textutil, memory, commands sont
  purs et déjà couverts par des asserts manuels → les transformer en suite.
- **F35 · pyproject.toml + venv** ▲ — installation reproductible,
  `pip install -e .`, versions verrouillées.
- **F36 · Allowlist sécurité** ▲▲ — inverser la logique : catégories de
  commandes connues sûres passent, tout le reste confirme (D8).
- **F37 · Nettoyage des commandes apprises** ▲ — vérifier périodiquement que
  les AppID mémorisés existent encore (app désinstallée → purge).
- **F38 · « Statut système » vocal** ▲ — « Jarvis, rapport » → résumé santé :
  liaisons, erreurs récentes, coût, uptime.
- **F39 · Démarrage avec Windows** ▲ — raccourci vers `launch_jarvis.vbs`
  dans `shell:startup` (à documenter, 2 minutes).

---

## 4. Ce qu'il ne faut PAS faire (pièges)

- **Tout basculer sur le cloud** — la valeur de Jarvis est d'être local
  d'abord (privé, gratuit, rapide) avec Claude en renfort ciblé.
- **Écoute d'écran permanente sans opt-in explicite** (F28) — dangereux.
- **Envoi d'emails/messages automatique** — lecture oui, envoi toujours
  confirmé.
- **Grossir le prompt système** à chaque feature — chaque ajout coûte des
  tokens à CHAQUE tour ; préférer des outils que Claude appelle au besoin.
- **Réécrire l'UI en web/Electron** — PyQt6 tient très bien la charge et
  reste léger ; un navigateur embarqué = +300 Mo de RAM pour rien.

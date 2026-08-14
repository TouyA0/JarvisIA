"""Orchestrateur principal : boot, boucle d'écoute, routage des questions.

Séquence d'une question vocale :
  wake word → transcription → routage (mode / routine / note / mémoire /
  commande apprise / réponse locale / LLM) → parole en streaming avec
  possibilité d'interruption vocale à tout moment.

La boucle est protégée par un garde-crash : une exception imprévue est
journalisée dans data/logs/crash.log et la boucle redémarre (max 5 fois
par tranche de 10 minutes).
"""
from __future__ import annotations

import os
import threading
import time
import traceback

from agents.desktop import APP_VERSION, config, state
from agents.desktop.textutil import normalize_text
from agents.desktop.ui.hud import overlay, TOKEN_PAUSE, TOKEN_RESUME, TOKEN_SNIP

_tray = None


# ══ Parole ════════════════════════════════════════════════════════════════════
def say(text: str) -> None:
    """Parle avec écoute d'interruption pendant toute la durée."""
    from agents.desktop.audio import tts

    if not text:
        return
    print(f"Jarvis : {text}")
    overlay.set_response(text)
    overlay.set_state("speaking")
    if overlay.is_muted():
        overlay.set_state("idle")
        return
    interrupt_thread = threading.Thread(target=tts.listen_for_interrupt, daemon=True)
    interrupt_thread.start()
    tts.speak(text, on_level=overlay.set_level)
    state.stop_speaking.set()   # signal au listener pour qu'il s'arrête proprement
    interrupt_thread.join()
    overlay.set_state("idle")


def _speak_stream(phrase_iter, on_phrase=None) -> str | None:
    """Consomme un générateur de phrases en les prononçant au fil de l'eau,
    sous couverture d'un unique listener d'interruption.

    on_phrase(phrase) optionnel : appelé avant chaque phrase (ex : mettre à
    jour le badge de source une fois le cerveau réel connu).
    Retourne le texte complet prononcé, ou None si interrompu avant un mot.
    """
    from agents.desktop.audio import tts

    state.stop_agent.clear()
    state.stop_speaking.clear()
    interrupt_thread = threading.Thread(target=tts.listen_for_interrupt, daemon=True)
    interrupt_thread.start()

    muted = overlay.is_muted()
    spoken_parts: list[str] = []

    try:
        for phrase in phrase_iter:
            if state.stop_agent.is_set() or state.stop_speaking.is_set():
                break
            phrase = (phrase or "").strip()
            if not phrase:
                continue
            if on_phrase:
                on_phrase(phrase)
            spoken_parts.append(phrase)
            print(f"Jarvis : {phrase}")
            overlay.set_response(" ".join(spoken_parts))
            overlay.set_state("speaking")
            if not muted:
                tts.speak(phrase, on_level=overlay.set_level)
    finally:
        state.stop_speaking.set()
        interrupt_thread.join()
        overlay.set_state("idle")

    if state.stop_agent.is_set() and not spoken_parts:
        return None
    return " ".join(spoken_parts) if spoken_parts else None


def _answer_with_brain(question: str) -> str | None:
    """Interroge le cerveau adapté et fait parler Jarvis.

    Conversation → streaming phrase par phrase (Ollama d'abord, Claude en
    repli). Pilotage PC → agent Claude bloquant (les tool_use imbriqués
    rendent le streaming incrémental peu fiable), réponse prononcée d'un bloc.

    Retourne le texte prononcé, ou None si le tour a été interrompu avant
    toute parole.
    """
    from agents.desktop.brain import agent, chat, router

    if router.is_pc_command(question):
        from agents.desktop.audio import tts

        state.stop_agent.clear()
        state.stop_speaking.clear()
        interrupt_thread = threading.Thread(target=tts.listen_for_interrupt, daemon=True)
        interrupt_thread.start()
        overlay.set_source("ai")
        result = None
        try:
            result = agent.ask_with_tools(question)
            overlay.set_model_label(config.CLAUDE_MODEL)
            if result and not (state.stop_agent.is_set() or state.stop_speaking.is_set()):
                print(f"Jarvis : {result}")
                overlay.set_response(result)
                overlay.set_state("speaking")
                if not overlay.is_muted():
                    tts.speak(result, on_level=overlay.set_level)
        finally:
            state.stop_speaking.set()
            interrupt_thread.join()
            overlay.set_state("idle")
        if state.stop_agent.is_set() and not result:
            return None
        return result

    brain_state: dict = {}

    def _sync_source(_phrase):
        overlay.set_source("ollama" if brain_state.get("source") == "ollama" else "ai")

    result = _speak_stream(chat.ask_stream(question, brain_state), on_phrase=_sync_source)
    overlay.set_model_label(
        config.OLLAMA_MODEL if brain_state.get("source") == "ollama"
        else config.CLAUDE_MODEL)
    return result


# ══ Aide vocale ═══════════════════════════════════════════════════════════════
_HELP_TRIGGERS = ["que peux-tu faire", "que sais-tu faire", "qu'est-ce que tu sais faire",
                  "tes capacites", "tes fonctionnalites", "liste tes fonctions",
                  "aide jarvis", "comment tu fonctionnes"]

_HELP_CARD = (
    "CAPACITÉS PRINCIPALES\n"
    "« Jarvis » — mot d'éveil, puis parlez naturellement\n"
    "⌖ Vision ciblée : « regarde ça » · Ctrl+Alt+V · bouton ⌖\n"
    "PC : « ouvre… », « cherche… », « qu'est-ce que tu vois ? »\n"
    "◷ « minuteur 5 minutes » · « rappelle-moi de… dans 20 min »\n"
    "✎ « prends note que… » — carnet daté\n"
    "★ « mémorise que… » — mémoire long terme\n"
    "◈ « mode travail / détente / repas » · « routine matin »\n"
    "☾ heure · date · météo · volume à X % · « combien tu m'as coûté »\n"
    "Ctrl+Alt+J — afficher le HUD · parlez pendant que je parle pour m'interrompre")


def _match_help(question: str) -> bool:
    q = normalize_text(question)
    if q in ("aide", "help", "jarvis aide"):
        return True
    return any(t in q for t in _HELP_TRIGGERS)


# ══ Vision ciblée ═════════════════════════════════════════════════════════════
# Déclencheurs vocaux : la phrase DOIT commencer par l'un d'eux (préfixe).
_SNIP_TRIGGERS = ["regarde ca", "regarde cette zone", "regarde cette erreur",
                  "analyse ca", "analyse cette zone", "analyse cette erreur",
                  "capture une zone", "capture la zone", "vision ciblee"]


def match_snip_trigger(question: str) -> str | None:
    """Retourne la question résiduelle (peut être vide) si c'est une demande
    de Vision ciblée, None sinon."""
    import re
    q = normalize_text(question)
    q = re.sub(rf"^{config.WAKE_WORD}\b[\s,;:!?-]*", "", q).strip()
    for trigger in _SNIP_TRIGGERS:
        if q == trigger or q.startswith(trigger + " ") or q.startswith(trigger + ","):
            # Extraction sur la version normalisée (les index de `question`
            # brute ne correspondent pas à cause des accents retirés).
            return q[len(trigger):].strip(" ,;:!?-")
    return None


def _vision_flow(pre_question: str | None) -> None:
    """Sélection d'une zone d'écran puis question à Claude vision dessus."""
    from agents.desktop.audio import capture, stt
    from agents.desktop.brain import vision
    from agents.desktop.ui import snip

    state.is_busy = True
    try:
        _vision_flow_inner(pre_question, capture, stt, vision, snip)
    finally:
        state.is_busy = False


def _vision_flow_inner(pre_question, capture, stt, vision, snip) -> None:
    overlay.set_state("processing")
    overlay.set_activity("VISION CIBLÉE — SÉLECTION…")
    holder = snip.open_selector()
    shot = snip.wait_selector(holder, timeout=90)
    overlay.set_activity("")

    if not shot:
        overlay.set_state("idle")
        print("[Vision] sélection annulée.")
        return

    overlay.show(0)
    overlay.add_system_message(f"⌖ Zone capturée — {shot['w']}×{shot['h']} px")

    question = (pre_question or "").strip()
    if not question:
        say("Je vous écoute, Monsieur.")
        overlay.set_state("listening")
        capture.main.flush()
        typed = overlay.get_text_input_nowait()
        if typed and not typed.startswith("__"):
            question = typed
        elif not overlay.is_muted():
            question = stt.transcribe(capture.main, on_level=overlay.set_level)
        else:
            # Mode texte : attendre une saisie jusqu'à 30 s
            deadline = time.time() + 30
            while time.time() < deadline:
                typed = overlay.get_text_input_nowait()
                if typed and not typed.startswith("__"):
                    question = typed
                    break
                time.sleep(0.1)

    display = (question or "Décris cette zone.") + "  ⌖"
    overlay.set_transcript(display)
    overlay.set_state("processing")
    overlay.set_source("ai")
    overlay.set_activity("ANALYSE DE LA ZONE…")

    t0 = time.time()
    result = _speak_stream(
        vision.ask_stream(question, shot["image_b64"], shot["media_type"]))
    overlay.set_activity("")
    overlay.set_model_label(config.CLAUDE_MODEL)
    if result is None:
        print("[Vision] interrompu.")
        overlay.finish_response()
    else:
        overlay.finish_response(f"{time.time() - t0:.1f}s")
    capture.main.flush()


# ══ Routage d'une question ════════════════════════════════════════════════════
def _handle_question(question: str) -> None:
    """Toute la cascade de routage pour une question déjà transcrite."""
    print(f"Quentin : {question}")
    overlay.set_transcript(question)
    overlay.set_state("processing")
    t0 = time.time()
    state.is_busy = True
    try:
        _route_question(question, t0)
    finally:
        state.is_busy = False


def _route_question(question: str, t0: float) -> None:
    from agents.desktop.audio import capture
    from agents.desktop.brain import commands, memory, modes, router
    from agents.desktop.services import notes, routines, timers

    # 1. Changement de mode (« passe en mode travail »)
    mode_match = modes.match_trigger(question)
    if mode_match:
        activated = modes.set_mode(mode_match["id"])
        if activated:
            overlay.set_mode(activated["name"].replace("Mode ", ""))
            response = f"{activated['name']} activé, Monsieur. {activated['description']}"
        else:
            response = "Mode non reconnu, Monsieur."
        overlay.set_source("direct")
        capture.main.flush()
        say(response)
        capture.main.flush()
        return

    # 2. Routine (« routine matin », « bonjour jarvis »)
    routine = routines.match_trigger(question)
    if routine:
        overlay.set_source("direct")
        capture.main.flush()
        state.stop_agent.clear()
        routines.run(routine, say)
        active = modes.get_active_mode_data()
        overlay.set_mode(active["name"].replace("Mode ", "") if active else "Normal")
        capture.main.flush()
        return

    # 3. Minuteurs et rappels (« minuteur 5 minutes », « rappelle-moi dans… »)
    timer_response = timers.handle(question)
    if timer_response:
        overlay.set_source("direct")
        capture.main.flush()
        say(timer_response)
        capture.main.flush()
        return

    # 3bis. Aide (« que sais-tu faire ? ») — fiche mémo + résumé vocal
    if _match_help(question):
        overlay.set_source("direct")
        overlay.add_system_message(_HELP_CARD)
        capture.main.flush()
        say("Je pilote votre PC, j'analyse votre écran, je gère minuteurs, "
            "notes et mémoire, Monsieur. La liste complète s'affiche à l'écran.")
        capture.main.flush()
        return

    # 4. Vision ciblée (« regarde ça », « analyse cette zone »)
    snip_rest = match_snip_trigger(question)
    if snip_rest is not None:
        _vision_flow(snip_rest)
        return

    # 5. Fait personnel (« mémorise que… »)
    if memory.is_memory_fact(question):
        fact = memory.save_explicit_fact(question)
        confirm = (f"Mémorisé, Monsieur : « {fact[:60]} »." if fact
                   else "Je n'ai pas pu identifier le fait à mémoriser, Monsieur.")
        overlay.set_source("direct")
        capture.main.flush()
        say(confirm)
        capture.main.flush()
        return

    # 6. Prise de note (« prends note que… »)
    if notes.is_note_command(question):
        noted = notes.take_note(question)
        confirm = (f"Noté, Monsieur : « {noted[:60]} »." if noted
                   else "Je n'ai pas saisi le contenu de la note, Monsieur.")
        overlay.set_source("direct")
        capture.main.flush()
        say(confirm)
        capture.main.flush()
        return

    # 7. Commande apprise → exécution instantanée sans LLM
    matched_cmd = commands.match(question)
    if matched_cmd:
        print(f"Commande '{matched_cmd['id']}' en {time.time() - t0:.3f}s")
        response = commands.execute_entry(matched_cmd)
        overlay.set_source("cache")
        capture.main.flush()
        say(response)
        capture.main.flush()
        return

    # 8. Réponse locale instantanée (heure, date, IP, volume %, météo, coût)
    direct = router.handle_direct(question)
    if direct:
        print(f"Réponse locale en {time.time() - t0:.1f}s")
        overlay.set_source("direct")
        capture.main.flush()
        say(direct)
        capture.main.flush()
        return

    # 9. LLM (chat en streaming, ou agent à outils)
    result = _answer_with_brain(question)
    turn_s = time.time() - t0
    if result is None:
        print("(Agent interrompu)")
        overlay.finish_response()
    else:
        print(f"Réponse en {turn_s:.1f}s")
        overlay.finish_response(f"{turn_s:.1f}s")
    state.set_metric("turn_ms", turn_s * 1000)
    capture.main.flush()


# ══ Boucle principale ═════════════════════════════════════════════════════════
def _set_waiting(waiting: bool) -> None:
    state.is_waiting = waiting
    if _tray:
        _tray.set_status("paused" if state.is_paused else ("waiting" if waiting else "active"))


def _enter_pause() -> None:
    state.is_paused = True
    overlay.set_paused(True)
    _set_waiting(True)
    say("Mise en veille, Monsieur.")


def _exit_pause() -> None:
    state.is_paused = False
    overlay.set_paused(False)
    _set_waiting(True)
    say("De retour, Monsieur.")


def _main_loop() -> None:
    from agents.desktop.audio import capture, stt, wakeword
    from agents.desktop.brain import memory, router

    question_count = 0

    while True:
        # ── Mode pause : seul « reprends » ou le bouton HUD réveille ─────────
        if state.is_paused:
            _set_waiting(True)
            inline = wakeword.listen(
                capture.main,
                poll_text=overlay.get_text_input_nowait,
                is_muted=overlay.is_muted,
                on_level=overlay.set_level,
            )
            if inline == TOKEN_RESUME:
                _exit_pause()
                continue
            if inline == TOKEN_PAUSE:
                continue  # déjà en pause
            if inline == TOKEN_SNIP:
                # Vision ciblée autorisée même en pause (action explicite)
                _vision_flow(None)
                continue
            question = inline or stt.transcribe(capture.main, on_level=overlay.set_level)
            if question and question not in (TOKEN_PAUSE, TOKEN_RESUME):
                if router.is_pause_command(question) == "resume":
                    _exit_pause()
            continue

        # ── Attente du wake word ─────────────────────────────────────────────
        _set_waiting(True)
        inline = wakeword.listen(
            capture.main,
            poll_text=overlay.get_text_input_nowait,
            is_muted=overlay.is_muted,
            on_level=overlay.set_level,
        )

        if inline == TOKEN_PAUSE:
            _enter_pause()
            continue
        if inline == TOKEN_RESUME:
            continue
        if inline == TOKEN_SNIP:
            _vision_flow(None)
            continue

        state.stop_speaking.clear()
        _set_waiting(False)
        overlay.set_state("listening")
        timeout_start = time.time()

        # ── Fenêtre de conversation (pas besoin de redire « Jarvis ») ────────
        while True:
            if state.is_paused:
                break

            typed = overlay.get_text_input_nowait()
            if typed == TOKEN_PAUSE:
                state.stop_speaking.set()
                _enter_pause()
                break
            if typed == TOKEN_RESUME:
                typed = None
            if typed == TOKEN_SNIP:
                _vision_flow(None)
                overlay.set_state("listening")
                timeout_start = time.time()
                continue

            if typed or inline:
                question = typed or inline
            elif overlay.is_muted():
                # Mode texte : le micro n'est PAS lu, seule la saisie compte
                time.sleep(0.05)
                question = ""
            else:
                question = stt.transcribe(capture.main, on_level=overlay.set_level)
            inline = ""

            if question and len(question) > 2:
                cmd = router.is_pause_command(question)
                if cmd == "pause":
                    overlay.set_transcript(question)
                    _enter_pause()
                    break

                _handle_question(question)

                question_count += 1
                if question_count % config.MEMORY_UPDATE_EVERY == 0:
                    print("Mise à jour de la mémoire en arrière-plan...")
                    threading.Thread(target=memory.update_memory, daemon=True).start()

                overlay.set_state("listening")
                timeout_start = time.time()
            else:
                if time.time() - timeout_start > config.CONVERSATION_TIMEOUT:
                    print("(Retour en veille)")
                    overlay.set_state("idle")
                    break


# ══ Boot ══════════════════════════════════════════════════════════════════════
def _greeting() -> str:
    h = time.localtime().tm_hour
    if 5 <= h < 18:
        salut = "Bonjour"
    else:
        salut = "Bonsoir"
    return f"{salut}, Monsieur. Systèmes opérationnels."


def _boot() -> None:
    """Séquence de mise sous tension — chaque étape s'affiche dans le journal."""
    from agents.desktop.audio import capture, vad, wakeword
    from agents.desktop.brain import modes, usage
    from agents.desktop.services import bootsound, diagnostics, hotkey, timers, weather

    overlay.show(0)
    overlay.set_state("processing")
    overlay.add_system_message(f"J.A.R.V.I.S. MARK {APP_VERSION} — mise sous tension…")

    # Modèles et flux audio
    vad.init()
    overlay.add_system_message("Détection de parole — Silero VAD chargé")
    wakeword.load_model()
    overlay.add_system_message("Mot d'éveil « Jarvis » — modèle local armé")
    capture.init_all()
    overlay.add_system_message("Flux micro ouverts")

    # Services d'arrière-plan
    diagnostics.start(overlay.update_diagnostics)
    weather.start_refresher(overlay.set_weather)
    timers.start(say, overlay.set_timer_chip)
    if config.GLOBAL_HOTKEY:
        hotkey.start([
            (hotkey.MOD_CONTROL | hotkey.MOD_ALT, "J", overlay.focus_input),
            (hotkey.MOD_CONTROL | hotkey.MOD_ALT, "V",
             lambda: overlay.push_input(TOKEN_SNIP)),
        ])
    overlay.add_system_message("Services en ligne — météo · diagnostics · minuteurs")

    # État initial du HUD
    active = modes.get_active_mode_data()
    if active:
        overlay.set_mode(active["name"].replace("Mode ", ""))
    s = usage.summary()
    overlay.set_cost(s["last_cost_usd"], s["month_cost_usd"], s["month_calls"])
    overlay.set_model_label(config.OLLAMA_MODEL)
    overlay.add_system_message(
        "Ctrl+Alt+J — HUD · Ctrl+Alt+V — Vision ciblée · « aide » — capacités")
    overlay.add_system_message("Tous les systèmes sont nominaux.")

    # Mise sous tension
    if config.BOOT_SOUND:
        bootsound.play(blocking=True)
    say(_greeting())


def _worker() -> None:
    """Thread principal de travail : boot + boucle, protégés par un garde-crash."""
    try:
        _boot()
    except Exception:
        _log_crash("BOOT")
        overlay.set_state("error")
        overlay.add_system_message("Échec d'initialisation — voir data/logs/crash.log")
        return

    restarts: list[float] = []
    while True:
        try:
            _main_loop()
            return
        except Exception:
            _log_crash("LOOP")
            overlay.set_state("error")
            restarts = [t for t in restarts if time.time() - t < 600]
            restarts.append(time.time())
            if len(restarts) > 5:
                print("Trop de crashs successifs — arrêt.")
                overlay.add_system_message("Trop de crashs — arrêt du noyau.")
                return
            try:
                say("Une erreur interne est survenue, Monsieur. Redémarrage du noyau.")
            except Exception:
                pass
            time.sleep(2)


def _log_crash(where: str) -> None:
    tb = traceback.format_exc()
    print(f"[CRASH {where}]\n{tb}")
    try:
        with open(config.LOGS_DIR / "crash.log", "a", encoding="utf-8") as f:
            f.write(f"\n=== {time.strftime('%Y-%m-%d %H:%M:%S')} [{where}] ===\n{tb}")
    except Exception:
        pass


# ══ Démarrage ═════════════════════════════════════════════════════════════════
def _toggle_pause_from_ui() -> None:
    """Depuis le tray : poste le token approprié, traité par la boucle."""
    overlay.push_input(TOKEN_RESUME if state.is_paused else TOKEN_PAUSE)


def _quit() -> None:
    if _tray:
        _tray.hide()
    os._exit(0)


def start() -> None:
    """Point d'entrée : construit l'UI sur le thread principal (exigence Qt),
    lance le travail sur un thread dédié, puis exécute la boucle Qt."""
    global _tray

    config.ensure_dirs()

    # Identité Windows explicite : sans ça, la barre des tâches groupe Jarvis
    # sous « Python » avec l'icône python.exe au lieu de l'arc reactor.
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TouyA0.Jarvis")
    except Exception:
        pass

    from agents.desktop.brain import agent, usage
    from agents.desktop.ui import dialogs, snip
    from agents.desktop.ui.tray import Tray

    overlay.start()
    dialogs.init()
    snip.init()
    _tray = Tray(
        on_show=lambda: overlay.show(overlay.HIDE_AFTER_TRAY),
        on_toggle_pause=_toggle_pause_from_ui,
        on_quit=_quit,
    )

    # Câblage des callbacks vers le HUD
    usage.on_update = overlay.set_cost
    agent.on_activity = overlay.set_activity
    overlay.on_quit = _quit

    def _mode_change_from_hud(mode_id: str) -> None:
        from agents.desktop.brain import modes
        activated = modes.set_mode(mode_id)
        if activated:
            overlay.set_mode(activated["name"].replace("Mode ", ""))
            say(f"{activated['name']} activé, Monsieur.")
    overlay.on_mode_change = _mode_change_from_hud

    threading.Thread(target=_worker, daemon=True).start()
    overlay.exec()   # boucle Qt — bloque jusqu'à fermeture

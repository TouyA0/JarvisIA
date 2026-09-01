"""Minuteurs et rappels vocaux.

« Jarvis, minuteur 5 minutes » · « rappelle-moi d'appeler maman dans 20 minutes »
« combien de temps reste-t-il ? » · « annule le minuteur »

Le prochain échéancier s'affiche en compte à rebours dans le header du HUD.
À l'échéance : carillon + annonce vocale (en attendant poliment que Jarvis
ait fini de parler si un tour est en cours).
"""
from __future__ import annotations

import re
import threading
import time
from typing import Callable, Optional

from agents.desktop import state
from common.durations import format_duration, parse_duration
from common.textutil import normalize_text


# ── Service ───────────────────────────────────────────────────────────────────
_timers: list[dict] = []
_lock = threading.Lock()
_say: Optional[Callable[[str], None]] = None
_chip: Optional[Callable[[str], None]] = None


def _chime() -> None:
    """Double ping cristallin — distinct du son de démarrage."""
    try:
        import numpy as np
        import sounddevice as sd
        sr = 22050
        seg = []
        for freq in (1568.0, 2093.0):
            t = np.linspace(0, 0.22, int(sr * 0.22), endpoint=False)
            seg.append(np.sin(2 * np.pi * freq * t) * np.exp(-t * 11))
            seg.append(np.zeros(int(sr * 0.06)))
        audio = (np.concatenate(seg) * 0.35 * 32767).astype(np.int16)
        sd.play(audio, samplerate=sr)
        sd.wait()
    except Exception:
        pass


def _wait_for_quiet(max_wait: float = 90) -> None:
    """Attend que Jarvis ait fini de parler / d'agir avant d'annoncer."""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        if not state.is_speaking and not state.is_busy:
            return
        time.sleep(0.5)


def _loop() -> None:
    while True:
        time.sleep(0.5)
        due = []
        with _lock:
            now = time.time()
            for t in _timers[:]:
                if t["end"] <= now:
                    due.append(t)
                    _timers.remove(t)
            nxt = min(_timers, key=lambda t: t["end"]) if _timers else None

        if _chip:
            if nxt:
                rem = max(0, int(nxt["end"] - time.time()))
                h, r = divmod(rem, 3600)
                m, s = divmod(r, 60)
                txt = f"◷ {h}:{m:02d}:{s:02d}" if h else f"◷ {m:02d}:{s:02d}"
                _chip(txt)
            else:
                _chip("")

        for t in due:
            _wait_for_quiet()
            _chime()
            if _say:
                if t["kind"] == "reminder" and t["label"]:
                    _say(f"Monsieur, vous m'aviez demandé de vous rappeler : {t['label']}.")
                else:
                    _say(f"Monsieur, votre minuteur de {format_duration(t['duration'])} est écoulé.")


def start(say: Callable[[str], None], chip: Callable[[str], None]) -> None:
    global _say, _chip
    _say = say
    _chip = chip
    threading.Thread(target=_loop, daemon=True).start()


def _add(seconds: int, kind: str, label: str = "") -> None:
    with _lock:
        _timers.append({
            "end": time.time() + seconds,
            "duration": seconds,
            "kind": kind,
            "label": label,
        })


def _cancel_all() -> int:
    with _lock:
        n = len(_timers)
        _timers.clear()
    if _chip:
        _chip("")
    return n


def _next_remaining() -> tuple[int, dict] | None:
    with _lock:
        if not _timers:
            return None
        nxt = min(_timers, key=lambda t: t["end"])
        return max(0, int(nxt["end"] - time.time())), nxt


# ── Routage vocal ─────────────────────────────────────────────────────────────
_TIMER_WORDS = ("minuteur", "minuterie", "timer", "compte a rebours")
_REMIND_RE = re.compile(
    r"rappelle[- ]?(?:moi|toi)\s*(?:de |d')?(.*?)(?:\s+dans\s+(.+))?$")


def handle(question: str) -> str | None:
    """Retourne la réponse à prononcer si la phrase concerne les minuteurs,
    None sinon (la cascade de routage continue)."""
    q = normalize_text(question)
    has_timer_word = any(w in q for w in _TIMER_WORDS)
    has_remind = "rappelle" in q and ("moi" in q or "toi" in q)

    if not has_timer_word and not has_remind:
        return None

    # Annulation
    if has_timer_word and any(w in q for w in ("annule", "supprime", "arrete", "stoppe", "enleve")):
        n = _cancel_all()
        if n == 0:
            return "Aucun minuteur n'était actif, Monsieur."
        return ("Minuteur annulé, Monsieur." if n == 1
                else f"Les {n} minuteurs sont annulés, Monsieur.")

    # Temps restant
    if has_timer_word and ("reste" in q or "restant" in q):
        nxt = _next_remaining()
        if not nxt:
            return "Aucun minuteur actif, Monsieur."
        rem, t = nxt
        return f"Il reste {format_duration(rem)}, Monsieur."

    # Rappel avec message
    if has_remind:
        m = _REMIND_RE.search(q)
        seconds = parse_duration(q)
        if not seconds:
            return "Précisez la durée du rappel, Monsieur — par exemple : dans dix minutes."
        label = ""
        if m and m.group(1):
            label = m.group(1).strip()
            # Retirer une durée qui aurait été happée dans le libellé
            label = re.sub(r"dans\s+.*$", "", label).strip(" ,.")
        _add(seconds, "reminder", label)
        return f"Rappel programmé dans {format_duration(seconds)}, Monsieur."

    # Minuteur simple
    seconds = parse_duration(q)
    if not seconds:
        return "Précisez la durée, Monsieur — par exemple : minuteur cinq minutes."
    _add(seconds, "timer", "")
    return f"Minuteur de {format_duration(seconds)} lancé, Monsieur."

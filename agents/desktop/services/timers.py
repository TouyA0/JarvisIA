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
from agents.desktop.textutil import normalize_text

# ── Parsing des durées en français ────────────────────────────────────────────
_WORD_NUMBERS = {
    "un": 1, "une": 1, "deux": 2, "trois": 3, "quatre": 4, "cinq": 5,
    "six": 6, "sept": 7, "huit": 8, "neuf": 9, "dix": 10, "onze": 11,
    "douze": 12, "treize": 13, "quatorze": 14, "quinze": 15, "seize": 16,
    "vingt": 20, "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60,
}
_UNIT_SECONDS = {"h": 3600, "min": 60, "s": 1}

_DUR_RE = re.compile(
    r"(\d+|" + "|".join(_WORD_NUMBERS) + r")\s*"
    r"(heures?|heure|h\b|minutes?|min\b|mn\b|secondes?|sec\b|s\b)",
)
_HM_RE = re.compile(r"(\d+)\s*h\s*(\d+)")   # « 1h30 »


def parse_duration(text: str) -> int | None:
    """Retourne la durée totale en secondes, ou None si rien de reconnaissable."""
    q = normalize_text(text)

    if re.search(r"demi[- ]heure", q):
        return 1800
    if re.search(r"quart\s+d\W?\s*heure|quart\s+heure", q):
        return 900

    # « 1 heure 30 » = 1 h 30 min ; « 2 minutes 30 » = 2 min 30 s.
    # Le nombre orphelin hérite de l'unité inférieure, sauf s'il a déjà la sienne.
    q = re.sub(r"(heures?)\s+(\d{1,2})\b(?!\s*(?:h\b|min|mn|sec|s\b|heure))",
               r"\1 \2 minutes", q)
    q = re.sub(r"(minutes?|min\b|mn\b)\s+(\d{1,2})\b(?!\s*(?:h\b|min|mn|sec|s\b|heure))",
               r"\1 \2 secondes", q)

    total = 0
    m = _HM_RE.search(q)
    if m:
        total += int(m.group(1)) * 3600 + int(m.group(2)) * 60
        q = q[:m.start()] + q[m.end():]

    last_unit = None
    for m in _DUR_RE.finditer(q):
        raw_n, raw_u = m.group(1), m.group(2)
        n = int(raw_n) if raw_n.isdigit() else _WORD_NUMBERS[raw_n]
        if raw_u.startswith("h"):
            unit = "h"
        elif raw_u.startswith(("min", "mn")):
            unit = "min"
        else:
            unit = "s"
        total += n * _UNIT_SECONDS[unit]
        last_unit = unit

    # « une heure et demie », « deux minutes et demie »
    if ("et demi" in q) and last_unit in ("h", "min"):
        total += _UNIT_SECONDS[last_unit] // 2

    return total if total > 0 else None


def format_duration(seconds: int) -> str:
    """Durée orale : « 1 heure 30 », « 5 minutes », « 45 secondes »."""
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f"{h} heure{'s' if h > 1 else ''}")
        if m:
            parts.append(str(m))
    elif m:
        parts.append(f"{m} minute{'s' if m > 1 else ''}")
        if s and not h:
            parts.append(str(s))
    else:
        parts.append(f"{s} seconde{'s' if s > 1 else ''}")
    return " ".join(parts)


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

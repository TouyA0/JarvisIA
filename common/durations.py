"""Analyse de durées en français : « 5 minutes », « 1h30 », « une demi-heure ».

Partagé entre agents/desktop/services/timers.py (minuteurs vocaux, locaux à
la voix) et brain/timers.py (minuteurs brain, visibles web/téléphone) —
c'était dupliqué dans le premier avant que le second n'existe (C1).
"""
from __future__ import annotations

import re

from common.textutil import normalize_text

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

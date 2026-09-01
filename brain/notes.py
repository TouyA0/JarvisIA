"""Notes — carnet texte horodaté (C2).

Écrit jusqu'ici uniquement par agents/desktop/services/notes.py
(« prends note que… »), dans data/notes/notes-AAAA-MM-JJ.md — jamais
relisibles depuis le web/téléphone : pas de vue, pas de recherche, aucune
route côté brain. Ce module lit/écrit les MÊMES fichiers Markdown, donc
sans duplication d'état ni synchronisation à prévoir : une note prise à la
voix sur le PC fixe apparaît ici telle quelle, et réciproquement — voir
agents/desktop/services/notes.py, qui délègue maintenant l'écriture ici.
"""
from __future__ import annotations

import re
import time

from brain import config
from common.textutil import normalize_text_aligned

_LINE_RE = re.compile(r"^-\s+\*\*(\d{2}:\d{2})\*\*\s+—\s+(.*)$")

_TRIGGERS = ["prends note", "prend note", "prends en note", "prend en note",
             "nouvelle note", "ajoute une note", "note dans mes notes"]


def is_note_command(question: str) -> bool:
    q = normalize_text_aligned(question)
    return any(t in q for t in _TRIGGERS)


def extract_content(question: str) -> str | None:
    """Le texte de la note une fois le déclencheur retiré (« prends note
    que je dois… » → « je dois… »), ou None si la phrase n'en est pas une."""
    q = normalize_text_aligned(question)
    for trigger in _TRIGGERS:
        if trigger not in q:
            continue
        idx = q.index(trigger) + len(trigger)
        content = question[idx:].strip()
        for lead in ("que ", "qu'", "de ", ": ", ", "):
            if normalize_text_aligned(content).startswith(lead):
                content = content[len(lead):].strip()
                break
        return content.strip().rstrip(".") or None
    return None


def _files():
    config.ensure_dirs()
    return sorted(config.NOTES_DIR.glob("notes-*.md"), reverse=True)


def list_notes(limit: int = 200) -> list[dict]:
    """Les plus récentes d'abord, tous jours confondus."""
    out: list[dict] = []
    for path in _files():
        date = path.stem.removeprefix("notes-")
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        day_entries = [
            {"date": date, "time": m.group(1), "text": m.group(2)}
            for line in lines
            if (m := _LINE_RE.match(line))
        ]
        out.extend(reversed(day_entries))
        if len(out) >= limit:
            break
    return out[:limit]


def add(text: str) -> dict:
    text = text.strip().rstrip(".")
    if not text:
        raise ValueError("note vide")
    config.ensure_dirs()
    date = time.strftime("%Y-%m-%d")
    hm = time.strftime("%H:%M")
    day_file = config.NOTES_DIR / f"notes-{date}.md"
    is_new = not day_file.exists()
    with open(day_file, "a", encoding="utf-8") as f:
        if is_new:
            f.write(f"# Notes du {time.strftime('%d/%m/%Y')}\n\n")
        f.write(f"- **{hm}** — {text}\n")
    return {"date": date, "time": hm, "text": text}

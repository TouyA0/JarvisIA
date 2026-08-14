"""Prise de notes vocale : « prends note que… » → fichier Markdown horodaté.

Distinct de la mémoire (« mémorise que… » = fait durable sur Monsieur) :
ici c'est un carnet de notes datées, consultable dans data/notes/.
"""
from __future__ import annotations

import time

from agents.desktop import config
from agents.desktop.textutil import normalize_text_aligned

_NOTE_TRIGGERS = ["prends note", "prend note", "prends en note", "prend en note",
                  "nouvelle note", "ajoute une note", "note dans mes notes"]


def is_note_command(question: str) -> bool:
    q = normalize_text_aligned(question)
    return any(t in q for t in _NOTE_TRIGGERS)


def take_note(question: str) -> str | None:
    """Extrait le contenu après le déclencheur et l'ajoute au carnet du jour.

    Retourne la note enregistrée, ou None si le contenu est vide.
    """
    q = normalize_text_aligned(question)
    for trigger in _NOTE_TRIGGERS:
        if trigger not in q:
            continue
        idx = q.index(trigger) + len(trigger)
        content = question[idx:].strip()
        # Retirer les liaisons de début : « que », « de », « : »
        for lead in ("que ", "qu'", "de ", ": ", ", "):
            if normalize_text_aligned(content).startswith(lead):
                content = content[len(lead):].strip()
                break
        content = content.strip().rstrip(".")
        if not content:
            return None

        day_file = config.NOTES_DIR / f"notes-{time.strftime('%Y-%m-%d')}.md"
        is_new = not day_file.exists()
        with open(day_file, "a", encoding="utf-8") as f:
            if is_new:
                f.write(f"# Notes du {time.strftime('%d/%m/%Y')}\n\n")
            f.write(f"- **{time.strftime('%H:%M')}** — {content}\n")
        print(f"[Note] {content}")
        return content
    return None

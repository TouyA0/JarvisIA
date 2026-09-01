"""Prise de notes vocale : « prends note que… » → fichier Markdown horodaté.

Distinct de la mémoire (« mémorise que… » = fait durable sur Monsieur) :
ici c'est un carnet de notes datées, consultable dans data/notes/.

Détection et écriture déléguées à brain/notes.py (C2) — même carnet, pour
que le web/téléphone les voie sans rien synchroniser.
"""
from __future__ import annotations

from brain import notes as brain_notes

is_note_command = brain_notes.is_note_command


def take_note(question: str) -> str | None:
    """Extrait le contenu après le déclencheur et l'ajoute au carnet du jour.

    Retourne la note enregistrée, ou None si le contenu est vide.
    """
    content = brain_notes.extract_content(question)
    if not content:
        return None
    brain_notes.add(content)
    print(f"[Note] {content}")
    return content

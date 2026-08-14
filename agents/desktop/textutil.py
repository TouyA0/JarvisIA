"""Utilitaires texte partagés (normalisation, découpe en phrases)."""
from __future__ import annotations

import re
import unicodedata


def normalize_text_aligned(text: str) -> str:
    """Comme normalize_text mais sans strip : les index restent alignés sur
    l'original. Nécessaire dès qu'on cherche une position dans la version
    normalisée pour ensuite découper la chaîne d'origine.
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text.lower()


def normalize_text(text: str) -> str:
    """Normalise un texte pour les comparaisons robustes sans accents."""
    return normalize_text_aligned(text).strip()


# Découpe sur '.', '!', '?', ':' suivis d'espace — suffisant pour du français
# parlé sans dépendance NLP. Les points de suspension "..." restent groupés car
# le lookbehind ne matche qu'après le dernier '.' d'une séquence suivie d'espace.
_SENTENCE_END_RE = re.compile(r"(?<=[.!?:])\s+")


def split_ready_phrases(buffer: str) -> tuple[list[str], str]:
    """Sépare un buffer en (phrases complètes, reste en attente).

    Le dernier fragment n'est jamais renvoyé comme complet : il peut encore
    s'allonger (un nombre suivi d'un point décimal, un point de suspension
    en cours de génération token par token, etc.).
    """
    parts = _SENTENCE_END_RE.split(buffer)
    if len(parts) <= 1:
        return [], buffer
    return [p for p in parts[:-1] if p.strip()], parts[-1]

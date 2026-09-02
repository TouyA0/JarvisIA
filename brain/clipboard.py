"""Presse-papier partagé (C11) — une seule valeur, visible depuis n'importe
quel appareil : « copie ça sur mon autre PC », « colle-moi le lien du
téléphone ».

Persisté en JSON (même mécanique que preferences.py) pour survivre à un
redémarrage du brain — pas une historique, juste la dernière valeur
partagée, comme un presse-papier physique.
"""
from __future__ import annotations

import json
import time

from brain import config

_FILE = config.DATA_DIR / "clipboard.json"


def get() -> dict | None:
    if not _FILE.exists():
        return None
    with open(_FILE, encoding="utf-8") as f:
        return json.load(f)


def set(text: str, source: str = "") -> dict:
    text = text.strip()
    if not text:
        raise ValueError("presse-papier vide")
    config.ensure_dirs()
    entry = {"text": text[:5000], "source": source, "updated_at": time.time()}
    with open(_FILE, "w", encoding="utf-8") as f:
        json.dump(entry, f, ensure_ascii=False, indent=2)
    return entry

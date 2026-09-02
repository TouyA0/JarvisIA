"""Dépôt de fichiers + lien de téléchargement (C10, moitié « générale »).

« Envoie ce fichier sur mon téléphone » n'a pas d'agent mobile à qui
pousser quoi que ce soit (Phase 7 pas faite) ni de notifications push
(C12 pas fait) — le contournement volontaire, déjà décrit dans
docs/ROADMAP_TV_ET_CONTINUITE.md (C10), est un dépôt côté brain + un lien
de téléchargement que Monsieur ouvre lui-même depuis l'appareil visé.
Comme les cartes (brain/cards.py) diffusent déjà en direct vers toutes les
Consoles ouvertes, si celle du téléphone est déjà ouverte le lien y
apparaît sans rien faire de plus.

Fichiers stockés sous data/uploads/<id>/<nom original> — un id opaque
(uuid4, 32 caractères hex) sert de jeton d'accès : pas d'authentification
supplémentaire sur GET /api/files/{id}/{filename} (le lien EST le secret,
comme n'importe quel lien de partage), nécessaire de toute façon puisqu'un
clic depuis un navigateur ne peut pas poser l'en-tête Bearer du reste de
l'API (voir server.py::_require_console_auth, même raisonnement que les
callbacks OAuth). Pas d'expiration pour l'instant — usage personnel,
ménage manuel si `data/uploads/` grossit trop.
"""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from brain import config

UPLOAD_DIR = config.DATA_DIR / "uploads"

# Généreux pour des photos/documents/vidéos courtes sans ouvrir la porte à
# un remplissage de disque incontrôlé — même logique que vision.py::MAX_BYTES,
# juste une limite plus large puisque ce n'est pas envoyé à l'API Claude.
MAX_BYTES = 200 * 1024 * 1024


def _new_dir() -> tuple[str, Path]:
    file_id = uuid.uuid4().hex
    dest_dir = UPLOAD_DIR / file_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    return file_id, dest_dir


def store_path(local_path: str) -> dict:
    """Copie un fichier déjà présent sur la machine du brain (aujourd'hui le
    même PC fixe que l'agent desktop, voir ROADMAP_MULTIDEVICE.md) dans le
    dépôt. Lève FileNotFoundError/ValueError plutôt que de renvoyer un dict
    d'erreur — c'est brain/tools.py qui traduit pour Monsieur, comme pour
    vision.analyze()."""
    src = Path((local_path or "").strip().strip('"').strip("'")).expanduser()
    if not src.is_file():
        raise FileNotFoundError(f"fichier introuvable : {local_path}")
    size = src.stat().st_size
    if size > MAX_BYTES:
        raise ValueError(f"fichier trop volumineux ({size // (1024 * 1024)} Mo, max {MAX_BYTES // (1024 * 1024)} Mo)")
    file_id, dest_dir = _new_dir()
    dest = dest_dir / src.name
    shutil.copy2(src, dest)
    return {"id": file_id, "filename": src.name, "size": size}


def resolve(file_id: str) -> Path | None:
    """Retrouve le fichier déposé sous cet id. Refuse tout id qui ne serait
    pas un hex uuid4 propre (pas de traversal possible via ce format), et
    tout ce qui sortirait de UPLOAD_DIR par construction."""
    if not file_id or not all(c in "0123456789abcdef" for c in file_id):
        return None
    dest_dir = UPLOAD_DIR / file_id
    if not dest_dir.is_dir():
        return None
    files = [f for f in dest_dir.iterdir() if f.is_file()]
    return files[0] if files else None

"""Chiffrement des jetons d'intégration (refresh tokens Google…) au repos.

Clé Fernet auto-générée au premier lancement dans data/integrations.key
(jamais versionnée, voir .gitignore) — pas de secret à configurer à la main
pour que ça marche, contrairement à CONSOLE_PASSWORD qui protège l'accès
réseau. Un jeton chiffré avec cette clé est illisible si data/ fuite seul
(backup, sync cloud…) mais pas si la machine entière est compromise — la
clé vit à côté. Suffisant pour l'usage visé : éviter le clair dans un JSON
qu'on pourrait copier/partager par erreur, pas résister à un attaquant qui
contrôle déjà le PC.
"""
from __future__ import annotations

from cryptography.fernet import Fernet

from brain import config

_fernet: Fernet | None = None


def _load_key() -> bytes:
    config.ensure_dirs()
    if config.INTEGRATIONS_KEY_FILE.exists():
        return config.INTEGRATIONS_KEY_FILE.read_bytes()
    key = Fernet.generate_key()
    config.INTEGRATIONS_KEY_FILE.write_bytes(key)
    return key


def _get() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_load_key())
    return _fernet


def encrypt(plaintext: str) -> str:
    return _get().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    return _get().decrypt(token.encode("ascii")).decode("utf-8")

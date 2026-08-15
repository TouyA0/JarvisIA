"""Authentification minimale entre le brain et ses agents.

Pas de comptes ni de rôles — c'est un réseau perso, pas un service
multi-utilisateurs. Un token opaque par appareil, généré une fois à
l'appairage, envoyé dans chaque `DeviceRegister`. Le brain le compare à
ce qu'il a en mémoire pour cet appareil (voir `brain/devices.py`, Phase 1)
et refuse la connexion (`RegisterAck(ok=False)`) si le token est absent,
inconnu ou révoqué.
"""
from __future__ import annotations

import secrets


def generate_token() -> str:
    """Token opaque pour un nouvel appareil, à distribuer une seule fois à l'appairage."""
    return secrets.token_urlsafe(32)

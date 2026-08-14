"""Clients API partagés (initialisés une seule fois)."""
from __future__ import annotations

from agents.desktop import config

_anthropic_client = None


def get_anthropic():
    """Client Anthropic, ou None si la clé API est absente."""
    global _anthropic_client
    if _anthropic_client is None and config.ANTHROPIC_API_KEY:
        import anthropic
        _anthropic_client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _anthropic_client

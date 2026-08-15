"""Historique de conversation en mémoire + journal persistant."""
from __future__ import annotations

conversation_history: list = []


def remember_exchange(question: str, answer: str, source: str = "") -> None:
    conversation_history.append({"role": "user", "content": question})
    conversation_history.append({"role": "assistant", "content": answer})
    if len(conversation_history) > 30:
        conversation_history[:] = conversation_history[-30:]

    # Journal persistant (data/logs/) — consultable plus tard
    try:
        from brain.core import convlog
        convlog.log_exchange(question, answer, source)
    except Exception:
        pass


def recent_text_history() -> list:
    """Historique récent réduit aux messages texte simples (les blocs outils
    sont locaux au tour d'agent)."""
    return [
        {"role": m["role"], "content": m["content"]}
        for m in conversation_history[-10:]
        if isinstance(m.get("content"), str)
    ]

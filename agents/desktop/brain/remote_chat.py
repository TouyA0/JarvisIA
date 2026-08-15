"""Conversation déportée vers le vrai brain central, quand joignable.

Jusqu'ici, la voix (ce process) et la Console web (brain/server.py)
tournaient chacune leur propre instance de brain.core.chat/history — deux
conversations, deux mémoires, jamais synchronisées. Ce module fait parler
la boucle vocale au MÊME brain que le web, via /ws/chat (déjà utilisé par
la Console, Phase 2) : une seule décision prise au même endroit, un seul
historique.

Repli automatique sur brain.core.chat (local, dans ce process) si le
brain n'est pas joignable — Jarvis continue de répondre sans lui, comme
avant. Ne concerne QUE la conversation pure ; le pilotage PC
(router.py/agent.py) reste local, voir docs/ROADMAP_MULTIDEVICE.md.
"""
from __future__ import annotations

import json

from websockets.exceptions import WebSocketException
from websockets.sync.client import connect

from agents.desktop import config

_CONNECT_TIMEOUT = 3


def _chat_url() -> str:
    return config.BRAIN_URL.replace("/ws/agent", "/ws/chat")


def ask_stream_remote(question: str, brain_state: dict):
    """Même contrat que brain.core.chat.ask_stream : générateur synchrone
    de phrases. Lève une exception si le brain est injoignable — à
    l'appelant de basculer sur le repli local."""
    with connect(_chat_url(), open_timeout=_CONNECT_TIMEOUT, close_timeout=2) as ws:
        ws.send(json.dumps({"question": question}))
        while True:
            raw = json.loads(ws.recv())
            msg_type = raw.get("type")
            if msg_type == "chat.phrase":
                yield raw["text"]
            elif msg_type == "chat.done":
                brain_state["source"] = raw.get("source") or "brain"
                return


def ask_stream(question: str, brain_state: dict | None = None):
    """Essaie le brain distant d'abord ; à défaut (désactivé, injoignable),
    repli sur brain.core.chat.ask_stream — comportement inchangé.

    Si l'échec survient APRÈS que des phrases ont déjà été prononcées, on
    n'enchaîne pas sur le repli local par-dessus (incohérent à l'oral,
    même logique que le repli Ollama → Claude dans brain.core.chat) : on
    annonce juste l'interruption.
    """
    if brain_state is None:
        brain_state = {}

    if config.BRAIN_ENABLED:
        produced_any = False
        try:
            for phrase in ask_stream_remote(question, brain_state):
                produced_any = True
                yield phrase
            return
        except (WebSocketException, OSError, TimeoutError) as e:
            print(f"[brain] conversation distante indisponible ({e}) — repli local.")
            if produced_any:
                yield "Ma connexion au brain a été interrompue, Monsieur."
                return

    from brain.core import chat
    yield from chat.ask_stream(question, brain_state)

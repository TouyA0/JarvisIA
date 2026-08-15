"""Serveur central (brain) : FastAPI + WebSocket.

Deux canaux distincts :
  /ws/agent  — un agent (agents/desktop, plus tard agents/mobile) s'y
               connecte, s'enregistre, répond aux commandes.
  /ws/chat   — la Console web (Phase 2) y envoie du texte, reçoit la
               réponse en streaming phrase par phrase.

Pas encore de pilotage PC ici : ask_stream (brain.core.chat) ne fait que
de la conversation Ollama/Claude, aucun tool-use. Le pilotage PC reste
pour l'instant dans agents/desktop/brain/agent.py, exécuté en local —
voir docs/ROADMAP_MULTIDEVICE.md, Phase 3.
"""
from __future__ import annotations

import asyncio
import threading
from typing import Any, Callable

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from agents.protocol.messages import (
    CommandResult,
    DeviceRegister,
    DeviceStatus,
    RegisterAck,
    parse_message,
)
from brain import config
from brain.core.chat import ask_stream
from brain.devices import Device, registry

config.ensure_dirs()

app = FastAPI(title="Jarvis Brain")

_SENTINEL = object()


async def _stream_sync_generator(gen_func: Callable[..., Any], *args, **kwargs):
    """Pont thread → asyncio : consomme un générateur synchrone (I/O bloquante,
    requests vers Ollama/Claude) sans geler la boucle d'événements FastAPI."""
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def worker() -> None:
        try:
            for item in gen_func(*args, **kwargs):
                loop.call_soon_threadsafe(queue.put_nowait, item)
        except Exception as exc:  # remonté au consommateur, jamais avalé en silence
            loop.call_soon_threadsafe(queue.put_nowait, exc)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _SENTINEL)

    threading.Thread(target=worker, daemon=True).start()
    while True:
        item = await queue.get()
        if item is _SENTINEL:
            return
        if isinstance(item, Exception):
            raise item
        yield item


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "devices": [d.device_id for d in registry.list()]}


@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket) -> None:
    """Chat texte simple pour la Console web — pas de pilotage PC (Phase 2)."""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            question = (data.get("question") or "").strip()
            if not question:
                continue
            async for phrase in _stream_sync_generator(ask_stream, question):
                await websocket.send_json({"type": "chat.phrase", "text": phrase})
            await websocket.send_json({"type": "chat.done"})
    except WebSocketDisconnect:
        pass


@app.websocket("/ws/agent")
async def ws_agent(websocket: WebSocket) -> None:
    """Canal de contrôle d'un agent : enregistrement, heartbeat, résultats de commande."""
    await websocket.accept()
    device_id: str | None = None
    try:
        raw = await websocket.receive_json()
        try:
            msg = parse_message(raw)
        except (ValueError, ValidationError) as exc:
            await websocket.send_json(RegisterAck(device_id="", ok=False, reason=str(exc)).model_dump())
            await websocket.close()
            return

        if not isinstance(msg, DeviceRegister):
            await websocket.send_json(RegisterAck(
                device_id="", ok=False, reason="premier message attendu : device.register",
            ).model_dump())
            await websocket.close()
            return

        # TODO Phase 1 suite : vérifier msg.token contre un registre persistant
        # (data/devices.json) au lieu d'accepter tout token non vide.
        if not msg.token:
            await websocket.send_json(RegisterAck(
                device_id=msg.device_id, ok=False, reason="token manquant",
            ).model_dump())
            await websocket.close()
            return

        device_id = msg.device_id
        registry.register(Device(
            device_id=msg.device_id,
            name=msg.name,
            device_type=msg.device_type,
            capabilities=list(msg.capabilities),
            websocket=websocket,
        ))
        await websocket.send_json(RegisterAck(device_id=msg.device_id, ok=True).model_dump())
        print(f"[brain] appareil connecté : {msg.name} ({msg.device_id})")

        while True:
            raw = await websocket.receive_json()
            msg = parse_message(raw)
            if isinstance(msg, DeviceStatus):
                registry.touch(msg.device_id, msg.status)
            elif isinstance(msg, CommandResult):
                registry.resolve(msg)
    except WebSocketDisconnect:
        pass
    finally:
        if device_id:
            registry.unregister(device_id)
            print(f"[brain] appareil déconnecté : {device_id}")


def start() -> None:
    import uvicorn
    uvicorn.run(app, host=config.HOST, port=config.PORT)


if __name__ == "__main__":
    start()

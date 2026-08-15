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

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from agents.protocol.auth import generate_token
from agents.protocol.messages import (
    CommandResult,
    DeviceRegister,
    DeviceStatus,
    RegisterAck,
    parse_message,
)
from brain import config, device_store, pairing
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


@app.get("/api/devices")
async def list_devices() -> list[dict]:
    """Tous les appareils appairés (connus), en ligne ou pas — l'écran Centre
    d'appareils affiche aussi ceux actuellement hors ligne."""
    live = {d.device_id: d for d in registry.list()}
    result = []
    for known in device_store.list_known():
        device_id = known["device_id"]
        live_dev = live.get(device_id)
        result.append({
            "device_id": device_id,
            "name": known["name"],
            "device_type": known["device_type"],
            "paired_at": known["paired_at"],
            "capabilities": live_dev.capabilities if live_dev else [],
            "status": live_dev.status if live_dev else "offline",
        })
    return result


@app.post("/api/pairing/code")
async def create_pairing_code() -> dict:
    """Génère un code d'appairage à usage unique (5 min) — affiché côté
    Centre d'appareils, à saisir sur le nouvel agent."""
    return {"code": pairing.create_code()}


@app.delete("/api/devices/{device_id}")
async def forget_device(device_id: str) -> dict:
    """Révoque un appareil appairé — il devra être ré-appairé pour revenir."""
    live_dev = registry.get(device_id)
    if live_dev:
        await live_dev.websocket.close()
        registry.unregister(device_id)
    if not device_store.forget(device_id):
        raise HTTPException(404, f"appareil {device_id!r} inconnu")
    return {"ok": True}


@app.post("/api/devices/{device_id}/dispatch")
async def dispatch_command(device_id: str, body: dict) -> dict:
    """Envoie une commande à un agent connecté et attend son résultat.

    Utilisé pour l'instant pour valider la Phase 3 en conditions réelles ;
    deviendra le point d'entrée du bouton « exécuter » côté Focus appareil
    (Phase 4).
    """
    tool = body.get("tool")
    if not tool:
        raise HTTPException(400, "tool manquant")
    try:
        result = await registry.dispatch(device_id, tool, body.get("args", {}))
    except KeyError:
        raise HTTPException(404, f"appareil {device_id!r} non connecté")
    except asyncio.TimeoutError:
        raise HTTPException(504, "l'appareil n'a pas répondu à temps")
    return result.model_dump()


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

        issued_token = None
        known = device_store.find_by_token(msg.token) if msg.token else None

        if known:
            # Reconnexion normale : le token présenté est déjà celui émis à
            # l'appairage. On fait confiance au device_id qu'il porte déjà.
            pass
        elif msg.token and pairing.consume(msg.token):
            # Premier appairage : msg.token était en fait le code affiché
            # côté Centre d'appareils, pas un vrai token — on en émet un
            # définitif que l'agent devra sauvegarder pour la suite.
            issued_token = generate_token()
            device_store.register(msg.device_id, msg.name, msg.device_type, issued_token)
        else:
            await websocket.send_json(RegisterAck(
                device_id=msg.device_id, ok=False,
                reason="token invalide, expiré, ou appareil non appairé",
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
        await websocket.send_json(RegisterAck(
            device_id=msg.device_id, ok=True, issued_token=issued_token,
        ).model_dump())
        print(f"[brain] appareil connecté : {msg.name} ({msg.device_id})"
              + (" [nouvel appairage]" if issued_token else ""))

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

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

from fastapi import FastAPI, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from agents.protocol.auth import generate_token
from agents.protocol.messages import (
    CommandResult,
    DeviceRegister,
    DeviceStatus,
    RegisterAck,
    parse_message,
)
from brain import activity, config, device_store, pairing, routines, speech
from brain.core.chat import ask_stream
from brain.devices import Device, registry

config.ensure_dirs()

app = FastAPI(title="Jarvis Brain")

if not config.CONSOLE_PASSWORD:
    print("[brain] CONSOLE_PASSWORD non défini — API et Console accessibles sans "
          "authentification à quiconque atteint ce serveur (VPN/LAN compris). "
          "À définir dans .env avant toute exposition au-delà de 127.0.0.1.")


@app.middleware("http")
async def _require_console_auth(request: Request, call_next):
    """Rempart unique devant toute l'API : sans lui, quiconque atteint le
    brain sur le réseau (VPN, LAN) peut déjà tout faire — lire les
    appareils, dispatcher des commandes, déclencher des routines. Devient
    plus sensible depuis que le chat peut piloter le PC en langage libre,
    pas seulement via les boutons figés de Focus. /api/health reste ouvert
    (sondes de démarrage, aucune donnée sensible)."""
    path = request.url.path
    if config.CONSOLE_PASSWORD and path.startswith("/api/") and path != "/api/health":
        auth = request.headers.get("authorization", "")
        token = auth[7:] if auth.lower().startswith("bearer ") else ""
        if token != config.CONSOLE_PASSWORD:
            return JSONResponse({"detail": "authentification requise"}, status_code=401)
    return await call_next(request)


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


@app.get("/api/devices/{device_id}")
async def get_device(device_id: str) -> dict:
    live_dev = registry.get(device_id)
    known = next((d for d in device_store.list_known() if d["device_id"] == device_id), None)
    if not known:
        raise HTTPException(404, f"appareil {device_id!r} inconnu")
    return {
        "device_id": device_id,
        "name": known["name"],
        "device_type": known["device_type"],
        "paired_at": known["paired_at"],
        "capabilities": live_dev.capabilities if live_dev else [],
        "status": live_dev.status if live_dev else "offline",
    }


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
        activity.record(device_id, tool, ok=False, error="timeout")
        raise HTTPException(504, "l'appareil n'a pas répondu à temps")
    activity.record(device_id, tool, ok=result.ok, error=result.error)
    return result.model_dump()


@app.get("/api/devices/{device_id}/activity")
async def device_activity(device_id: str) -> list[dict]:
    return activity.for_device(device_id)


@app.get("/api/routines")
async def list_routines() -> list[dict]:
    return routines.list_routines()


@app.post("/api/routines")
async def create_routine(body: dict) -> dict:
    name = (body.get("name") or "").strip()
    steps = body.get("steps") or []
    if not name:
        raise HTTPException(400, "nom manquant")
    if not steps:
        raise HTTPException(400, "au moins une étape requise")
    return routines.create(name, steps)


@app.delete("/api/routines/{routine_id}")
async def delete_routine(routine_id: str) -> dict:
    if not routines.delete(routine_id):
        raise HTTPException(404, f"routine {routine_id!r} inconnue")
    return {"ok": True}


@app.post("/api/routines/{routine_id}/run")
async def run_routine(routine_id: str) -> dict:
    if not routines.exists(routine_id):
        raise HTTPException(404, f"routine {routine_id!r} inconnue")
    asyncio.create_task(routines.run(routine_id))
    return {"ok": True}


@app.get("/api/routines/{routine_id}/status")
async def routine_status(routine_id: str) -> dict:
    return routines.status(routine_id) or {"status": "idle"}


@app.post("/api/speech/transcribe")
async def transcribe_speech(file: UploadFile) -> dict:
    """Transcrit un segment audio envoyé par la Console web (Phase 9).

    Appel bloquant (I/O réseau vers Speaches) exécuté dans le threadpool
    de FastAPI par défaut pour les endpoints `def` synchrones — mais ici
    la fonction est `async`, donc on le fait explicitement pour ne pas
    geler la boucle d'événements pendant l'appel à Speaches.
    """
    audio_bytes = await file.read()
    text = await asyncio.to_thread(
        speech.transcribe, audio_bytes, file.filename or "audio.webm", file.content_type or "audio/webm",
    )
    return {"text": text}


@app.post("/api/speech/synthesize")
async def synthesize_speech(body: dict) -> Response:
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text manquant")
    audio = await asyncio.to_thread(speech.synthesize, text)
    if audio is None:
        raise HTTPException(502, "synthèse vocale indisponible")
    return Response(content=audio, media_type="audio/mpeg")


@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket) -> None:
    """Chat texte — utilisé par la Console web (Phase 2) et, depuis la
    Phase 3 suite, par la boucle vocale de l'agent desktop elle-même
    (voir agents/desktop/brain/remote_chat.py) : les deux partagent
    maintenant la même conversation/mémoire, un seul brain qui décide.
    Pas de pilotage PC ici, juste la conversation Ollama/Claude.
    """
    await websocket.accept()
    if config.CONSOLE_PASSWORD and websocket.query_params.get("token") != config.CONSOLE_PASSWORD:
        # Pas de header custom possible au handshake WebSocket depuis un
        # navigateur — le token passe donc en paramètre de requête, comme
        # web/src/lib/useConsoleAuth.js le construit.
        await websocket.close(code=4401)
        return
    try:
        while True:
            data = await websocket.receive_json()
            question = (data.get("question") or "").strip()
            if not question:
                continue
            brain_state: dict = {}
            async for phrase in _stream_sync_generator(ask_stream, question, brain_state):
                await websocket.send_json({"type": "chat.phrase", "text": phrase})
            await websocket.send_json({"type": "chat.done", "source": brain_state.get("source")})
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


# Doit être monté APRÈS toutes les routes /api et /ws ci-dessus : Starlette
# essaie les routes dans l'ordre d'enregistrement, donc /api/... continue de
# matcher ses handlers avant que ce montage catch-all ne s'en charge.
# Nécessaire pour la Phase 9 (détection locale du mot d'éveil) : le
# navigateur importe dynamiquement des fichiers .wasm/.mjs, ce que le
# serveur de dev Vite refuse pour les fichiers de web/public — brain sert
# le vrai build (web/dist) sans cette restriction. `npm run build` d'abord.
_WEB_DIST = config.ROOT / "web" / "dist"
if _WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=str(_WEB_DIST), html=True), name="web")
else:
    print(f"[brain] {_WEB_DIST} introuvable — lance `npm run build` dans web/ pour servir la Console ici.")


def start() -> None:
    import uvicorn
    uvicorn.run(app, host=config.HOST, port=config.PORT)


if __name__ == "__main__":
    start()

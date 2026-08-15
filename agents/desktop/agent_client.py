"""Client WebSocket : connecte l'agent desktop au brain central.

Se connecte à `brain/server.py` (`/ws/agent`), s'enregistre, écoute les
`command.dispatch` et les exécute via `agents/desktop/tools/registry.py`
(déjà tout prêt — mêmes outils que ceux utilisés en local par l'agent
Claude aujourd'hui).

Volontairement un canal PARALLÈLE et OPTIONNEL pour l'instant : ce module
ne touche pas à `runtime.py` ni à la boucle vocale existante. Il se lance
à part (`python -m agents.desktop.agent_client`) pour valider le
protocole de bout en bout — enregistrement, heartbeat, dispatch, résultat
— avant toute décision sur COMMENT router.py/commands.py/agent.py
devraient un jour appeler ça au lieu d'exécuter en local. Cette décision
d'intégration n'est pas prise ici, voir docs/ROADMAP_MULTIDEVICE.md,
Phase 3.
"""
from __future__ import annotations

import asyncio
import json
import platform
import uuid

import websockets

from agents.desktop import config
from agents.desktop.tools import registry
from agents.protocol.auth import generate_token
from agents.protocol.messages import (
    CommandDispatch,
    CommandResult,
    DeviceRegister,
    DeviceStatus,
    RegisterAck,
    parse_message,
)

HEARTBEAT_SECONDS = 20
RECONNECT_SECONDS = 5


def _load_identity() -> dict:
    """Identité stable de cet agent — générée une fois, réutilisée à chaque
    connexion (le brain doit reconnaître le même appareil d'une fois à
    l'autre, pas un nouveau à chaque redémarrage)."""
    if config.DEVICE_ID_FILE.exists():
        with open(config.DEVICE_ID_FILE, encoding="utf-8") as f:
            return json.load(f)
    identity = {"device_id": uuid.uuid4().hex, "token": generate_token()}
    config.DEVICE_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(config.DEVICE_ID_FILE, "w", encoding="utf-8") as f:
        json.dump(identity, f, ensure_ascii=False, indent=2)
    return identity


def _execute(tool: str, args: dict) -> tuple[bool, dict | None, str | None]:
    """Exécute un outil via le registry existant, capture toute exception
    pour qu'une erreur outil ne tue jamais la connexion au brain."""
    try:
        result = registry.execute(tool, args)
    except Exception as exc:
        return False, None, str(exc)
    if isinstance(result, dict):
        return True, result, None
    return True, {"text": result}, None


async def _heartbeat(ws, device_id: str) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_SECONDS)
        await ws.send(json.dumps(DeviceStatus(device_id=device_id, status="online").model_dump()))


async def _handle_connection(ws, identity: dict) -> None:
    await ws.send(json.dumps(DeviceRegister(
        device_id=identity["device_id"],
        name=platform.node() or "PC fixe",
        device_type="desktop",
        capabilities=["screen", "input", "exec"],
        token=identity["token"],
    ).model_dump()))

    ack = parse_message(json.loads(await ws.recv()))
    if not isinstance(ack, RegisterAck) or not ack.ok:
        reason = getattr(ack, "reason", None) or "raison inconnue"
        print(f"[agent] enregistrement refusé par le brain : {reason}")
        return

    print(f"[agent] connecté au brain en tant que {identity['device_id']} ({ack.device_id})")
    heartbeat_task = asyncio.create_task(_heartbeat(ws, identity["device_id"]))
    try:
        async for raw in ws:
            msg = parse_message(json.loads(raw))
            if not isinstance(msg, CommandDispatch):
                continue
            ok, result, error = _execute(msg.tool, msg.args)
            await ws.send(json.dumps(CommandResult(
                request_id=msg.request_id,
                device_id=identity["device_id"],
                ok=ok,
                result=result,
                error=error,
            ).model_dump()))
    finally:
        heartbeat_task.cancel()


async def run(brain_url: str | None = None) -> None:
    identity = _load_identity()
    url = brain_url or config.BRAIN_URL
    while True:
        try:
            async with websockets.connect(url) as ws:
                await _handle_connection(ws, identity)
        except (websockets.exceptions.ConnectionClosed, OSError) as exc:
            print(f"[agent] brain injoignable ({exc}) — nouvelle tentative dans {RECONNECT_SECONDS}s")
        await asyncio.sleep(RECONNECT_SECONDS)


def start() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    start()

"""Registre des agents connectés + dispatch de commandes.

En mémoire uniquement (vidé au redémarrage du brain) — pas besoin de
persistance pour l'instant, un agent se réenregistre à chaque connexion.

Ce module sait envoyer une commande à un agent précis et attendre sa
réponse (corrélées par `request_id`), mais personne ne l'appelle encore :
router.py/commands.py/agent.py continuent d'exécuter localement dans
l'agent desktop (Phase 3 branchera ça une fois l'agent desktop reconverti
en client WebSocket).
"""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field

from fastapi import WebSocket

from agents.protocol.messages import CommandDispatch, CommandResult, DeviceType


@dataclass
class Device:
    device_id: str
    name: str
    device_type: DeviceType
    capabilities: list[str]
    websocket: WebSocket
    connected_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    status: str = "online"


class DeviceRegistry:
    """Un seul brain, potentiellement plusieurs agents — tout passe par ici."""

    def __init__(self) -> None:
        self._devices: dict[str, Device] = {}
        self._pending: dict[str, asyncio.Future[CommandResult]] = {}

    # ── Cycle de vie ──────────────────────────────────────────────────────────
    def register(self, device: Device) -> None:
        self._devices[device.device_id] = device

    def unregister(self, device_id: str) -> None:
        self._devices.pop(device_id, None)

    def touch(self, device_id: str, status: str = "online") -> None:
        dev = self._devices.get(device_id)
        if dev:
            dev.last_seen = time.time()
            dev.status = status

    def get(self, device_id: str) -> Device | None:
        return self._devices.get(device_id)

    def list(self) -> list[Device]:
        return list(self._devices.values())

    def pick_default_device(self) -> str | None:
        """Appareil cible implicite pour le pilotage PC déclenché depuis le
        chat (Phase 10) : un seul appareil réel existe aujourd'hui, donc pas
        de sélecteur — juste celui qui sait exécuter des outils
        (capacité "exec"). None si aucun ou plusieurs (ambigu) ; la
        désambiguïsation explicite est reportée sciemment, comme le
        "routage contextuel" de la Phase 4, tant qu'il n'y a pas un vrai
        deuxième appareil à cibler."""
        candidates = [d for d in self._devices.values() if "exec" in d.capabilities]
        return candidates[0].device_id if len(candidates) == 1 else None

    # ── Dispatch ──────────────────────────────────────────────────────────────
    async def dispatch(self, device_id: str, tool: str, args: dict, timeout: float = 15.0) -> CommandResult:
        """Envoie une commande à un appareil et attend son résultat.

        Lève TimeoutError si l'appareil ne répond pas dans le délai, ou
        KeyError s'il n'est pas connecté.
        """
        dev = self._devices[device_id]
        request_id = uuid.uuid4().hex
        message = CommandDispatch(request_id=request_id, device_id=device_id, tool=tool, args=args)

        loop = asyncio.get_running_loop()
        future: asyncio.Future[CommandResult] = loop.create_future()
        self._pending[request_id] = future
        try:
            await dev.websocket.send_json(message.model_dump())
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self._pending.pop(request_id, None)

    def resolve(self, result: CommandResult) -> None:
        """À appeler quand un command.result arrive — débloque le dispatch en attente."""
        future = self._pending.get(result.request_id)
        if future and not future.done():
            future.set_result(result)


registry = DeviceRegistry()

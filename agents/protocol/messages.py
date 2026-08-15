"""Schéma des messages échangés en WebSocket entre le brain et les agents.

Contrat unique entre `brain/` et `agents/*` : aucun appel direct d'un
package à l'autre, tout passe par des messages JSON validés par ces
modèles Pydantic. Chaque message porte un champ `type` qui sélectionne
son schéma (voir MESSAGE_TYPES en bas de fichier).

Sens des échanges :
    agent → brain : DeviceRegister, DeviceStatus, CommandResult
    brain → agent : RegisterAck, CommandDispatch
"""
from __future__ import annotations

import time
from typing import Literal

from pydantic import BaseModel, Field

DeviceType = Literal["desktop", "mobile"]

# Ce qu'un agent sait faire — le brain n'envoie un command.dispatch à un
# appareil que si le tool demandé correspond à une de ses capabilities.
Capability = Literal["screen", "input", "exec", "audio", "notify"]


# ══ Agent → Brain ═══════════════════════════════════════════════════════════
class DeviceRegister(BaseModel):
    """Premier message envoyé par un agent à la connexion WebSocket."""

    type: Literal["device.register"] = "device.register"
    device_id: str
    name: str
    device_type: DeviceType
    capabilities: list[Capability]
    token: str


class DeviceStatus(BaseModel):
    """Heartbeat périodique — permet au brain de détecter un agent mort."""

    type: Literal["device.status"] = "device.status"
    device_id: str
    status: Literal["online", "busy", "offline"]
    ts: float = Field(default_factory=time.time)


class CommandResult(BaseModel):
    """Réponse d'un agent à un CommandDispatch reçu du brain."""

    type: Literal["command.result"] = "command.result"
    request_id: str
    device_id: str
    ok: bool
    result: dict | None = None
    error: str | None = None


# ══ Brain → Agent ═══════════════════════════════════════════════════════════
class RegisterAck(BaseModel):
    """Réponse du brain à un DeviceRegister — accepte ou refuse la connexion."""

    type: Literal["device.register_ack"] = "device.register_ack"
    device_id: str
    ok: bool
    reason: str | None = None


class CommandDispatch(BaseModel):
    """Ordre du brain vers un agent précis, à exécuter via son registry de tools."""

    type: Literal["command.dispatch"] = "command.dispatch"
    request_id: str
    device_id: str
    tool: str
    args: dict = Field(default_factory=dict)


MESSAGE_TYPES: dict[str, type[BaseModel]] = {
    "device.register": DeviceRegister,
    "device.register_ack": RegisterAck,
    "device.status": DeviceStatus,
    "command.dispatch": CommandDispatch,
    "command.result": CommandResult,
}


def parse_message(raw: dict) -> BaseModel:
    """Décode un message JSON brut vers son modèle Pydantic, selon son champ `type`."""
    msg_type = raw.get("type")
    model = MESSAGE_TYPES.get(msg_type)
    if model is None:
        raise ValueError(f"Type de message inconnu : {msg_type!r}")
    return model.model_validate(raw)

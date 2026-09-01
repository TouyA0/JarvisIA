"""Comptes tiers connectés — stockage générique, un compte par service
(Google Calendar aujourd'hui, Drive/Gmail/Spotify demain sur le même
modèle). Même forme que brain/routines.py (JSON + lock), le jeton en plus
étant chiffré via brain.integrations.crypto avant écriture.
"""
from __future__ import annotations

import json
import threading
import time
import uuid

from brain import config
from brain.integrations import crypto

_lock = threading.Lock()


def _load() -> dict:
    if config.INTEGRATIONS_FILE.exists():
        with open(config.INTEGRATIONS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"accounts": []}


def _save(data: dict) -> None:
    config.ensure_dirs()
    with open(config.INTEGRATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def list_public(account_type: str | None = None) -> list[dict]:
    """Comptes sans le jeton — c'est la seule vue que l'API/Console voit."""
    accounts = _load()["accounts"]
    if account_type:
        accounts = [a for a in accounts if a["type"] == account_type]
    return [
        {"id": a["id"], "type": a["type"], "label": a["label"], "connected_at": a["connected_at"]}
        for a in accounts
    ]


def list_for(account_type: str) -> list[dict]:
    """Comptes complets (jeton déchiffré) pour un type donné — usage interne
    des modules d'intégration uniquement, jamais exposé tel quel à l'API."""
    result = []
    for a in _load()["accounts"]:
        if a["type"] != account_type:
            continue
        result.append({**a, "refresh_token": crypto.decrypt(a["refresh_token_enc"]), "extra": a.get("extra", {})})
    return result


def add(account_type: str, label: str, refresh_token: str, extra: dict | None = None) -> dict:
    """`extra` : métadonnées propres au fournisseur, non chiffrées (rien de
    secret dedans — pour Zoho par ex. : région du datacenter, accountId
    Zoho Mail nécessaire à toutes les requêtes). Stockées telles quelles,
    renvoyées par list_for(), jamais par list_public()."""
    account = {
        "id": uuid.uuid4().hex,
        "type": account_type,
        "label": label,
        "connected_at": time.time(),
        "refresh_token_enc": crypto.encrypt(refresh_token),
        "extra": extra or {},
    }
    with _lock:
        data = _load()
        # Reconnecter le même compte (même label) remplace l'ancien jeton
        # plutôt que de dupliquer la carte côté Console.
        data["accounts"] = [a for a in data["accounts"] if not (a["type"] == account_type and a["label"] == label)]
        data["accounts"].append(account)
        _save(data)
    return {"id": account["id"], "type": account_type, "label": label, "connected_at": account["connected_at"]}


def remove(account_id: str) -> bool:
    with _lock:
        data = _load()
        before = len(data["accounts"])
        data["accounts"] = [a for a in data["accounts"] if a["id"] != account_id]
        _save(data)
    return len(data["accounts"]) < before

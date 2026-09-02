"""Web Push (C12) — atteindre une Console fermée ou en arrière-plan.

Jusqu'ici, `new Notification(...)` dans Hud.jsx (voir useCardFeed.js) ne
fonctionne que si l'onglet de la Console est ouvert et le socket /ws/cards
connecté : un minuteur qui sonne pendant que Monsieur a changé d'appli sur
son téléphone, ou simplement verrouillé l'écran, ne l'atteint jamais. Le
Web Push standard (RFC 8030, chiffré VAPID) résout ça : le navigateur
maintient sa propre connexion avec le service push du système
d'exploitation (FCM, Mozilla, APNs web push…), indépendante de la nôtre —
c'est ce canal-là qui réveille web/public/sw.js même onglet fermé.

Duplique volontairement le déclenchement (et seulement lui) plutôt que de
remplacer /ws/cards : ce dernier reste le canal principal, immédiat, pour
toute Console déjà ouverte (mise à jour de l'UI, pas seulement la
notification) — le push est le complément pour le cas où rien n'écoute.
"""
from __future__ import annotations

import base64
import json
import threading
from typing import Any

from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)
from pywebpush import WebPushException, webpush
from py_vapid import Vapid

from brain import config


def _vapid_keys() -> dict:
    """Paire de clés VAPID, générée une fois puis relue — tous les
    abonnements de navigateur (chaque `pushManager.subscribe(...)`, voir
    web/src/lib/usePush.js) sont signés avec la même paire pour la durée de
    vie de l'installation ; en changer invaliderait tous les abonnements
    existants."""
    if config.VAPID_FILE.exists():
        with open(config.VAPID_FILE, encoding="utf-8") as f:
            return json.load(f)

    vapid = Vapid()
    vapid.generate_keys()
    # Format attendu par `PushManager.subscribe({ applicationServerKey })` :
    # le point EC non compressé (65 octets, préfixe 0x04), en base64url sans
    # padding — ni le DER ni le PEM que py_vapid expose directement.
    raw_point = vapid.public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    # `pywebpush.webpush(vapid_private_key=...)` relit cette chaîne via
    # `Vapid.from_string` (py_vapid), qui n'accepte ni le PEM ni un objet
    # clé — seulement du DER PKCS8 (ou du raw 32 octets) en base64url.
    der_key = vapid.private_key.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())
    keys = {
        "private_key": base64.urlsafe_b64encode(der_key).rstrip(b"=").decode("ascii"),
        "public_key": base64.urlsafe_b64encode(raw_point).rstrip(b"=").decode("ascii"),
    }
    config.ensure_dirs()
    with open(config.VAPID_FILE, "w", encoding="utf-8") as f:
        json.dump(keys, f)
    return keys


def public_key() -> str:
    """Clé publique VAPID, au format urlsafe-base64 attendu par
    `PushManager.subscribe({ applicationServerKey })` côté navigateur."""
    return _vapid_keys()["public_key"]


_lock = threading.Lock()


def _load_subscriptions() -> list[dict]:
    if config.PUSH_SUBSCRIPTIONS_FILE.exists():
        with open(config.PUSH_SUBSCRIPTIONS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_subscriptions(subs: list[dict]) -> None:
    config.ensure_dirs()
    with open(config.PUSH_SUBSCRIPTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(subs, f, ensure_ascii=False, indent=2)


def subscribe(subscription: dict) -> None:
    """Enregistre (ou met à jour) l'abonnement d'un navigateur — `endpoint`
    l'identifie de façon unique, un même appareil peut se réabonner (perte
    de `localStorage`, changement de navigateur) sans créer de doublon."""
    endpoint = subscription.get("endpoint")
    if not endpoint:
        return
    with _lock:
        subs = _load_subscriptions()
        subs = [s for s in subs if s.get("endpoint") != endpoint]
        subs.append(subscription)
        _save_subscriptions(subs)


def unsubscribe(endpoint: str) -> None:
    with _lock:
        subs = _load_subscriptions()
        subs = [s for s in subs if s.get("endpoint") != endpoint]
        _save_subscriptions(subs)


def notify_all(title: str, body: str, tag: str = "", data: dict[str, Any] | None = None) -> None:
    """Pousse une notification à tous les navigateurs abonnés. Appelé
    depuis `brain/cards.py::emit` pour les cartes "timer" et "proactive" —
    les deux seules qui déclenchaient déjà `new Notification(...)` côté
    Hud.jsx, donc les deux seules qui justifient de réveiller un appareil
    dont l'onglet est fermé."""
    with _lock:
        subs = _load_subscriptions()
    if not subs:
        return

    payload = json.dumps({"title": title, "body": body, "tag": tag, "data": data or {}})
    keys = _vapid_keys()
    stale: list[str] = []
    for sub in subs:
        try:
            webpush(
                subscription_info=sub,
                data=payload,
                vapid_private_key=keys["private_key"],
                vapid_claims={"sub": f"mailto:{config.VAPID_CONTACT_EMAIL}"},
            )
        except WebPushException as exc:
            # 404/410 : abonnement périmé (désinstallation, permission
            # révoquée, cache navigateur vidé) — le service push nous le
            # dit lui-même, plutôt que de laisser la liste grossir de
            # cibles mortes indéfiniment.
            status = exc.response.status_code if exc.response is not None else None
            if status in (404, 410):
                stale.append(sub.get("endpoint", ""))
            else:
                print(f"[brain][push] échec d'envoi : {exc}")

    if stale:
        with _lock:
            subs = _load_subscriptions()
            subs = [s for s in subs if s.get("endpoint") not in stale]
            _save_subscriptions(subs)

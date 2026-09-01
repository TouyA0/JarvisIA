"""Cartes — le canal d'affichage riche de Jarvis.

Socle prévu par `docs/ROADMAP_DISPLAY_INTEGRATIONS.md` §2. Jusqu'ici, tout
ce que Jarvis allait chercher (agenda, mails, fichiers, morceau en cours,
capture d'écran) revenait en texte formaté : lisible à voix haute, pauvre à
l'écran. Une carte est la même information, mais structurée, que la Console
web sait afficher pour de vrai.

Deux chemins de sortie, volontairement :

  - **diffusion** (`subscribe`) — toute carte émise part vers TOUTES les
    Consoles ouvertes, quel que soit le client à l'origine de la demande.
    C'est ce qui fait qu'une question posée à voix haute au PC fixe
    illumine l'écran d'à côté, au lieu que l'affichage ne suive que la
    fenêtre qui a parlé.
  - **tampon circulaire** (`recent`) — les dernières cartes survivent à un
    rafraîchissement de page ; sans ça, ouvrir la Console juste après avoir
    parlé donnerait un écran vide.

Le tampon `recent()` ne survit pas à un redémarrage — pour ça, chaque carte
est aussi ajoutée à un journal JSONL mensuel (même mécanisme que
`brain/core/convlog.py`), lu par `history()`. Les champs volumineux
(l'image d'une capture d'écran, notamment) sont retirés avant écriture :
le journal sert à retrouver CE QUI a été affiché et QUAND, pas à
rejouer l'image elle-même — sans ce filtre, quelques captures suffiraient
à faire grossir le fichier de plusieurs Mo par jour pour rien.
"""
from __future__ import annotations

import asyncio
import itertools
import json
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

from brain import config

# Attributs qu'on sait volumineux et sans intérêt à relire plus tard —
# retirés de la copie écrite sur disque, jamais de celle diffusée en direct.
_STRIP_ON_DISK = {"image_b64"}

# 30 cartes ≈ une bonne session de travail. Au-delà, la Console ferait
# défiler un mur d'instantanés périmés — les cartes vieillissent vite.
_MAX_CARDS = 30

_lock = threading.Lock()
_recent: deque[dict] = deque(maxlen=_MAX_CARDS)
_ids = itertools.count(1)


@dataclass
class _Subscriber:
    queue: asyncio.Queue
    loop: asyncio.AbstractEventLoop


_subscribers: list[_Subscriber] = []


def subscribe() -> asyncio.Queue:
    """À appeler depuis une coroutine (le endpoint WebSocket). La boucle
    de l'appelant est mémorisée avec la file : `emit()` est appelé depuis
    un thread d'outil, pas depuis la boucle asyncio, et n'a donc pas le
    droit de toucher la Queue directement."""
    sub = _Subscriber(queue=asyncio.Queue(), loop=asyncio.get_running_loop())
    with _lock:
        _subscribers.append(sub)
    return sub.queue


def unsubscribe(queue: asyncio.Queue) -> None:
    with _lock:
        for sub in list(_subscribers):
            if sub.queue is queue:
                _subscribers.remove(sub)


def _publish(message: dict) -> None:
    """Envoie un message à toutes les Consoles abonnées. Sans danger depuis
    n'importe quel thread — les outils tournent dans le threadpool, pas
    dans la boucle asyncio."""
    with _lock:
        subs = list(_subscribers)
    for sub in subs:
        try:
            sub.loop.call_soon_threadsafe(sub.queue.put_nowait, message)
        except RuntimeError:
            # Boucle fermée entre-temps (onglet fermé pendant l'émission) :
            # le endpoint se désabonnera de lui-même, rien à faire ici.
            pass


def emit(card_type: str, title: str, data: dict[str, Any], subtitle: str = "",
         actions: list[dict] | None = None) -> dict:
    """Publie une carte."""
    card = {
        "id": f"c{next(_ids)}",
        "type": card_type,
        "title": title,
        "subtitle": subtitle,
        "data": data,
        "actions": actions or [],
        "at": time.time(),
    }
    with _lock:
        _recent.append(card)
    _publish({"kind": "card", "card": card})
    _persist(card)
    return card


def _persist(card: dict) -> None:
    config.ensure_dirs()
    stripped = {**card, "data": {k: v for k, v in card["data"].items() if k not in _STRIP_ON_DISK}}
    path = config.LOGS_DIR / f"cards-{time.strftime('%Y-%m')}.jsonl"
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(stripped, ensure_ascii=False) + "\n")
    except OSError as exc:
        print(f"[brain][cards] échec d'écriture du journal : {exc}")


def history(limit: int = 100) -> list[dict]:
    """Les `limit` dernières cartes émises, du plus ancien au plus récent —
    survit à un redémarrage, contrairement à `recent()`. Même schéma de
    lecture à rebours que brain/core/convlog.py::recent."""
    files = sorted(config.LOGS_DIR.glob("cards-*.jsonl"), reverse=True)
    entries: list[dict] = []
    for path in files:
        try:
            with open(path, encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            continue
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
            if len(entries) >= limit:
                return list(reversed(entries))
    return list(reversed(entries))


def exchange(question: str, answer: str, source: str = "") -> None:
    """Diffuse un tour de conversation — quel que soit le client qui l'a
    déclenché. C'est ce qui permet à la Console de rester allumée en
    arrière-plan et d'afficher ce que Monsieur vient de demander à voix
    haute au PC fixe, sans qu'elle ait elle-même posé la question.

    Rien n'est mémorisé ici : l'historique durable est déjà écrit par
    brain/core/convlog.py, appelé depuis le même endroit."""
    _publish({
        "kind": "exchange",
        "question": question,
        "answer": answer,
        "source": source,
        "at": time.time(),
    })


def recent(limit: int = _MAX_CARDS) -> list[dict]:
    with _lock:
        return list(_recent)[-limit:]


def clear() -> None:
    with _lock:
        _recent.clear()

"""Minuteurs & rappels — source de vérité brain (C1).

Jusqu'ici entièrement locaux à agents/desktop/services/timers.py : posés à
la voix, invisibles du web/téléphone puisque le brain n'en savait rien. Ce
module donne au brain sa propre liste de minuteurs, indépendante de celle
du desktop (qui garde son fonctionnement local — chime + annonce vocale
sans dépendre du réseau) : « minuteur 5 minutes » tapé ou dit depuis
n'importe quelle Console web crée désormais un minuteur que TOUTES les
Consoles voient, via /api/timers et le compte à rebours du bandeau ambiant
(Hud.jsx). À l'échéance, une carte est émise sur /ws/cards — c'est elle qui
déclenche la notification navigateur côté web (useCardFeed → Notification).
"""
from __future__ import annotations

import re
import threading
import time
import uuid
from typing import Optional

from brain import cards
from common.durations import format_duration, parse_duration
from common.textutil import normalize_text

_lock = threading.Lock()
_timers: list[dict] = []


def add(seconds: int, kind: str = "timer", label: str = "") -> dict:
    timer = {
        "id": uuid.uuid4().hex,
        "end": time.time() + seconds,
        "duration": seconds,
        "kind": kind,
        "label": label,
    }
    with _lock:
        _timers.append(timer)
    return _public(timer)


def cancel(timer_id: str) -> bool:
    with _lock:
        before = len(_timers)
        _timers[:] = [t for t in _timers if t["id"] != timer_id]
        return len(_timers) < before


def cancel_all() -> int:
    with _lock:
        n = len(_timers)
        _timers.clear()
    return n


def _public(t: dict) -> dict:
    return {**t, "remaining": max(0, int(t["end"] - time.time()))}


def list_active() -> list[dict]:
    with _lock:
        return [_public(t) for t in sorted(_timers, key=lambda t: t["end"])]


def _pop_due() -> list[dict]:
    with _lock:
        now = time.time()
        due = [t for t in _timers if t["end"] <= now]
        _timers[:] = [t for t in _timers if t["end"] > now]
        return due


def _announce_due(t: dict) -> None:
    if t["kind"] == "reminder" and t["label"]:
        title = "Rappel"
        subtitle = t["label"]
    else:
        title = "Minuteur écoulé"
        subtitle = format_duration(t["duration"])
    cards.emit("timer", title, {"kind": t["kind"], "label": t["label"], "duration": t["duration"]}, subtitle)


def _loop() -> None:
    while True:
        time.sleep(0.5)
        for t in _pop_due():
            _announce_due(t)


_started = False


def start() -> None:
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_loop, daemon=True).start()


# ── Routage texte (chat/voix via /ws/chat) ────────────────────────────────────
# Même cascade que agents/desktop/services/timers.py::handle, volontairement
# dupliquée plutôt que partagée : les deux gèrent des listes de minuteurs
# différentes (locale au poste vs brain) — mutualiser le *routage* sans
# mutualiser l'état aurait plus centralisé de logique qu'inutile.
_TIMER_WORDS = ("minuteur", "minuterie", "timer", "compte a rebours")
_REMIND_RE = re.compile(
    r"rappelle[- ]?(?:moi|toi)\s*(?:de |d')?(.*?)(?:\s+dans\s+(.+))?$")


def handle(question: str) -> Optional[str]:
    """Retourne la réponse à renvoyer si la phrase concerne les minuteurs
    brain, None sinon (la conversation normale continue)."""
    q = normalize_text(question)
    has_timer_word = any(w in q for w in _TIMER_WORDS)
    has_remind = "rappelle" in q and ("moi" in q or "toi" in q)

    if not has_timer_word and not has_remind:
        return None

    if has_timer_word and any(w in q for w in ("annule", "supprime", "arrete", "stoppe", "enleve")):
        n = cancel_all()
        if n == 0:
            return "Aucun minuteur n'était actif, Monsieur."
        return "Minuteur annulé, Monsieur." if n == 1 else f"Les {n} minuteurs sont annulés, Monsieur."

    if has_timer_word and ("reste" in q or "restant" in q):
        active = list_active()
        if not active:
            return "Aucun minuteur actif, Monsieur."
        return f"Il reste {format_duration(active[0]['remaining'])}, Monsieur."

    if has_remind:
        m = _REMIND_RE.search(q)
        seconds = parse_duration(q)
        if not seconds:
            return "Précisez la durée du rappel, Monsieur — par exemple : dans dix minutes."
        label = ""
        if m and m.group(1):
            label = re.sub(r"dans\s+.*$", "", m.group(1).strip()).strip(" ,.")
        add(seconds, "reminder", label)
        return f"Rappel programmé dans {format_duration(seconds)}, Monsieur."

    seconds = parse_duration(q)
    if not seconds:
        return "Précisez la durée, Monsieur — par exemple : minuteur cinq minutes."
    add(seconds, "timer", "")
    return f"Minuteur de {format_duration(seconds)} lancé, Monsieur."

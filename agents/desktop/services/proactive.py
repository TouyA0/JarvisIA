"""Proactivité (F5/F6 de docs/ROADMAP.md) — Jarvis qui parle SANS qu'on lui
demande : alertes système (disque/RAM/batterie), suggestion de coucher
tardif, briefing matinal (heure, météo, agenda, mails non lus).

Volontairement un thread séparé de agents/desktop/services/diagnostics.py
(qui échantillonne toutes les 2s pour le HUD) plutôt que greffé dessus :
les seuils proactifs n'ont besoin d'être vérifiés qu'une fois par minute,
et coupler les deux aurait risqué de perturber un panneau HUD qui
fonctionne déjà.

Chaque règle a son propre cooldown, mémorisé sur disque
(data/proactive_state.json) pour survivre à un redémarrage — sans ça,
relancer Jarvis à 23h35 répéterait la suggestion de coucher qu'il venait
tout juste de faire à 23h30.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Callable

from agents.desktop import config, state

_CHECK_INTERVAL_S = 60
_STATE_FILE = config.DATA_DIR / "proactive_state.json"
_lock = threading.Lock()

_say: Callable[[str], None] | None = None
_log: Callable[[str], None] | None = None


def _load_state() -> dict:
    if _STATE_FILE.exists():
        try:
            with open(_STATE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def _save_state(data: dict) -> None:
    try:
        with open(_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def _today() -> str:
    return time.strftime("%Y-%m-%d")


def _once_per_day(rule: str) -> bool:
    """True si `rule` n'a pas encore été déclenchée aujourd'hui — et
    l'enregistre comme faite dans la foulée (appelant doit annoncer juste
    après, pas avant, mais le risque d'un doublon sur une fenêtre d'une
    minute est négligeable ici)."""
    with _lock:
        data = _load_state()
        if data.get(rule) == _today():
            return False
        data[rule] = _today()
        _save_state(data)
        return True


def _cooldown_ok(rule: str, seconds: float) -> bool:
    """True si `rule` n'a pas été déclenchée depuis au moins `seconds` —
    pour les seuils système (disque/RAM) qui peuvent légitimement se
    reproduire plusieurs fois par jour, contrairement au coucher/briefing."""
    with _lock:
        data = _load_state()
        last = data.get(rule, 0)
        if time.time() - last < seconds:
            return False
        data[rule] = time.time()
        _save_state(data)
        return True


def _announce(text: str) -> None:
    """Attend que Jarvis se taise avant de parler par-dessus lui — même
    principe que timers.py::_wait_for_quiet, pour ne jamais couper une
    réponse en cours avec une alerte spontanée."""
    deadline = time.time() + 90
    while time.time() < deadline and (state.is_speaking or state.is_busy):
        time.sleep(0.5)
    if _log:
        _log(text)
    if _say:
        _say(text)


# ── Alertes système ───────────────────────────────────────────────────────────
def _check_system() -> None:
    try:
        import psutil
    except ImportError:
        return

    try:
        disk = psutil.disk_usage("C:\\").percent
        if disk >= config.PROACTIVE_DISK_THRESHOLD and _cooldown_ok("disk", 2 * 3600):
            _announce(f"Votre disque C est presque plein, Monsieur — {int(disk)} pour cent d'occupation.")
    except Exception:
        pass

    try:
        mem = psutil.virtual_memory().percent
        if mem >= config.PROACTIVE_RAM_THRESHOLD and _cooldown_ok("ram", 3600):
            _announce(f"La mémoire vive est saturée, Monsieur — {int(mem)} pour cent d'utilisation.")
    except Exception:
        pass

    try:
        battery = psutil.sensors_battery()
        if battery and not battery.power_plugged and battery.percent <= 15 and _cooldown_ok("battery", 1800):
            _announce(f"Batterie faible, Monsieur — {int(battery.percent)} pour cent restant.")
    except Exception:
        pass  # pas de batterie (PC fixe) : sensors_battery() renvoie None, rien à faire


# ── Coucher tardif ────────────────────────────────────────────────────────────
def _check_bedtime() -> None:
    now = time.localtime()
    target = (config.PROACTIVE_BEDTIME_HOUR, config.PROACTIVE_BEDTIME_MINUTE)
    if (now.tm_hour, now.tm_min) < target:
        return
    if now.tm_hour > target[0] or (now.tm_hour == target[0] and now.tm_min > target[1] + 5):
        return  # fenêtre d'une poignée de minutes après l'heure cible, pas toute la nuit
    if _once_per_day("bedtime"):
        _announce(f"Il est {now.tm_hour} heures {now.tm_min:02d}, Monsieur. Puis-je suggérer le repos ?")


# ── Briefing matinal ──────────────────────────────────────────────────────────
def _briefing_agenda() -> str | None:
    """None si Calendar n'est pas connecté (silence plutôt qu'une erreur
    dans le briefing) — sinon une phrase résumant les événements du jour."""
    from brain.integrations import google_calendar, store

    if not store.list_public("google_calendar"):
        return None
    time_min, time_max = google_calendar.range_for("today")
    events = google_calendar.list_events(time_min, time_max)
    if not events:
        return "Rien de prévu à l'agenda aujourd'hui."
    parts = []
    for e in events[:4]:
        when = e["start"][11:16] if not e["all_day"] and e["start"] and "T" in e["start"] else "toute la journée"
        parts.append(f"{e['summary']} à {when}" if when != "toute la journée" else f"{e['summary']} ({when})")
    more = f", et {len(events) - 4} de plus" if len(events) > 4 else ""
    return f"À l'agenda aujourd'hui : {', puis '.join(parts)}{more}."


def _briefing_mail() -> str | None:
    """None si Gmail n'est pas connecté, ou si la boîte est vide (pas
    besoin d'annoncer « zéro mail », ce n'est pas une information utile)."""
    from brain.integrations import google_gmail, store

    if not store.list_public("gmail"):
        return None
    messages = google_gmail.search("is:unread", limit=20)
    if not messages or "error" in (messages[0] if messages else {}):
        return None
    n = len(messages)
    return f"{n} mail{'s' if n > 1 else ''} non lu{'s' if n > 1 else ''}."


def _check_briefing() -> None:
    now = time.localtime()
    target = (config.PROACTIVE_BRIEFING_HOUR, config.PROACTIVE_BRIEFING_MINUTE)
    if (now.tm_hour, now.tm_min) < target:
        return
    if now.tm_hour > target[0] or (now.tm_hour == target[0] and now.tm_min > target[1] + 5):
        return
    if not _once_per_day("briefing"):
        return

    from agents.desktop.services import weather

    parts = [f"Il est {now.tm_hour} heures {now.tm_min:02d}, Monsieur."]
    w = weather.answer()
    if w:
        parts.append(w)
    try:
        agenda = _briefing_agenda()
        if agenda:
            parts.append(agenda)
    except Exception as e:
        print(f"[Proactif] briefing agenda : {e}")
    try:
        mail = _briefing_mail()
        if mail:
            parts.append(mail)
    except Exception as e:
        print(f"[Proactif] briefing mail : {e}")

    _announce(" ".join(parts))


def _loop() -> None:
    while True:
        time.sleep(_CHECK_INTERVAL_S)
        if not config.PROACTIVE_ENABLED:
            continue
        try:
            _check_system()
            _check_bedtime()
            _check_briefing()
        except Exception as e:
            print(f"[Proactif] erreur de boucle : {e}")


def start(say: Callable[[str], None], log: Callable[[str], None] | None = None) -> None:
    global _say, _log
    _say = say
    _log = log
    if not config.PROACTIVE_ENABLED:
        print("[Proactif] désactivé (PROACTIVE_ENABLED=0)")
        return
    threading.Thread(target=_loop, daemon=True).start()

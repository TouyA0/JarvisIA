"""Proactivité (C3) — alertes système, coucher tardif, briefing matinal,
poussés à TOUTES les Consoles (carte + notification navigateur), pas
seulement annoncés à voix haute sur le PC fixe.

Duplique volontairement la logique de seuils/cooldowns de
agents/desktop/services/proactive.py plutôt que de la lui retirer : le
desktop garde sa propre boucle pour continuer à *parler* de façon fiable,
sans dépendre du réseau brain. Les deux partagent le même fichier d'état
(data/proactive_state.json) : si le desktop a déjà annoncé une alerte à
voix haute, ce module la voit en cooldown et ne la republie pas en double
sous forme de carte quelques secondes plus tard.
"""
from __future__ import annotations

import json
import threading
import time

from brain import cards, config

_CHECK_INTERVAL_S = 60
_STATE_FILE = config.DATA_DIR / "proactive_state.json"
_lock = threading.Lock()


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
    with _lock:
        data = _load_state()
        if data.get(rule) == _today():
            return False
        data[rule] = _today()
        _save_state(data)
        return True


def _cooldown_ok(rule: str, seconds: float) -> bool:
    with _lock:
        data = _load_state()
        last = data.get(rule, 0)
        if time.time() - last < seconds:
            return False
        data[rule] = time.time()
        _save_state(data)
        return True


def _announce(title: str, text: str) -> None:
    cards.emit("proactive", title, {"text": text}, text)


# ── Alertes système ────────────────────────────────────────────────────────
def _is_windows() -> bool:
    import platform
    return platform.system() == "Windows"


def _check_system() -> None:
    try:
        import psutil
    except ImportError:
        return

    try:
        disk = psutil.disk_usage("C:\\" if _is_windows() else "/").percent
        if disk >= config.PROACTIVE_DISK_THRESHOLD and _cooldown_ok("disk", 2 * 3600):
            _announce("Disque presque plein", f"{int(disk)}% d'occupation sur le disque système, Monsieur.")
    except Exception:
        pass

    try:
        mem = psutil.virtual_memory().percent
        if mem >= config.PROACTIVE_RAM_THRESHOLD and _cooldown_ok("ram", 3600):
            _announce("Mémoire saturée", f"{int(mem)}% d'utilisation de la RAM, Monsieur.")
    except Exception:
        pass

    try:
        battery = psutil.sensors_battery()
        if battery and not battery.power_plugged and battery.percent <= 15 and _cooldown_ok("battery", 1800):
            _announce("Batterie faible", f"{int(battery.percent)}% restant, Monsieur.")
    except Exception:
        pass  # pas de batterie (PC fixe) : sensors_battery() renvoie None


# ── Coucher tardif ────────────────────────────────────────────────────────
def _check_bedtime() -> None:
    now = time.localtime()
    target = (config.PROACTIVE_BEDTIME_HOUR, config.PROACTIVE_BEDTIME_MINUTE)
    if (now.tm_hour, now.tm_min) < target:
        return
    if now.tm_hour > target[0] or (now.tm_hour == target[0] and now.tm_min > target[1] + 5):
        return  # fenêtre d'une poignée de minutes après l'heure cible
    if _once_per_day("bedtime"):
        _announce("Suggestion", f"Il est {now.tm_hour} heures {now.tm_min:02d}, Monsieur. Puis-je suggérer le repos ?")


# ── Briefing matinal ──────────────────────────────────────────────────────
def _briefing_agenda() -> str | None:
    from brain.integrations import google_calendar, store

    if not store.list_public(google_calendar.SERVICE_TYPE):
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
    from brain.integrations import google_gmail, store

    if not store.list_public(google_gmail.SERVICE_TYPE):
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

    from brain import weather

    parts = [f"Il est {now.tm_hour} heures {now.tm_min:02d}, Monsieur."]
    w = weather.get()
    if w and w["temp"] is not None:
        parts.append(f"Il fait {round(w['temp'])} degrés à {config.WEATHER_CITY}, {weather.description(w['code'])}.")
    try:
        agenda = _briefing_agenda()
        if agenda:
            parts.append(agenda)
    except Exception as e:
        print(f"[brain][proactif] briefing agenda : {e}")
    try:
        mail = _briefing_mail()
        if mail:
            parts.append(mail)
    except Exception as e:
        print(f"[brain][proactif] briefing mail : {e}")

    _announce("Briefing du matin", " ".join(parts))


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
            print(f"[brain][proactif] erreur de boucle : {e}")


_started = False


def start() -> None:
    global _started
    if _started:
        return
    _started = True
    if not config.PROACTIVE_ENABLED:
        print("[brain][proactif] désactivé (PROACTIVE_ENABLED=0)")
        return
    threading.Thread(target=_loop, daemon=True).start()

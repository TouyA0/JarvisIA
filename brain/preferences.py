"""Réglages généraux éditables depuis la Console web (C6 / F26 de la
roadmap) — jusqu'ici uniquement dans `.env`, à éditer et redémarrer le
brain pour voir l'effet.

Ne couvre que ce qui a un sens depuis N'IMPORTE QUEL appareil (ville
météo, seuils et horaires de la proactivité, C3) — pas les réglages voix/
seuils barge-in/hotkeys de agents/desktop, propres au poste physique et
sans signification depuis un téléphone.

Même mécanique que brain/integrations/settings.py (JSON local, priorité
au réglage saisi sur la valeur .env) mais hors du dossier integrations/ :
rien ici n'est lié à un compte tiers. Les valeurs .env (brain/config.py)
restent les valeurs par défaut ET le filet de secours si ce fichier est
vide ou incomplet.
"""
from __future__ import annotations

import json

from brain import config

_FILE = config.DATA_DIR / "preferences.json"


def _load() -> dict:
    if _FILE.exists():
        with open(_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save(data: dict) -> None:
    config.ensure_dirs()
    with open(_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── Météo ────────────────────────────────────────────────────────────────
def get_weather() -> dict:
    data = _load().get("weather", {})
    return {
        "city": data.get("city", config.WEATHER_CITY),
        "lat": data.get("lat", config.WEATHER_LAT),
        "lon": data.get("lon", config.WEATHER_LON),
    }


def set_weather(city: str, lat: float, lon: float) -> dict:
    data = _load()
    data["weather"] = {"city": city, "lat": lat, "lon": lon}
    _save(data)
    from brain import weather
    weather.clear_cache()  # sinon jusqu'à 30 min avant que le changement se voie
    return get_weather()


def clear_weather() -> dict:
    data = _load()
    data.pop("weather", None)
    _save(data)
    from brain import weather
    weather.clear_cache()
    return get_weather()


# ── Proactivité (C3) ─────────────────────────────────────────────────────
_PROACTIVE_DEFAULTS = {
    "enabled": lambda: config.PROACTIVE_ENABLED,
    "disk_threshold": lambda: config.PROACTIVE_DISK_THRESHOLD,
    "ram_threshold": lambda: config.PROACTIVE_RAM_THRESHOLD,
    "bedtime_hour": lambda: config.PROACTIVE_BEDTIME_HOUR,
    "bedtime_minute": lambda: config.PROACTIVE_BEDTIME_MINUTE,
    "briefing_hour": lambda: config.PROACTIVE_BRIEFING_HOUR,
    "briefing_minute": lambda: config.PROACTIVE_BRIEFING_MINUTE,
}


def get_proactive() -> dict:
    data = _load().get("proactive", {})
    return {k: data.get(k, default()) for k, default in _PROACTIVE_DEFAULTS.items()}


def set_proactive(values: dict) -> dict:
    data = _load()
    current = get_proactive()
    current.update({k: v for k, v in values.items() if k in _PROACTIVE_DEFAULTS and v is not None})
    data["proactive"] = current
    _save(data)
    return get_proactive()


def clear_proactive() -> dict:
    data = _load()
    data.pop("proactive", None)
    _save(data)
    return get_proactive()

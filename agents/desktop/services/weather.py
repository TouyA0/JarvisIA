"""Météo temps réel via Open-Meteo (gratuit, sans clé API).

Cache de 30 min : « quel temps fait-il » répond instantanément sans LLM,
et le HUD affiche la météo en permanence.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

import requests

from agents.desktop import config

# Codes WMO → description française
_WMO = {
    0: "ciel dégagé", 1: "plutôt dégagé", 2: "partiellement nuageux", 3: "couvert",
    45: "brouillard", 48: "brouillard givrant",
    51: "bruine légère", 53: "bruine", 55: "bruine dense",
    61: "pluie légère", 63: "pluie", 65: "pluie forte",
    66: "pluie verglaçante", 67: "pluie verglaçante forte",
    71: "neige légère", 73: "neige", 75: "neige forte", 77: "grésil",
    80: "averses légères", 81: "averses", 82: "averses violentes",
    85: "averses de neige", 86: "averses de neige fortes",
    95: "orage", 96: "orage avec grêle", 99: "orage avec grêle forte",
}

_cache = {"at": 0.0, "temp": None, "code": None, "wind": None}
_lock = threading.Lock()

_WEATHER_KEYWORDS = ("meteo", "quel temps", "temperature dehors", "il fait combien",
                     "fait-il beau", "fait beau", "va-t-il pleuvoir", "va pleuvoir")


def is_weather_question(normalized_q: str) -> bool:
    return any(kw in normalized_q for kw in _WEATHER_KEYWORDS)


def _fetch() -> bool:
    try:
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": config.WEATHER_LAT,
                "longitude": config.WEATHER_LON,
                "current": "temperature_2m,weather_code,wind_speed_10m",
            },
            timeout=6,
        )
        if resp.status_code != 200:
            return False
        cur = resp.json().get("current", {})
        with _lock:
            _cache["at"] = time.time()
            _cache["temp"] = cur.get("temperature_2m")
            _cache["code"] = cur.get("weather_code")
            _cache["wind"] = cur.get("wind_speed_10m")
        return True
    except Exception as e:
        print(f"[Météo] erreur : {e}")
        return False


def get(max_age_s: float = config.WEATHER_REFRESH_MINUTES * 60) -> dict | None:
    """Retourne la météo courante (du cache, rafraîchi si trop vieux)."""
    with _lock:
        fresh = time.time() - _cache["at"] < max_age_s and _cache["temp"] is not None
    if not fresh and not _fetch():
        with _lock:
            return dict(_cache) if _cache["temp"] is not None else None
    with _lock:
        return dict(_cache)


def answer() -> str:
    """Réponse vocale style Jarvis."""
    w = get()
    if not w or w["temp"] is None:
        return "Les données météo ne sont pas disponibles pour l'instant, Monsieur."
    desc = _WMO.get(w["code"], "conditions indéterminées")
    return (f"Il fait {round(w['temp'])} degrés à {config.WEATHER_CITY}, "
            f"{desc}, Monsieur.")


def short() -> str:
    """Version courte pour le HUD, ex: « 21° PLUTÔT DÉGAGÉ »."""
    w = get(max_age_s=float("inf"))  # jamais bloquant : dernière valeur connue
    if not w or w["temp"] is None:
        return ""
    desc = _WMO.get(w["code"], "")
    return f"{round(w['temp'])}° {desc.upper()}"


def start_refresher(on_update: Optional[Callable[[str], None]] = None) -> None:
    """Thread d'arrière-plan : rafraîchit la météo et pousse la version courte
    vers le HUD."""
    def _loop():
        while True:
            if _fetch() and on_update:
                try:
                    on_update(short())
                except Exception:
                    pass
            time.sleep(config.WEATHER_REFRESH_MINUTES * 60)

    threading.Thread(target=_loop, daemon=True).start()

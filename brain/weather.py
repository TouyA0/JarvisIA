"""Météo côté brain — Open-Meteo, sans clé, cache 30 min. Duplique
volontairement agents/desktop/services/weather.py plutôt que d'en dépendre
(le brain doit pouvoir tourner sans le package agent desktop) : même API,
même fournisseur, juste rappelée ici pour la carte "weather" (voir
docs/ROADMAP_DISPLAY_INTEGRATIONS.md §2.2, item resté non fait jusqu'ici).
"""
from __future__ import annotations

import threading
import time

import requests

from brain import config, preferences

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
_REFRESH_S = 30 * 60


def get() -> dict | None:
    with _lock:
        fresh = time.time() - _cache["at"] < _REFRESH_S and _cache["temp"] is not None
        if fresh:
            return dict(_cache)

    loc = preferences.get_weather()
    try:
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": loc["lat"],
                "longitude": loc["lon"],
                "current": "temperature_2m,weather_code,wind_speed_10m",
            },
            timeout=6,
        )
        resp.raise_for_status()
        cur = resp.json().get("current", {})
        with _lock:
            _cache.update(at=time.time(), temp=cur.get("temperature_2m"),
                          code=cur.get("weather_code"), wind=cur.get("wind_speed_10m"))
            return dict(_cache)
    except Exception as exc:
        with _lock:
            if _cache["temp"] is not None:
                return dict(_cache)  # dernière valeur connue plutôt que rien
        print(f"[brain][weather] {exc}")
        return None


def description(code: int | None) -> str:
    return _WMO.get(code, "conditions indéterminées")


def clear_cache() -> None:
    """Force un rafraîchissement au prochain get() — appelé après un
    changement de ville/coordonnées (brain/preferences.py::set_weather),
    sinon jusqu'à 30 min avant que le changement se voie."""
    with _lock:
        _cache.update(at=0.0, temp=None, code=None, wind=None)

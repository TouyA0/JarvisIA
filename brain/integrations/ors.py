"""Intégration OpenRouteService (openrouteservice.org, basé OpenStreetMap)
— alternative gratuite à Google Maps, écarté pour son exigence de carte
bancaire (voir docs/ROADMAP_DISPLAY_INTEGRATIONS.md). Clé API simple, pas
d'OAuth, pas de facturation.

Pas de notion de "compte" à connecter (contrairement à Tisséo/Jellyfin) :
un calcul d'itinéraire ne se rattache à rien de persistant, la clé globale
(settings.py) suffit à chaque appel — pas de store.py ici.

Deux appels par itinéraire : geocode() convertit une adresse en
coordonnées (Pelias/OpenStreetMap), directions() calcule le trajet entre
deux points. Moins précis que Google sur le trafic temps réel, largement
suffisant pour "combien de temps pour aller à X".
"""
from __future__ import annotations

from brain.integrations import settings

import requests

# api.openrouteservice.org déprécié depuis le 28/04/2026 au profit de la
# structure unifiée HeiGIT "api.heigit.org/<service>/<version>/" — pas
# juste un changement de domaine. Vérifié en pratique (sondes HTTP réelles,
# 401 = chemin correct/clé manquante vs 404 = mauvais chemin), pas deviné :
# les itinéraires restent sous /openrouteservice/, mais le géocodage
# (Pelias) a son propre namespace séparé /pelias/, pas sous /openrouteservice/.
API_BASE = "https://api.heigit.org/openrouteservice"
GEOCODE_BASE = "https://api.heigit.org/pelias/v1"

_PROFILES = {
    "voiture": "driving-car",
    "vélo": "cycling-regular",
    "velo": "cycling-regular",
    "à pied": "foot-walking",
    "a pied": "foot-walking",
    "marche": "foot-walking",
}


def configured() -> bool:
    return bool(settings.get_ors_api_key())


def resolve_profile(mode: str | None) -> str:
    return _PROFILES.get((mode or "voiture").lower(), "driving-car")


def geocode(address: str) -> dict | None:
    """Coordonnées + libellé pour une adresse en texte libre. None si rien
    trouvé (adresse trop vague, faute de frappe...)."""
    api_key = settings.get_ors_api_key()
    try:
        resp = requests.get(
            f"{GEOCODE_BASE}/search",
            params={"api_key": api_key, "text": address, "size": 1},
            timeout=10,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Service de géocodage injoignable : {exc}")
    if resp.status_code != 200:
        raise RuntimeError(f"Géocodage refusé par OpenRouteService ({resp.status_code}) : {resp.text[:300]}")
    features = resp.json().get("features", [])
    if not features:
        return None
    feat = features[0]
    lon, lat = feat["geometry"]["coordinates"]
    return {"lon": lon, "lat": lat, "label": feat.get("properties", {}).get("label", address)}


def directions(origin: str | None, destination: str, mode: str | None = None) -> dict:
    """Distance + durée entre deux adresses en texte libre. Résout chaque
    adresse via geocode() avant d'appeler l'API d'itinéraire — deux appels
    réseau, mais évite d'exiger des coordonnées de la part de Monsieur.

    `origin` vide/absent → adresse domicile configurée (settings.py), s'il
    y en a une ; sinon erreur explicite plutôt que de deviner un point de
    départ arbitraire."""
    if not configured():
        return {"error": "OpenRouteService n'est pas configuré, Monsieur — aucune clé API renseignée."}

    if not origin:
        origin = settings.get_home_address()
        if not origin:
            return {"error": "Aucune adresse de départ donnée, et aucune adresse domicile enregistrée, Monsieur — précise l'une ou l'autre."}

    profile = resolve_profile(mode)
    try:
        origin_point = geocode(origin)
        if not origin_point:
            return {"error": f"Adresse de départ introuvable : « {origin} », Monsieur."}
        dest_point = geocode(destination)
        if not dest_point:
            return {"error": f"Adresse d'arrivée introuvable : « {destination} », Monsieur."}
    except RuntimeError as exc:
        return {"error": str(exc)}

    api_key = settings.get_ors_api_key()
    try:
        resp = requests.get(
            f"{API_BASE}/v2/directions/{profile}",
            params={
                "api_key": api_key,
                "start": f"{origin_point['lon']},{origin_point['lat']}",
                "end": f"{dest_point['lon']},{dest_point['lat']}",
            },
            timeout=15,
        )
    except requests.RequestException as exc:
        return {"error": f"Service d'itinéraire injoignable : {exc}"}
    if resp.status_code != 200:
        return {"error": f"Itinéraire refusé par OpenRouteService ({resp.status_code}) : {resp.text[:300]}"}
    data = resp.json()
    features = data.get("features", [])
    if not features:
        return {"error": f"Aucun itinéraire trouvé entre « {origin} » et « {destination} », Monsieur."}
    summary = features[0]["properties"]["summary"]
    return {
        "origin": origin_point["label"],
        "destination": dest_point["label"],
        "distance_km": round(summary["distance"] / 1000, 1),
        "duration_min": round(summary["duration"] / 60),
        "mode": mode or "voiture",
    }

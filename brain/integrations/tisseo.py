"""Intégration Tisséo (transports en commun Toulouse) — API publique
gratuite (data.tisseo.fr), authentification par clé simple, pas d'OAuth,
pas de facturation (contrairement à Google Maps, envisagé puis écarté pour
cette raison).

Pas de notion de "compte" ici — la clé API est globale (settings.py), les
"comptes" stockés via store.py représentent en réalité des ARRÊTS FAVORIS
enregistrés (label = nom de l'arrêt) : plusieurs favoris possibles (arrêt
domicile, arrêt travail…), fusionnés automatiquement au listing des
prochains passages, même modèle que les comptes Calendar/Drive.

Confiance sur les endpoints : MODÉRÉE — l'API Tisséo est beaucoup moins
documentée dans ce que je connais que Google/Spotify. Implémenté avec ma
meilleure connaissance ; chaque erreur HTTP renvoie le corps brut de la
réponse pour corriger vite si un nom de paramètre est faux.
"""
from __future__ import annotations

import requests

from brain.integrations import settings, store

SERVICE_TYPE = "tisseo"
API_BASE = "https://api.tisseo.fr/v2"


def configured() -> bool:
    return bool(settings.get_tisseo_api_key())


def search_stops(query: str, limit: int = 5) -> list[dict]:
    """Cherche un arrêt par nom — utilisé à la fois pour connect() et pour
    aider Monsieur à choisir s'il y a ambiguïté (plusieurs "Jean Jaurès" par
    exemple)."""
    api_key = settings.get_tisseo_api_key()
    if not api_key:
        raise RuntimeError("Clé API Tisséo manquante — voir Paramètres Tisséo dans la Console.")
    resp = requests.get(
        f"{API_BASE}/stops_areas.json",
        params={"key": api_key, "term": query, "format": "json"},
        timeout=10,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Recherche d'arrêt refusée par Tisséo ({resp.status_code}) : {resp.text[:300]}")
    data = resp.json()
    areas = data.get("stopAreas", data.get("stop_areas", []))
    results = []
    for a in areas[:limit]:
        results.append({
            "id": a.get("id") or a.get("stopAreaId"),
            "name": a.get("name", query),
            "city": a.get("cityName", ""),
        })
    return results


def connect(stop_query: str) -> dict:
    """Résout `stop_query` vers un arrêt Tisséo (premier résultat) et
    l'enregistre comme favori. Lève RuntimeError si rien ne correspond ou
    si l'API refuse."""
    matches = search_stops(stop_query, limit=1)
    if not matches:
        raise RuntimeError(f"Aucun arrêt trouvé pour « {stop_query} », Monsieur — vérifie l'orthographe.")
    stop = matches[0]
    label = f"{stop['name']} ({stop['city']})" if stop.get("city") else stop["name"]
    return store.add(SERVICE_TYPE, label, stop["id"], {"stop_area_id": stop["id"]})


def _next_for_stop(account: dict, limit: int) -> list[dict]:
    api_key = settings.get_tisseo_api_key()
    stop_area_id = account.get("extra", {}).get("stop_area_id")
    resp = requests.get(
        f"{API_BASE}/stops_schedules.json",
        params={"key": api_key, "stopAreaId": stop_area_id, "number": limit, "format": "json"},
        timeout=10,
    )
    if resp.status_code != 200:
        return [{"stop": account["label"], "error": f"{resp.status_code} : {resp.text[:200]}"}]
    data = resp.json()
    departures = []
    for dep in data.get("departures", []):
        journey = dep.get("journey", dep)
        departures.append({
            "stop": account["label"],
            "line": journey.get("line", {}).get("shortName", journey.get("line", "")),
            "destination": journey.get("destination", ""),
            "datetime": dep.get("dateTime", journey.get("dateTime", "")),
            "waiting": dep.get("waiting", ""),
        })
    return departures


def next_departures(account_hint: str | None = None, limit: int = 5) -> list[dict]:
    """Prochains passages pour tous les arrêts favoris enregistrés (ou un
    seul si account_hint filtre par nom), fusionnés. Un arrêt en erreur
    n'empêche pas les autres."""
    accounts = store.list_for(SERVICE_TYPE)
    if account_hint:
        accounts = [a for a in accounts if account_hint.lower() in a["label"].lower()] or accounts
    if not accounts:
        return [{"error": "Aucun arrêt favori enregistré, Monsieur — ajoute-en un depuis la Console (Intégrations)."}]

    all_departures: list[dict] = []
    for account in accounts:
        all_departures.extend(_next_for_stop(account, limit))
    return all_departures

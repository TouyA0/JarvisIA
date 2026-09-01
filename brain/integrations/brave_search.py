"""Recherche web + lecture d'article — F2 de docs/ROADMAP.md, le manque le
plus cité par Monsieur (« Jarvis, cherche… »). API Brave Search : clé
simple, gratuite (2000 requêtes/mois), pas d'OAuth, pas de facturation —
même mécanique que Tisséo/OpenRouteService.

Deux outils distincts et complémentaires (voir brain/tools.py) :
  - search()     → titres/liens/extraits, pour une réponse rapide ou pour
                    choisir quelle page approfondir.
  - fetch_page()  → texte complet et nettoyé d'UNE page (via trafilatura :
                    retire nav/pubs/scripts, ne garde que l'article), pour
                    « résume-moi cette page/cet article ».
"""
from __future__ import annotations

import requests

from brain.integrations import settings

API_URL = "https://api.search.brave.com/res/v1/web/search"


def configured() -> bool:
    return bool(settings.get_brave_api_key())


def search(query: str, count: int = 5) -> list[dict]:
    api_key = settings.get_brave_api_key()
    try:
        resp = requests.get(
            API_URL,
            headers={"Accept": "application/json", "X-Subscription-Token": api_key},
            params={"q": query, "count": count},
            timeout=10,
        )
    except requests.RequestException as exc:
        return [{"error": f"Service de recherche injoignable : {exc}"}]
    if resp.status_code != 200:
        return [{"error": f"Recherche refusée par Brave ({resp.status_code}) : {resp.text[:300]}"}]
    results = []
    for item in resp.json().get("web", {}).get("results", [])[:count]:
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("description", ""),
        })
    return results


def fetch_page(url: str, max_chars: int = 8000) -> dict:
    """Texte principal d'une page web, débarrassé de la navigation/pubs.
    {"error": "..."} si la page est injoignable ou que rien d'exploitable
    n'a pu en être extrait (page purement en JavaScript, PDF, paywall...)."""
    import trafilatura

    try:
        downloaded = trafilatura.fetch_url(url)
    except Exception as exc:
        return {"error": f"Page injoignable : {exc}"}
    if not downloaded:
        return {"error": f"Impossible de récupérer « {url} », Monsieur — vérifie l'adresse."}

    text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
    if not text or not text.strip():
        return {"error": f"Aucun contenu texte exploitable trouvé sur « {url} », Monsieur (page dynamique, PDF, ou protégée)."}

    return {"text": text[:max_chars], "truncated": len(text) > max_chars}

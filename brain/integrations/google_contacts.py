"""Intégration Google Contacts (People API) — même schéma que
google_calendar.py, mécanique OAuth partagée via google_oauth.py.

Scope demandé : contacts.readonly — lecture seule, aucun outil d'écriture
(créer/modifier un contact n'a pas d'usage identifié pour l'instant, pas de
raison d'élargir le scope sans besoin réel).

Recherche par filtrage LOCAL (tous les contacts rapatriés une fois par
appel, puis filtre en mémoire) plutôt que via l'endpoint people:searchContacts
de Google : ce dernier s'appuie sur un index qui met du retard à jour après
l'ajout d'un contact ("warm-up" documenté par Google) — pour une poignée de
centaines de contacts personnels, une liste + filtre local est plus simple
et plus prévisible qu'un index parfois en retard.
"""
from __future__ import annotations

import requests

from brain.integrations import google_oauth, store

SERVICE_TYPE = "google_contacts"
# contacts.readonly seul suffit pour lire les contacts (connections) mais
# PAS pour lire le profil du compte connecté lui-même (people/me) — Google
# le classe à part, sous userinfo.email. Sans ce 2e scope, people/me renvoie
# 403 (constaté en pratique) alors même que l'API est bien activée et la
# recherche de contacts, elle, aurait fonctionné.
SCOPE = "https://www.googleapis.com/auth/contacts.readonly https://www.googleapis.com/auth/userinfo.email"
PEOPLE_API = "https://people.googleapis.com/v1"
_PERSON_FIELDS = "names,phoneNumbers,emailAddresses,organizations"


def configured() -> bool:
    return google_oauth.configured()


def build_auth_url() -> str:
    return google_oauth.build_auth_url(SERVICE_TYPE, SCOPE)


def _fetch_owner_label(access_token: str) -> str:
    # Endpoint OAuth2 générique (pas People API) : couvert par le scope
    # userinfo.email, indépendant de contacts.readonly — voir note SCOPE.
    resp = requests.get(
        "https://www.googleapis.com/oauth2/v3/userinfo",
        headers={"Authorization": f"Bearer {access_token}"}, timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("email") or data.get("name", "compte Google")


def handle_callback(code: str) -> dict:
    return google_oauth.handle_callback(SERVICE_TYPE, code, _fetch_owner_label)


def _parse_person(person: dict) -> dict:
    names = person.get("names", [])
    name = names[0].get("displayName", "(sans nom)") if names else "(sans nom)"
    phones = [p.get("value", "") for p in person.get("phoneNumbers", [])]
    emails = [e.get("value", "") for e in person.get("emailAddresses", [])]
    orgs = person.get("organizations", [])
    org = orgs[0].get("name", "") if orgs else ""
    return {"name": name, "phones": phones, "emails": emails, "organization": org}


def _fetch_all_connections(account: dict) -> list[dict]:
    access_token = google_oauth.access_token_for(account)
    people: list[dict] = []
    page_token = None
    # Deux pages (jusqu'à 2000 contacts) largement suffisant pour un usage
    # personnel — évite une boucle non bornée si un compte a un carnet
    # d'adresses anormalement énorme (professionnel, importé en masse…).
    for _ in range(2):
        params = {"personFields": _PERSON_FIELDS, "pageSize": 1000}
        if page_token:
            params["pageToken"] = page_token
        resp = requests.get(
            f"{PEOPLE_API}/people/me/connections",
            headers={"Authorization": f"Bearer {access_token}"}, params=params, timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        people.extend(data.get("connections", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return people


def search(query: str, account_id: str | None = None, limit: int = 5) -> list[dict]:
    """Contacts dont le nom contient `query` (insensible à la casse), tous
    comptes connectés confondus (ou un seul si account_id est donné). Un
    compte en erreur n'empêche pas les autres."""
    accounts = store.list_for(SERVICE_TYPE)
    if account_id:
        accounts = [a for a in accounts if a["id"] == account_id]

    q = query.lower()
    results: list[dict] = []
    for account in accounts:
        try:
            connections = _fetch_all_connections(account)
        except Exception as exc:
            results.append({"account": account["label"], "name": f"[erreur : {exc}]", "phones": [], "emails": [], "organization": ""})
            continue
        for person in connections:
            parsed = _parse_person(person)
            if q in parsed["name"].lower():
                parsed["account"] = account["label"]
                results.append(parsed)
                if len(results) >= limit:
                    return results
    return results

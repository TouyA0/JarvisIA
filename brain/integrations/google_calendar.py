"""Intégration Google Calendar — logique métier uniquement, la mécanique
OAuth commune (auth URL, échange de code, refresh) vit dans google_oauth.py
et est partagée avec google_drive.py.

Flux de connexion (déclenché depuis la Console web, voir Integrations.jsx) :
  1. GET /api/integrations/google/auth-url?service=google_calendar → URL de
     consentement Google, la Console l'ouvre dans un nouvel onglet.
  2. L'utilisateur choisit son compte Google et accepte.
  3. Google redirige vers GOOGLE_REDIRECT_URI (server.py::google_callback,
     exempté de l'auth Console — c'est Google qui l'appelle) avec un `code`.
  4. server.py route vers handle_callback() ci-dessous, qui échange le code,
     identifie le compte (email de l'agenda principal), le stocke chiffré.

Scope demandé : calendar.readonly — lecture seule, cohérent avec la
politique du projet (écriture toujours confirmée, voir docs/ROADMAP.md).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from brain import config
from brain.integrations import google_oauth, store

SERVICE_TYPE = "google_calendar"
SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
CALENDAR_API = "https://www.googleapis.com/calendar/v3"


def configured() -> bool:
    return google_oauth.configured()


def build_auth_url() -> str:
    return google_oauth.build_auth_url(SERVICE_TYPE, SCOPE)


def _fetch_primary_email(access_token: str) -> str:
    resp = requests.get(
        f"{CALENDAR_API}/calendars/primary", headers={"Authorization": f"Bearer {access_token}"}, timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("id", "compte Google")


def handle_callback(code: str) -> dict:
    return google_oauth.handle_callback(SERVICE_TYPE, code, _fetch_primary_email)


def _events_for_account(account: dict, time_min: datetime, time_max: datetime) -> list[dict]:
    access_token = google_oauth.access_token_for(account)
    resp = requests.get(
        f"{CALENDAR_API}/calendars/primary/events",
        headers={"Authorization": f"Bearer {access_token}"},
        params={
            "timeMin": time_min.isoformat(),
            "timeMax": time_max.isoformat(),
            "singleEvents": "true",
            "orderBy": "startTime",
            "maxResults": 50,
        },
        timeout=10,
    )
    resp.raise_for_status()
    events = []
    for item in resp.json().get("items", []):
        start = item.get("start", {})
        events.append({
            "account": account["label"],
            "summary": item.get("summary", "(sans titre)"),
            "start": start.get("dateTime") or start.get("date"),
            "all_day": "date" in start,
            "location": item.get("location"),
        })
    return events


def list_events(time_min: datetime, time_max: datetime, account_id: str | None = None) -> list[dict]:
    """Événements de tous les comptes connectés (ou un seul si account_id est
    donné) sur la période, fusionnés et triés chronologiquement. Un compte
    dont le jeton a expiré ne fait pas échouer les autres — son erreur est
    incluse dans un événement synthétique pour rester visible à l'agent."""
    accounts = store.list_for(SERVICE_TYPE)
    if account_id:
        accounts = [a for a in accounts if a["id"] == account_id]

    all_events: list[dict] = []
    for account in accounts:
        try:
            all_events.extend(_events_for_account(account, time_min, time_max))
        except Exception as exc:
            all_events.append({
                "account": account["label"], "summary": f"[erreur : {exc}]",
                "start": time_min.isoformat(), "all_day": True, "location": None,
            })
    all_events.sort(key=lambda e: e["start"] or "")
    return all_events


def range_for(name: str) -> tuple[datetime, datetime]:
    """Traduit un raccourci ('today'/'tomorrow'/'week') en bornes datetime,
    calculées dans le fuseau local (config.TIMEZONE) — un "aujourd'hui" en
    UTC ne correspond pas à la journée locale réelle, voir config.py."""
    now = datetime.now(ZoneInfo(config.TIMEZONE))
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if name == "tomorrow":
        start = start_of_today + timedelta(days=1)
        return start, start + timedelta(days=1)
    if name == "week":
        return start_of_today, start_of_today + timedelta(days=7)
    return start_of_today, start_of_today + timedelta(days=1)  # "today" par défaut

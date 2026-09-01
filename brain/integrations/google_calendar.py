"""Intégration Google Calendar — OAuth2 "à la main" (requests seul, pas de
google-api-python-client : trois appels REST suffisent, inutile d'ajouter
~4 dépendances lourdes pour ça). Comptes multiples supportés nativement
(chaque compte = une entrée dans brain/integrations/store.py).

Flux de connexion (déclenché depuis la Console web, voir Integrations.jsx) :
  1. GET /api/integrations/google/auth-url  → renvoie l'URL de consentement
     Google, la Console l'ouvre dans un nouvel onglet.
  2. L'utilisateur choisit son compte Google et accepte.
  3. Google redirige vers GOOGLE_REDIRECT_URI (ce process, exempté de l'auth
     Console — voir server.py) avec un `code`.
  4. Ce module échange le code contre un refresh_token, identifie le
     compte (email de l'agenda principal), le stocke chiffré.

Scope demandé : calendar.readonly — lecture seule, cohérent avec la
politique du projet (écriture toujours confirmée, voir docs/ROADMAP.md).
"""
from __future__ import annotations

import secrets
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

from brain import config
from brain.integrations import settings, store

SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
CALENDAR_API = "https://www.googleapis.com/calendar/v3"

_STATE_TTL = 5 * 60
_state_lock = threading.Lock()
_pending_states: dict[str, float] = {}  # state -> expiration (epoch)

# access_token de courte durée (1h côté Google) mis en cache par account_id
# pour éviter un refresh à chaque appel — même compte interrogé plusieurs
# fois d'affilée (ex: "aujourd'hui" puis "cette semaine").
_access_cache: dict[str, tuple[str, float]] = {}  # account_id -> (token, expiry)
_access_lock = threading.Lock()


def configured() -> bool:
    client_id, client_secret = settings.get_google_credentials()
    return bool(client_id and client_secret)


def build_auth_url() -> str:
    client_id, _ = settings.get_google_credentials()
    if not configured():
        raise RuntimeError(
            "Identifiants Google manquants — renseigne le Client ID / Client "
            "Secret dans la Console (Intégrations → Paramètres Google)."
        )
    state = secrets.token_urlsafe(24)
    with _state_lock:
        _expire_stale_states()
        _pending_states[state] = time.time() + _STATE_TTL
    params = {
        "client_id": client_id,
        "redirect_uri": config.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        # "consent" force Google à renvoyer un refresh_token même si ce
        # compte a déjà autorisé l'appli avant — sinon un second compte
        # google connecté après le premier n'en recevrait pas.
        "prompt": "consent",
        "state": state,
    }
    query = "&".join(f"{k}={requests.utils.quote(str(v), safe='')}" for k, v in params.items())
    return f"{AUTH_URL}?{query}"


def _expire_stale_states() -> None:
    now = time.time()
    for s in [s for s, exp in _pending_states.items() if exp <= now]:
        del _pending_states[s]


def _consume_state(state: str) -> bool:
    with _state_lock:
        expires_at = _pending_states.pop(state, None)
    return expires_at is not None and expires_at > time.time()


def handle_callback(code: str, state: str) -> dict:
    """Échange le code contre des jetons, identifie le compte, le stocke.
    Lève ValueError (state invalide/expiré) ou RuntimeError (échec Google)."""
    if not _consume_state(state):
        raise ValueError("état OAuth invalide ou expiré — relance la connexion depuis la Console")

    client_id, client_secret = settings.get_google_credentials()
    resp = requests.post(TOKEN_URL, data={
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": config.GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }, timeout=10)
    if resp.status_code != 200:
        raise RuntimeError(f"échange de code refusé par Google : {resp.text[:300]}")
    tokens = resp.json()
    refresh_token = tokens.get("refresh_token")
    access_token = tokens.get("access_token")
    if not refresh_token:
        # Arrive si ce compte Google avait déjà un refresh_token émis et que
        # prompt=consent n'a pas suffi (rare, mais Google le documente) —
        # message actionnable plutôt qu'un compte à moitié connecté.
        raise RuntimeError(
            "Google n'a pas renvoyé de jeton de rafraîchissement — "
            "révoque l'accès existant sur myaccount.google.com/permissions "
            "puis reconnecte ce compte."
        )

    label = _fetch_primary_email(access_token)
    return store.add("google_calendar", label, refresh_token)


def _fetch_primary_email(access_token: str) -> str:
    resp = requests.get(
        f"{CALENDAR_API}/calendars/primary", headers={"Authorization": f"Bearer {access_token}"}, timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("id", "compte Google")


def _access_token_for(account: dict) -> str:
    account_id = account["id"]
    with _access_lock:
        cached = _access_cache.get(account_id)
        if cached and cached[1] > time.time() + 30:
            return cached[0]

    client_id, client_secret = settings.get_google_credentials()
    resp = requests.post(TOKEN_URL, data={
        "refresh_token": account["refresh_token"],
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
    }, timeout=10)
    if resp.status_code != 200:
        raise RuntimeError(f"jeton {account['label']} expiré ou révoqué, reconnecte-le depuis la Console")
    tokens = resp.json()
    access_token = tokens["access_token"]
    expires_at = time.time() + tokens.get("expires_in", 3600)
    with _access_lock:
        _access_cache[account_id] = (access_token, expires_at)
    return access_token


def _events_for_account(account: dict, time_min: datetime, time_max: datetime) -> list[dict]:
    access_token = _access_token_for(account)
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
    accounts = store.list_for("google_calendar")
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

"""Mécanique OAuth2 Google commune à tous les services (Calendar, Drive,
Gmail…) — extrait de google_calendar.py au moment d'ajouter Drive : jusque
là dupliquer aurait été prématuré (une seule intégration), à partir de deux
ça ne l'est plus.

Un seul redirect_uri est enregistré côté Google Cloud Console
(GOOGLE_REDIRECT_URI, un seul callback possible) : le `state` généré par
build_auth_url encode donc aussi le service demandé, pour que le callback
partagé (server.py::google_callback) sache quoi faire du code reçu — voir
consume_state.

Chaque module `google_<service>.py` n'implémente plus que : son scope, sa
fonction de libellé (quel texte afficher pour identifier le compte), et sa
logique métier propre (list_events, search_files…).
"""
from __future__ import annotations

import secrets
import threading
import time

import requests

from brain import config
from brain.integrations import settings, store

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"

_STATE_TTL = 5 * 60
_state_lock = threading.Lock()
_pending_states: dict[str, tuple[float, str]] = {}  # state -> (expiration, service_type)

# access_token de courte durée (1h côté Google) mis en cache par account_id
# (uuid unique tous services confondus, pas de collision possible) pour
# éviter un refresh à chaque appel d'outil.
_access_cache: dict[str, tuple[str, float]] = {}  # account_id -> (token, expiry)
_access_lock = threading.Lock()


def configured() -> bool:
    client_id, client_secret = settings.get_google_credentials()
    return bool(client_id and client_secret)


def build_auth_url(service_type: str, scope: str) -> str:
    if not configured():
        raise RuntimeError(
            "Identifiants Google manquants — renseigne le Client ID / Client "
            "Secret dans la Console (Intégrations → Paramètres Google)."
        )
    client_id, _ = settings.get_google_credentials()
    state = secrets.token_urlsafe(24)
    with _state_lock:
        _expire_stale_states()
        _pending_states[state] = (time.time() + _STATE_TTL, service_type)
    params = {
        "client_id": client_id,
        "redirect_uri": config.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": scope,
        "access_type": "offline",
        # "consent" force Google à renvoyer un refresh_token même si ce
        # compte a déjà autorisé l'appli avant (pour un autre service, ou un
        # autre compte) — sinon une connexion suivante n'en recevrait pas.
        "prompt": "consent",
        "state": state,
    }
    query = "&".join(f"{k}={requests.utils.quote(str(v), safe='')}" for k, v in params.items())
    return f"{AUTH_URL}?{query}"


def _expire_stale_states() -> None:
    now = time.time()
    for s in [s for s, (exp, _) in _pending_states.items() if exp <= now]:
        del _pending_states[s]


def consume_state(state: str) -> str | None:
    """Retourne le service_type associé, ou None si le state est invalide/expiré."""
    with _state_lock:
        entry = _pending_states.pop(state, None)
    if entry is None:
        return None
    expires_at, service_type = entry
    return service_type if expires_at > time.time() else None


def exchange_code(code: str) -> dict:
    """Échange le code contre des jetons. Lève RuntimeError si Google refuse
    ou ne renvoie pas de refresh_token (reconnexion sans révocation préalable)."""
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
    if not tokens.get("refresh_token"):
        raise RuntimeError(
            "Google n'a pas renvoyé de jeton de rafraîchissement — "
            "révoque l'accès existant sur myaccount.google.com/permissions "
            "puis reconnecte ce compte."
        )
    return tokens


def access_token_for(account: dict) -> str:
    """Access token courant pour ce compte (cache mémoire, refresh à la
    demande) — même fonction pour tous les services, un compte Drive et un
    compte Calendar ont chacun leur propre refresh_token/account_id."""
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


def handle_callback(service_type: str, code: str, label_fetcher) -> dict:
    """Échange le code, identifie le compte via `label_fetcher(access_token)`,
    le stocke sous `service_type`. Commun à tous les modules google_*."""
    tokens = exchange_code(code)
    label = label_fetcher(tokens["access_token"])
    return store.add(service_type, label, tokens["refresh_token"])

"""Mécanique OAuth2 Spotify — module séparé de google_oauth.py/zoho_oauth.py
(identifiants et endpoints propres à Spotify), mais nettement plus simple
que Zoho : un seul domaine, pas de région à gérer.

Différence notable avec Google : Spotify authentifie l'échange de code et
le refresh via un header `Authorization: Basic base64(client_id:client_secret)`
plutôt que client_id/client_secret dans le corps de la requête — les deux
sont documentés côté Spotify, celui-ci est l'usage recommandé.
"""
from __future__ import annotations

import base64
import secrets
import threading
import time

import requests

from brain import config
from brain.integrations import settings, store

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"

_STATE_TTL = 5 * 60
_state_lock = threading.Lock()
_pending_states: dict[str, float] = {}  # state -> expiration (epoch)

_access_cache: dict[str, tuple[str, float]] = {}  # account_id -> (token, expiry)
_access_lock = threading.Lock()


def configured() -> bool:
    client_id, client_secret = settings.get_spotify_credentials()
    return bool(client_id and client_secret)


def _basic_auth_header() -> dict:
    client_id, client_secret = settings.get_spotify_credentials()
    raw = f"{client_id}:{client_secret}".encode("utf-8")
    return {"Authorization": f"Basic {base64.b64encode(raw).decode('ascii')}"}


def build_auth_url(scope: str) -> str:
    if not configured():
        raise RuntimeError(
            "Identifiants Spotify manquants — renseigne le Client ID / Client "
            "Secret dans la Console (Intégrations → Paramètres Spotify)."
        )
    client_id, _ = settings.get_spotify_credentials()
    state = secrets.token_urlsafe(24)
    with _state_lock:
        _expire_stale_states()
        _pending_states[state] = time.time() + _STATE_TTL
    params = {
        "client_id": client_id,
        "redirect_uri": config.SPOTIFY_REDIRECT_URI,
        "response_type": "code",
        "scope": scope,
        "state": state,
        # Spotify ne propose pas de refresh_token à un client déjà autorisé
        # sans repasser par l'écran de consentement — équivalent du
        # prompt=consent Google/Zoho, indispensable pour un 2e compte.
        "show_dialog": "true",
    }
    query = "&".join(f"{k}={requests.utils.quote(str(v), safe='')}" for k, v in params.items())
    return f"{AUTH_URL}?{query}"


def _expire_stale_states() -> None:
    now = time.time()
    for s in [s for s, exp in _pending_states.items() if exp <= now]:
        del _pending_states[s]


def consume_state(state: str) -> bool:
    with _state_lock:
        expires_at = _pending_states.pop(state, None)
    return expires_at is not None and expires_at > time.time()


def exchange_code(code: str) -> dict:
    resp = requests.post(
        TOKEN_URL, headers=_basic_auth_header(),
        data={"code": code, "redirect_uri": config.SPOTIFY_REDIRECT_URI, "grant_type": "authorization_code"},
        timeout=10,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"échange de code refusé par Spotify : {resp.text[:300]}")
    tokens = resp.json()
    if not tokens.get("refresh_token"):
        raise RuntimeError(
            "Spotify n'a pas renvoyé de jeton de rafraîchissement — "
            "révoque l'accès existant depuis spotify.com/account/apps "
            "puis reconnecte ce compte."
        )
    return tokens


def access_token_for(account: dict) -> str:
    account_id = account["id"]
    with _access_lock:
        cached = _access_cache.get(account_id)
        if cached and cached[1] > time.time() + 30:
            return cached[0]

    resp = requests.post(
        TOKEN_URL, headers=_basic_auth_header(),
        data={"refresh_token": account["refresh_token"], "grant_type": "refresh_token"},
        timeout=10,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"jeton {account['label']} expiré ou révoqué, reconnecte-le depuis la Console")
    tokens = resp.json()
    access_token = tokens["access_token"]
    expires_at = time.time() + tokens.get("expires_in", 3600)
    with _access_lock:
        _access_cache[account_id] = (access_token, expires_at)
    return access_token


def handle_callback(service_type: str, code: str, label_fetcher) -> dict:
    tokens = exchange_code(code)
    label = label_fetcher(tokens["access_token"])
    return store.add(service_type, label, tokens["refresh_token"])

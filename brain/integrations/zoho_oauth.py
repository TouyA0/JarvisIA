"""Mécanique OAuth2 Zoho — séparée de google_oauth.py, pas un simple copier-
coller adapté : Zoho isole ses comptes par datacenter régional (com/eu/in/
com.au/jp/ca), donc les URLs d'autorisation/jeton dépendent de la région
choisie à la connexion (voir settings.py::set_zoho_credentials), et Zoho
renvoie en plus un `api_domain` dans la réponse de token à respecter pour
tous les appels API suivants (jamais deviné/reconstruit depuis la région
seule — Zoho documente que ça peut différer).

Comme pour Google, un seul redirect_uri est enregistré côté Zoho API
Console : le `state` encode le service demandé pour router le callback
partagé (aujourd'hui seul zoho_mail.py existe, mais Zoho a d'autres API —
Zoho CRM, Zoho Books… — sur le même mécanisme si un jour utile).
"""
from __future__ import annotations

import secrets
import threading
import time

import requests

from brain import config
from brain.integrations import settings, store

_STATE_TTL = 5 * 60
_state_lock = threading.Lock()
_pending_states: dict[str, tuple[float, str]] = {}  # state -> (expiration, service_type)

_access_cache: dict[str, tuple[str, float]] = {}  # account_id -> (token, expiry)
_access_lock = threading.Lock()


def configured() -> bool:
    client_id, client_secret, _ = settings.get_zoho_credentials()
    return bool(client_id and client_secret)


def _accounts_domain(region: str) -> str:
    return f"https://accounts.zoho.{region}"


def build_auth_url(service_type: str, scope: str) -> str:
    if not configured():
        raise RuntimeError(
            "Identifiants Zoho manquants — renseigne le Client ID / Client "
            "Secret / région dans la Console (Intégrations → Paramètres Zoho)."
        )
    client_id, _, region = settings.get_zoho_credentials()
    state = secrets.token_urlsafe(24)
    with _state_lock:
        _expire_stale_states()
        _pending_states[state] = (time.time() + _STATE_TTL, service_type)
    params = {
        "client_id": client_id,
        "redirect_uri": config.ZOHO_REDIRECT_URI,
        "response_type": "code",
        "scope": scope,
        "access_type": "offline",
        # équivalent du prompt=consent Google : sans ça, une reconnexion
        # (2e compte, ou après révocation) peut ne pas renvoyer de refresh_token.
        "prompt": "consent",
        "state": state,
    }
    query = "&".join(f"{k}={requests.utils.quote(str(v), safe='')}" for k, v in params.items())
    return f"{_accounts_domain(region)}/oauth/v2/auth?{query}"


def _expire_stale_states() -> None:
    now = time.time()
    for s in [s for s, (exp, _) in _pending_states.items() if exp <= now]:
        del _pending_states[s]


def consume_state(state: str) -> str | None:
    with _state_lock:
        entry = _pending_states.pop(state, None)
    if entry is None:
        return None
    expires_at, service_type = entry
    return service_type if expires_at > time.time() else None


def exchange_code(code: str) -> dict:
    """Échange le code contre des jetons + api_domain. Lève RuntimeError si
    Zoho refuse ou ne renvoie pas de refresh_token."""
    client_id, client_secret, region = settings.get_zoho_credentials()
    resp = requests.post(f"{_accounts_domain(region)}/oauth/v2/token", data={
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": config.ZOHO_REDIRECT_URI,
        "grant_type": "authorization_code",
    }, timeout=10)
    if resp.status_code != 200:
        raise RuntimeError(f"échange de code refusé par Zoho : {resp.text[:300]}")
    tokens = resp.json()
    if not tokens.get("refresh_token"):
        raise RuntimeError(
            "Zoho n'a pas renvoyé de jeton de rafraîchissement — révoque "
            "l'accès existant depuis les paramètres de sécurité de ton compte "
            "Zoho puis reconnecte-le."
        )
    if not tokens.get("api_domain"):
        raise RuntimeError(f"Réponse Zoho inattendue (pas d'api_domain) : {resp.text[:300]}")
    return tokens


def access_token_for(account: dict) -> str:
    """Access token courant (cache mémoire, refresh à la demande). La région
    vient de account["extra"]["region"] (stockée à la connexion), pas du
    réglage courant — un compte connecté sous une région reste sur cette
    région même si la config globale change ensuite."""
    account_id = account["id"]
    with _access_lock:
        cached = _access_cache.get(account_id)
        if cached and cached[1] > time.time() + 30:
            return cached[0]

    client_id, client_secret, _ = settings.get_zoho_credentials()
    region = account.get("extra", {}).get("region", "com")
    resp = requests.post(f"{_accounts_domain(region)}/oauth/v2/token", data={
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


def handle_callback(service_type: str, code: str, account_builder) -> dict:
    """Échange le code, construit le compte via
    `account_builder(access_token, api_domain) -> (label, extra_dict)`,
    le stocke sous `service_type`. `account_builder` fait l'appel API
    spécifique au service (ex : lister les comptes Zoho Mail pour trouver
    l'accountId) puisque Zoho n'a pas d'endpoint /userinfo générique commun
    à toutes ses API comme Google."""
    tokens = exchange_code(code)
    _, _, region = settings.get_zoho_credentials()
    label, extra = account_builder(tokens["access_token"], tokens["api_domain"])
    extra["region"] = region
    extra["api_domain"] = tokens["api_domain"]
    return store.add(service_type, label, tokens["refresh_token"], extra)

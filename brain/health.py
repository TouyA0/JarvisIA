"""Sonde de santé des comptes connectés (C7).

`store.list_public()` ne renvoie qu'un horodatage de connexion, jamais un
état de santé : un jeton révoqué (accès retiré côté Google/Zoho/Spotify,
ou serveur Jellyfin/Home Assistant éteint/reconfiguré) restait « connecté »
indéfiniment aux yeux de la Console — rien ne le distinguait d'un compte
qui marche, jusqu'au jour où Jarvis échouait en silence sur une vraie
demande.

Sonde ACTIVE : un aller-retour minimal et authentifié auprès du
fournisseur (rafraîchir un access_token pour OAuth, une requête légère
pour Jellyfin/Home Assistant) plutôt qu'une déduction passive d'un échec
en cours d'usage — sans ça, un jeton mort resterait invisible jusqu'à la
prochaine fois que Monsieur demande vraiment son agenda ou ses mails.
Résultat mis en cache une poignée de minutes pour ne pas rappeler chaque
fournisseur à chaque ouverture de la Console.

`tisseo` n'a pas de sonde : un « compte » y est un arrêt favori, pas un
jeton — rien à expirer (voir tisseo.py). Pareil pour tout type inconnu ici :
`healthy` reste `None` (« non sondable »), à ne pas confondre avec `False`
(« sondé, en échec »).
"""
from __future__ import annotations

import threading
import time

from brain.integrations import android_tv, google_oauth, home_assistant, jellyfin, spotify_oauth, store, zoho_oauth

_CACHE_TTL_S = 5 * 60
_cache: dict[str, dict] = {}
_lock = threading.Lock()

# Un seul callable par type, même contrat partout : appelé avec le compte
# complet (jeton déchiffré), lève une exception si la sonde échoue, ne
# renvoie rien de significatif sinon.
_PROBES = {
    "google_calendar": google_oauth.access_token_for,
    "google_drive": google_oauth.access_token_for,
    "gmail": google_oauth.access_token_for,
    "google_contacts": google_oauth.access_token_for,
    "zoho_mail": zoho_oauth.access_token_for,
    "spotify": spotify_oauth.access_token_for,
    "jellyfin": jellyfin.probe,
    "home_assistant": home_assistant.probe,
}


def _probe(account: dict) -> dict:
    probe_func = _PROBES.get(account["type"])
    if not probe_func:
        return {"healthy": None, "error": None, "checked_at": time.time()}
    try:
        probe_func(account)
        return {"healthy": True, "error": None, "checked_at": time.time()}
    except Exception as exc:
        return {"healthy": False, "error": str(exc)[:200], "checked_at": time.time()}


def check(account_id: str, force: bool = False) -> dict:
    with _lock:
        cached = _cache.get(account_id)
        if cached and not force and time.time() - cached["checked_at"] < _CACHE_TTL_S:
            return cached

    account = store.get(account_id)
    if not account:
        return {"healthy": None, "error": "compte inconnu", "checked_at": time.time()}

    result = _probe(account)
    with _lock:
        _cache[account_id] = result
    return result


_TV_ID = "android_tv"


def _probe_tv() -> dict:
    try:
        android_tv.probe()
        return {"healthy": True, "error": None, "checked_at": time.time()}
    except Exception as exc:
        return {"healthy": False, "error": str(exc)[:200], "checked_at": time.time()}


def check_tv(force: bool = False) -> dict:
    """La télé (T2) n'est pas un compte de `store` — un seul appareil, IP
    fixe en .env, pas de jeton (voir android_tv.py) — donc son état ne peut
    pas passer par `check()`. Même cache 5 min, même contrat de retour."""
    with _lock:
        cached = _cache.get(_TV_ID)
        if cached and not force and time.time() - cached["checked_at"] < _CACHE_TTL_S:
            return cached

    if not android_tv.configured():
        return {"healthy": None, "error": None, "checked_at": time.time()}

    result = _probe_tv()
    with _lock:
        _cache[_TV_ID] = result
    return result


def check_all(force: bool = False) -> dict[str, dict]:
    result = {a["id"]: check(a["id"], force) for a in store.list_public()}
    if android_tv.configured():
        result[_TV_ID] = check_tv(force)
    return result

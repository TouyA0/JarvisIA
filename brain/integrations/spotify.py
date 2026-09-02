"""Intégration Spotify — contrôle de lecture, pas de gestion de contenu
(pas d'écriture destructrice possible ici : lancer/mettre en pause/changer
de morceau n'a rien d'irréversible). Cohérent avec la décision déjà prise
dans docs/ROADMAP_DISPLAY_INTEGRATIONS.md (I6) : contrôle direct, aucune
confirmation nécessaire — contrairement à Drive/Gmail/Zoho.

Un seul compte actif à la fois a du sens pour de la musique (contrairement
à Calendar/Drive où fusionner plusieurs comptes est naturel) : plusieurs
comptes PEUVENT être connectés (même modèle de stockage), mais les outils
opèrent sur le premier connecté sauf `account` explicite — jamais fusionnés.

Toute action de lecture (play/pause/next/volume) suppose un appareil
Spotify déjà actif quelque part (l'app ouverte sur le téléphone, le PC, un
enceinte connectée…) — sans ça, Spotify répond 404 NO_ACTIVE_DEVICE, géré
explicitement ici avec un message actionnable plutôt qu'une erreur brute.
"""
from __future__ import annotations

import requests

from brain.integrations import spotify_oauth, store

SERVICE_TYPE = "spotify"
SCOPE = (
    "user-read-playback-state user-modify-playback-state user-read-currently-playing "
    "playlist-read-private playlist-read-collaborative user-read-private"
)
API = "https://api.spotify.com/v1"


def configured() -> bool:
    return spotify_oauth.configured()


def build_auth_url() -> str:
    return spotify_oauth.build_auth_url(SCOPE)


def _fetch_account_label(access_token: str) -> str:
    resp = requests.get(f"{API}/me", headers={"Authorization": f"Bearer {access_token}"}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return data.get("display_name") or data.get("email") or data.get("id", "compte Spotify")


def handle_callback(code: str) -> dict:
    return spotify_oauth.handle_callback(SERVICE_TYPE, code, _fetch_account_label)


def _pick_account(account_hint: str | None = None) -> dict | None:
    accounts = store.list_for(SERVICE_TYPE)
    if account_hint:
        accounts = [a for a in accounts if account_hint.lower() in a["label"].lower()] or accounts
    return accounts[0] if accounts else None


def _headers(account: dict) -> dict:
    return {"Authorization": f"Bearer {spotify_oauth.access_token_for(account)}"}


def _no_device_message() -> str:
    return "Aucun appareil Spotify actif, Monsieur — ouvre l'application Spotify quelque part (téléphone, PC, enceinte) puis réessaie."


def now_playing(account_hint: str | None = None) -> dict:
    account = _pick_account(account_hint)
    if not account:
        return {"error": "Aucun compte Spotify connecté, Monsieur."}
    resp = requests.get(f"{API}/me/player/currently-playing", headers=_headers(account), timeout=10)
    if resp.status_code == 204 or not resp.content:
        return {"playing": False}
    if resp.status_code != 200:
        return {"error": f"Spotify a refusé la requête ({resp.status_code}), Monsieur."}
    data = resp.json()
    item = data.get("item")
    if not item:
        return {"playing": False}
    album = item.get("album", {})
    images = album.get("images") or []
    return {
        "playing": data.get("is_playing", False),
        "track": item.get("name", ""),
        "artists": ", ".join(a["name"] for a in item.get("artists", [])),
        "album": album.get("name", ""),
        # Pochette : inutile à l'oral, mais c'est tout l'intérêt de la carte
        # « morceau en cours » côté Console (ROADMAP_DISPLAY_INTEGRATIONS.md
        # §2.2). Spotify trie ses images de la plus grande à la plus petite.
        "cover": images[0].get("url", "") if images else "",
        "progress_ms": data.get("progress_ms", 0),
        "duration_ms": item.get("duration_ms", 0),
    }


def _search_own_playlists(account: dict, query: str) -> dict | None:
    resp = requests.get(f"{API}/me/playlists", headers=_headers(account), params={"limit": 50}, timeout=10)
    if resp.status_code != 200:
        return None
    q = query.lower()
    for pl in resp.json().get("items", []):
        if q in pl.get("name", "").lower():
            return {"type": "playlist", "name": pl["name"], "uri": pl["uri"]}
    return None


def _search_catalog(account: dict, query: str) -> dict | None:
    resp = requests.get(
        f"{API}/search", headers=_headers(account),
        params={"q": query, "type": "track,playlist,album,artist", "limit": 1}, timeout=10,
    )
    if resp.status_code != 200:
        return None
    data = resp.json()
    # Ordre de priorité : un titre précis avant une collection — "mets X"
    # dit le plus souvent un morceau, sauf s'il a été trouvé dans les
    # playlists personnelles juste avant (_search_own_playlists).
    for kind in ("tracks", "playlists", "albums", "artists"):
        items = data.get(kind, {}).get("items", [])
        if items and items[0]:
            item = items[0]
            name = item["name"]
            if kind == "tracks":
                name = f"{name} — {', '.join(a['name'] for a in item.get('artists', []))}"
            return {"type": kind[:-1], "name": name, "uri": item["uri"]}
    return None


def play(query: str, account_hint: str | None = None) -> dict:
    """Résout `query` (playlist perso d'abord, puis catalogue Spotify :
    titre/playlist publique/album/artiste) et lance la lecture sur
    l'appareil actif. Aucune confirmation — action directe, réversible."""
    account = _pick_account(account_hint)
    if not account:
        return {"error": "Aucun compte Spotify connecté, Monsieur."}

    match = _search_own_playlists(account, query) or _search_catalog(account, query)
    if not match:
        return {"error": f"Rien trouvé sur Spotify pour « {query} », Monsieur."}

    body = {"uris": [match["uri"]]} if match["type"] == "track" else {"context_uri": match["uri"]}
    resp = requests.put(f"{API}/me/player/play", headers=_headers(account), json=body, timeout=10)
    if resp.status_code == 404:
        return {"error": _no_device_message()}
    if resp.status_code not in (200, 204):
        return {"error": f"Lecture refusée par Spotify ({resp.status_code}), Monsieur."}
    return {"name": match["name"], "type": match["type"]}


_CONTROL_ENDPOINTS = {
    "pause": ("PUT", "/me/player/pause"),
    "resume": ("PUT", "/me/player/play"),
    "next": ("POST", "/me/player/next"),
    "previous": ("POST", "/me/player/previous"),
}


def control(action: str, account_hint: str | None = None) -> dict:
    if action not in _CONTROL_ENDPOINTS:
        return {"error": f"Action inconnue : {action!r}, Monsieur."}
    account = _pick_account(account_hint)
    if not account:
        return {"error": "Aucun compte Spotify connecté, Monsieur."}
    method, path = _CONTROL_ENDPOINTS[action]
    resp = requests.request(method, f"{API}{path}", headers=_headers(account), timeout=10)
    if resp.status_code == 404:
        return {"error": _no_device_message()}
    if resp.status_code not in (200, 204):
        return {"error": f"Action refusée par Spotify ({resp.status_code}), Monsieur."}
    return {"action": action}


def list_devices(account_hint: str | None = None) -> dict:
    """GET /me/player/devices — tous les appareils que Spotify voit
    actuellement (app ouverte au moins une fois récemment quelque part :
    téléphone, PC, enceinte Connect, TV…), pas seulement celui actif."""
    account = _pick_account(account_hint)
    if not account:
        return {"error": "Aucun compte Spotify connecté, Monsieur."}
    resp = requests.get(f"{API}/me/player/devices", headers=_headers(account), timeout=10)
    if resp.status_code != 200:
        return {"error": f"Spotify a refusé la requête ({resp.status_code}), Monsieur."}
    devices = [
        {
            "id": d["id"],
            "name": d.get("name", ""),
            "type": d.get("type", ""),
            "is_active": d.get("is_active", False),
            "volume_percent": d.get("volume_percent"),
        }
        for d in resp.json().get("devices", [])
    ]
    return {"devices": devices}


def transfer(device_name: str, account_hint: str | None = None) -> dict:
    """C5 — PUT /me/player : bascule la lecture vers l'appareil Spotify dont
    le nom contient `device_name` (substring insensible à la casse — « télé
    », « salon », un nom d'enceinte…), plutôt qu'un identifiant technique
    que Monsieur ne connaît pas. `play: true` : reprend/démarre sur le
    nouvel appareil immédiatement, pas juste un changement d'appareil actif
    silencieux — c'est tout l'intérêt de « passe la musique sur X ».
    L'appareil cible doit avoir eu l'app Spotify ouverte récemment pour
    apparaître dans /devices (limite Spotify, pas de cette intégration)."""
    if not device_name or not device_name.strip():
        return {"error": "Nom d'appareil manquant, Monsieur."}
    account = _pick_account(account_hint)
    if not account:
        return {"error": "Aucun compte Spotify connecté, Monsieur."}

    result = list_devices(account_hint)
    if "error" in result:
        return result
    devices = result["devices"]
    if not devices:
        return {"error": "Aucun appareil Spotify visible, Monsieur — ouvre l'application sur l'appareil cible au moins une fois."}

    needle = device_name.strip().lower()
    match = next((d for d in devices if needle in d["name"].lower()), None)
    if not match:
        names = ", ".join(d["name"] for d in devices)
        return {"error": f"Aucun appareil Spotify ne correspond à « {device_name} », Monsieur — appareils visibles : {names}."}

    resp = requests.put(
        f"{API}/me/player", headers=_headers(account),
        json={"device_ids": [match["id"]], "play": True}, timeout=10,
    )
    if resp.status_code not in (200, 202, 204):
        return {"error": f"Transfert refusé par Spotify ({resp.status_code}), Monsieur."}
    return {"device": match["name"]}


def set_volume(percent: int, account_hint: str | None = None) -> dict:
    account = _pick_account(account_hint)
    if not account:
        return {"error": "Aucun compte Spotify connecté, Monsieur."}
    percent = max(0, min(100, percent))
    resp = requests.put(f"{API}/me/player/volume", headers=_headers(account), params={"volume_percent": percent}, timeout=10)
    if resp.status_code == 404:
        return {"error": _no_device_message()}
    if resp.status_code not in (200, 204):
        return {"error": f"Réglage refusé par Spotify ({resp.status_code}), Monsieur."}
    return {"percent": percent}

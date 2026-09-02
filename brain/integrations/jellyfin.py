"""Intégration Jellyfin — serveur personnel, pas de fournisseur tiers : pas
d'OAuth, une simple clé API générée depuis le tableau de bord Jellyfin
(Admin → Clés API). Connexion en une étape (voir server.py::connect_jellyfin),
pas de flux consentement/callback comme Google/Zoho/Spotify.

La clé API donne un accès de niveau serveur (pas lié à un utilisateur), mais
plusieurs endpoints utiles (reprise de lecture, nouveautés) sont scopés par
utilisateur Jellyfin — un `username` optionnel à la connexion permet de
résoudre le bon user_id une fois pour toutes (stocké dans extra, voir
brain/integrations/store.py). Sans lui, on prend le premier utilisateur
trouvé — imprécis si le serveur a plusieurs comptes, mais reste utilisable
pour la recherche (non scopée par utilisateur).

Recherche, lecture en cours, reprise, nouveautés — et, depuis C4, contrôle
à distance minimal d'une session existante (`resume_on_session`, via
`Sessions/{id}/Playing`) : reprendre sur la télé du salon un épisode en
cours ailleurs, sans passer par un deep-link app par app (voir
_find_tv_session)."""
from __future__ import annotations

import requests

from brain.integrations import store

SERVICE_TYPE = "jellyfin"


def _headers(account: dict) -> dict:
    return {"X-Emby-Token": account["refresh_token"]}  # "refresh_token" = la clé API, voir connect()


def _base_url(account: dict) -> str:
    return account.get("extra", {}).get("base_url", "").rstrip("/")


def connect(base_url: str, api_key: str, username: str | None = None) -> dict:
    """Valide la clé API contre le serveur, résout l'utilisateur si nommé,
    stocke la connexion. Lève RuntimeError si le serveur ne répond pas ou
    refuse la clé — message inclus pour diagnostiquer (mauvaise URL, clé
    révoquée, serveur injoignable depuis le brain…)."""
    base_url = base_url.rstrip("/")
    headers = {"X-Emby-Token": api_key}

    try:
        info_resp = requests.get(f"{base_url}/System/Info", headers=headers, timeout=8)
    except requests.RequestException as exc:
        raise RuntimeError(f"Serveur Jellyfin injoignable à {base_url} : {exc}")
    if info_resp.status_code != 200:
        raise RuntimeError(f"Clé API refusée par Jellyfin ({info_resp.status_code}) — vérifie la clé et l'URL.")
    server_name = info_resp.json().get("ServerName", "Jellyfin")

    users_resp = requests.get(f"{base_url}/Users", headers=headers, timeout=8)
    users = users_resp.json() if users_resp.status_code == 200 else []
    user_id = None
    label_user = None
    if username:
        match = next((u for u in users if u.get("Name", "").lower() == username.lower()), None)
        if not match:
            raise RuntimeError(f"Aucun utilisateur Jellyfin nommé « {username} » sur ce serveur.")
        user_id, label_user = match["Id"], match["Name"]
    elif users:
        user_id, label_user = users[0]["Id"], users[0]["Name"]

    label = f"{server_name} ({label_user})" if label_user else server_name
    return store.add(SERVICE_TYPE, label, api_key, {"base_url": base_url, "user_id": user_id})


def probe(account: dict) -> None:
    """Sonde de santé (C7, voir brain/health.py) — même endpoint que
    connect(), lève si le serveur est injoignable ou la clé révoquée."""
    resp = requests.get(f"{_base_url(account)}/System/Info", headers=_headers(account), timeout=6)
    if resp.status_code != 200:
        raise RuntimeError(f"Jellyfin a refusé la clé API ({resp.status_code})")


def _pick_account(account_hint: str | None = None) -> dict | None:
    accounts = store.list_for(SERVICE_TYPE)
    if account_hint:
        accounts = [a for a in accounts if account_hint.lower() in a["label"].lower()] or accounts
    return accounts[0] if accounts else None


def search(query: str, account_hint: str | None = None, limit: int = 10) -> list[dict]:
    account = _pick_account(account_hint)
    if not account:
        return [{"error": "Aucun serveur Jellyfin connecté, Monsieur."}]
    resp = requests.get(
        f"{_base_url(account)}/Items",
        headers=_headers(account),
        params={
            "searchTerm": query, "Recursive": "true", "Limit": limit,
            "IncludeItemTypes": "Movie,Series,Episode,Audio",
            "Fields": "ProductionYear,Overview",
        },
        timeout=10,
    )
    if resp.status_code != 200:
        return [{"error": f"Recherche refusée par Jellyfin ({resp.status_code}), Monsieur."}]
    items = []
    for it in resp.json().get("Items", []):
        items.append({
            "name": it.get("Name", "(sans titre)"),
            "type": it.get("Type", ""),
            "year": it.get("ProductionYear"),
            "series": it.get("SeriesName"),
        })
    return items


def now_playing(account_hint: str | None = None) -> list[dict]:
    """Sessions actives sur le serveur (tous appareils confondus) — pas
    filtré par utilisateur : sur un serveur personnel mono-utilisateur ça
    n'a pas d'importance, sur un serveur partagé ça montre tout le monde."""
    account = _pick_account(account_hint)
    if not account:
        return [{"error": "Aucun serveur Jellyfin connecté, Monsieur."}]
    resp = requests.get(f"{_base_url(account)}/Sessions", headers=_headers(account), timeout=10)
    if resp.status_code != 200:
        return [{"error": f"Requête refusée par Jellyfin ({resp.status_code}), Monsieur."}]
    sessions = []
    for s in resp.json():
        item = s.get("NowPlayingItem")
        if not item:
            continue
        sessions.append({
            "title": item.get("Name", ""),
            "series": item.get("SeriesName"),
            "user": s.get("UserName", ""),
            "device": s.get("DeviceName", ""),
            "paused": s.get("PlayState", {}).get("IsPaused", False),
        })
    return sessions


def continue_watching(account_hint: str | None = None, limit: int = 10) -> list[dict]:
    account = _pick_account(account_hint)
    if not account:
        return [{"error": "Aucun serveur Jellyfin connecté, Monsieur."}]
    user_id = account.get("extra", {}).get("user_id")
    if not user_id:
        return [{"error": "Aucun utilisateur Jellyfin résolu pour ce serveur, Monsieur — reconnecte en précisant un nom d'utilisateur."}]
    resp = requests.get(
        f"{_base_url(account)}/Users/{user_id}/Items/Resume",
        headers=_headers(account), params={"Limit": limit}, timeout=10,
    )
    if resp.status_code != 200:
        return [{"error": f"Requête refusée par Jellyfin ({resp.status_code}), Monsieur."}]
    items = []
    for it in resp.json().get("Items", []):
        items.append({
            "id": it.get("Id"),
            "name": it.get("Name", ""),
            "series": it.get("SeriesName"),
            "type": it.get("Type", ""),
            # C4 — position de reprise exacte (100 ns/tick, format Jellyfin) : sert à
            # relancer la lecture au bon endroit via resume_on_session(), pas affiché
            # à la voix (voir _format_jellyfin_items dans brain/tools.py).
            "resume_position_ticks": it.get("UserData", {}).get("PlaybackPositionTicks", 0),
        })
    return items


def recently_added(account_hint: str | None = None, limit: int = 10) -> list[dict]:
    account = _pick_account(account_hint)
    if not account:
        return [{"error": "Aucun serveur Jellyfin connecté, Monsieur."}]
    user_id = account.get("extra", {}).get("user_id")
    if not user_id:
        return [{"error": "Aucun utilisateur Jellyfin résolu pour ce serveur, Monsieur — reconnecte en précisant un nom d'utilisateur."}]
    resp = requests.get(
        f"{_base_url(account)}/Users/{user_id}/Items/Latest",
        headers=_headers(account), params={"Limit": limit}, timeout=10,
    )
    if resp.status_code != 200:
        return [{"error": f"Requête refusée par Jellyfin ({resp.status_code}), Monsieur."}]
    items = []
    for it in resp.json():
        items.append({"name": it.get("Name", ""), "type": it.get("Type", ""), "year": it.get("ProductionYear")})
    return items


def find_resume_item(query: str, account_hint: str | None = None) -> dict | None:
    """Cherche `query` (texte libre, « reprends mon épisode ») dans la liste
    « reprendre la lecture » (continue_watching()) — substring insensible à
    la casse sur le titre ET le nom de série, pour que « reprends breaking
    bad » matche un épisode dont le titre affiché est juste « Felina ».
    None si rien ne correspond ou si continue_watching() a échoué (compte
    absent, serveur injoignable…) plutôt que de faire remonter l'erreur ici
    — resume_on_tv (brain/tools.py) sait déjà distinguer les deux cas via
    continue_watching() directement."""
    query = query.strip().lower()
    if not query:
        return None
    items = continue_watching(account_hint, limit=20)
    if items and "error" in items[0]:
        return None
    for it in items:
        haystack = f"{it.get('series') or ''} {it.get('name') or ''}".lower()
        if query in haystack:
            return it
    return None


def _find_tv_session(account: dict) -> dict | None:
    """Session Jellyfin active correspondant à la télé du salon, parmi
    `/Sessions` (tous appareils confondus, voir now_playing()). Best
    effort : le client officiel Android TV se déclare "Jellyfin Android TV"
    dans le champ Client — on matche là-dessus en priorité ; à défaut, la
    première session qui accepte le contrôle à distance
    (`SupportsMediaControl`), pour rester utilisable même si le nom du
    client change un jour. None si l'appli Jellyfin n'est pas ouverte sur
    la télé (aucune session active tant qu'elle ne l'est pas) — à
    l'appelant de la lancer via android_tv.launch_app avant de réessayer."""
    resp = requests.get(f"{_base_url(account)}/Sessions", headers=_headers(account), timeout=10)
    if resp.status_code != 200:
        return None
    sessions = resp.json()
    for s in sessions:
        if "android tv" in (s.get("Client") or "").lower():
            return s
    for s in sessions:
        if s.get("SupportsMediaControl"):
            return s
    return None


def resume_on_session(item_id: str, position_ticks: int, account_hint: str | None = None) -> dict:
    """C4 — contrôle à distance d'une session déjà ouverte (`Sessions/{id}/
    Playing`), plutôt qu'un deep-link app par app : demande à la session
    Jellyfin trouvée sur la télé de lancer `item_id` à `position_ticks`.
    Ne fonctionne que si l'appli Jellyfin est déjà ouverte sur l'appareil
    cible (une session existe côté serveur tant qu'elle tourne, y compris
    en arrière-plan) — sinon renvoie {"error": "no_session"} (valeur
    sentinelle, pas un message pour Monsieur) : à l'appelant de lancer
    l'appli (android_tv.launch_app) puis de réessayer une fois, comme pour
    launch_app()/send_to_tv() ailleurs dans ce module."""
    account = _pick_account(account_hint)
    if not account:
        return {"error": "Aucun serveur Jellyfin connecté, Monsieur."}
    session = _find_tv_session(account)
    if not session:
        return {"error": "no_session"}
    resp = requests.post(
        f"{_base_url(account)}/Sessions/{session['Id']}/Playing",
        headers=_headers(account),
        params={"ItemIds": item_id, "StartPositionTicks": int(position_ticks), "PlayCommand": "PlayNow"},
        timeout=10,
    )
    if resp.status_code not in (200, 204):
        return {"error": f"Jellyfin a refusé de lancer la lecture ({resp.status_code}), Monsieur."}
    return {"ok": True, "device": session.get("DeviceName") or "l'appareil"}

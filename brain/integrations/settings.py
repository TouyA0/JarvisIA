"""Identifiants d'appli tiers (Client ID/Secret Google…) réglables depuis
la Console web, sans éditer `.env` à la main.

Ne pas confondre avec `brain/integrations/store.py` : ceci stocke les
identifiants de l'**application** Jarvis elle-même (un seul jeu, créé une
fois dans Google Cloud Console — Google ne fournit aucune API pour créer ce
genre de client OAuth automatiquement, c'est un geste manuel obligatoire
dans leur console, pas quelque chose qu'on peut contourner). `store.py`
stocke lui les **comptes utilisateur** connectés à travers cette appli
(potentiellement plusieurs) — ce sont eux qui se gèrent entièrement depuis
le panneau Intégrations (connecter/déconnecter), aucune manip fichier
requise.

`.env` (GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET) reste utilisable et prend le
pas au premier lancement si déjà rempli — sinon la valeur saisie dans la
Console est mémorisée ici (chiffrée comme les jetons, voir crypto.py) et
prioritaire ensuite.
"""
from __future__ import annotations

import json

from brain import config
from brain.integrations import crypto

_SETTINGS_FILE = config.DATA_DIR / "integrations_settings.json"


def _load() -> dict:
    if _SETTINGS_FILE.exists():
        with open(_SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save(data: dict) -> None:
    config.ensure_dirs()
    with open(_SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_google_credentials() -> tuple[str, str]:
    """(client_id, client_secret) — priorité au réglage saisi dans la
    Console, sinon repli sur .env, comme documenté ci-dessus."""
    data = _load().get("google", {})
    if data.get("client_id") and data.get("client_secret_enc"):
        return data["client_id"], crypto.decrypt(data["client_secret_enc"])
    return config.GOOGLE_CLIENT_ID, config.GOOGLE_CLIENT_SECRET


def set_google_credentials(client_id: str, client_secret: str) -> None:
    data = _load()
    data["google"] = {"client_id": client_id, "client_secret_enc": crypto.encrypt(client_secret)}
    _save(data)


def clear_google_credentials() -> None:
    data = _load()
    data.pop("google", None)
    _save(data)


def google_status() -> dict:
    """Ce que la Console affiche : configuré ou pas, et d'où vient le
    réglage — jamais le secret lui-même."""
    client_id, client_secret = get_google_credentials()
    if not (client_id and client_secret):
        return {"configured": False, "source": None, "client_id": None}
    source = "console" if "google" in _load() else "env"
    return {"configured": True, "source": source, "client_id": client_id}


# ── Zoho ─────────────────────────────────────────────────────────────────
# Même principe que Google, mais Zoho n'a pas de .env de repli : un compte
# Zoho est bien plus rare que Google dans ce projet, autant garder un seul
# chemin de configuration (la Console) plutôt que dupliquer le mécanisme
# .env pour un cas d'usage aussi ciblé. La région (com/eu/in/com.au/jp/ca)
# est nécessaire : Zoho isole ses comptes par datacenter, se tromper de
# région fait échouer l'authentification entière — voir README.md.
_ZOHO_REGIONS = {"com", "eu", "in", "com.au", "jp", "ca"}


def get_zoho_credentials() -> tuple[str, str, str]:
    """(client_id, client_secret, region) — région vide si jamais configuré."""
    data = _load().get("zoho", {})
    if data.get("client_id") and data.get("client_secret_enc"):
        return data["client_id"], crypto.decrypt(data["client_secret_enc"]), data.get("region", "com")
    return "", "", "com"


def set_zoho_credentials(client_id: str, client_secret: str, region: str) -> None:
    if region not in _ZOHO_REGIONS:
        raise ValueError(f"région Zoho inconnue : {region!r} (attendu : {', '.join(sorted(_ZOHO_REGIONS))})")
    data = _load()
    data["zoho"] = {"client_id": client_id, "client_secret_enc": crypto.encrypt(client_secret), "region": region}
    _save(data)


def clear_zoho_credentials() -> None:
    data = _load()
    data.pop("zoho", None)
    _save(data)


def zoho_status() -> dict:
    client_id, client_secret, region = get_zoho_credentials()
    if not (client_id and client_secret):
        return {"configured": False, "client_id": None, "region": None}
    return {"configured": True, "client_id": client_id, "region": region}


# ── Spotify ──────────────────────────────────────────────────────────────
# Même principe que Zoho (Console uniquement, pas de repli .env) — un seul
# datacenter/domaine chez Spotify, pas de région à choisir.
def get_spotify_credentials() -> tuple[str, str]:
    data = _load().get("spotify", {})
    if data.get("client_id") and data.get("client_secret_enc"):
        return data["client_id"], crypto.decrypt(data["client_secret_enc"])
    return "", ""


def set_spotify_credentials(client_id: str, client_secret: str) -> None:
    data = _load()
    data["spotify"] = {"client_id": client_id, "client_secret_enc": crypto.encrypt(client_secret)}
    _save(data)


def clear_spotify_credentials() -> None:
    data = _load()
    data.pop("spotify", None)
    _save(data)


def spotify_status() -> dict:
    client_id, client_secret = get_spotify_credentials()
    if not (client_id and client_secret):
        return {"configured": False, "client_id": None}
    return {"configured": True, "client_id": client_id}


# ── Tisséo ───────────────────────────────────────────────────────────────
# Une seule clé (pas de paire client_id/secret — l'API Tisséo authentifie
# par clé simple) : gratuite, sans facturation, à la différence de Google
# Maps évoqué puis écarté pour cette raison.
def get_tisseo_api_key() -> str:
    data = _load().get("tisseo", {})
    return crypto.decrypt(data["api_key_enc"]) if data.get("api_key_enc") else ""


def set_tisseo_api_key(api_key: str) -> None:
    data = _load()
    data["tisseo"] = {"api_key_enc": crypto.encrypt(api_key)}
    _save(data)


def clear_tisseo_api_key() -> None:
    data = _load()
    data.pop("tisseo", None)
    _save(data)


def tisseo_status() -> dict:
    return {"configured": bool(get_tisseo_api_key())}

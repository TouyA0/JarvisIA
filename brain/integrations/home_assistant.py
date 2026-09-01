"""Intégration Home Assistant — API REST, authentification par token
longue durée (généré dans le profil utilisateur HA), pas d'OAuth. Même
schéma de connexion directe que Jellyfin (base_url + jeton, pas de popup).

Résolution d'entité par nom (friendly_name) en texte libre plutôt que par
entity_id technique ("light.salon_plafonnier") — Monsieur dit « la lumière
du salon », pas l'identifiant HA. Premier match en cas d'ambiguïté (même
compromis que google_drive._pick_account/jellyfin) : à préciser vocalement
si plusieurs correspondances existent.

Sécurité : contrôle direct (allumer/éteindre/régler) pour la plupart des
domaines — pas destructif, réversible en un mot. EXCEPTION : déverrouiller
une serrure (lock) ou désarmer une alarme (alarm_control_panel) passe par
confirm.py, comme les écritures Drive/Gmail — ce sont les deux seules
actions HA qui rendent la maison MOINS sûre plutôt que plus pratique.
Verrouiller/armer (rendre plus sûr) ne demande jamais de confirmation.
"""
from __future__ import annotations

import requests

from brain.integrations import confirm, store

SERVICE_TYPE = "home_assistant"

# Domaines dont l'ouverture (unlock/disarm) exige une confirmation — jamais
# leur fermeture (lock/arm), qui ne fait que sécuriser davantage.
_SENSITIVE_DOMAINS = {"lock", "alarm_control_panel"}


def _headers(account: dict) -> dict:
    return {"Authorization": f"Bearer {account['refresh_token']}", "Content-Type": "application/json"}


def _base_url(account: dict) -> str:
    return account.get("extra", {}).get("base_url", "").rstrip("/")


def connect(base_url: str, token: str) -> dict:
    """Valide le token contre l'instance HA, stocke la connexion. Lève
    RuntimeError si l'instance ne répond pas ou refuse le token."""
    base_url = base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {token}"}
    try:
        resp = requests.get(f"{base_url}/api/config", headers=headers, timeout=8)
    except requests.RequestException as exc:
        raise RuntimeError(f"Instance Home Assistant injoignable à {base_url} : {exc}")
    if resp.status_code != 200:
        raise RuntimeError(f"Token refusé par Home Assistant ({resp.status_code}) — vérifie le token et l'URL.")
    label = resp.json().get("location_name", "Home Assistant")
    return store.add(SERVICE_TYPE, label, token, {"base_url": base_url})


def probe(account: dict) -> None:
    """Sonde de santé (C7, voir brain/health.py) — même endpoint que
    connect(), lève si l'instance est injoignable ou le token révoqué."""
    resp = requests.get(f"{_base_url(account)}/api/config", headers=_headers(account), timeout=6)
    if resp.status_code != 200:
        raise RuntimeError(f"Home Assistant a refusé le token ({resp.status_code})")


def _pick_account(account_hint: str | None = None) -> dict | None:
    accounts = store.list_for(SERVICE_TYPE)
    if account_hint:
        accounts = [a for a in accounts if account_hint.lower() in a["label"].lower()] or accounts
    return accounts[0] if accounts else None


def _all_states(account: dict) -> list[dict]:
    resp = requests.get(f"{_base_url(account)}/api/states", headers=_headers(account), timeout=10)
    if resp.status_code != 200:
        raise RuntimeError(f"États refusés par Home Assistant ({resp.status_code}) : {resp.text[:200]}")
    return resp.json()


def _find_entity(account: dict, query: str) -> dict | None:
    q = query.lower()
    states = _all_states(account)
    for s in states:
        name = s.get("attributes", {}).get("friendly_name", "")
        if q in name.lower():
            return s
    return None


def _entity_summary(entity: dict) -> dict:
    attrs = entity.get("attributes", {})
    # Attributs "simples" seulement (str/int/float/bool) — une prévision
    # météo ou une liste de capteurs groupés peut porter des listes/dicts
    # volumineux dans ses attributs, sans intérêt pour une réponse vocale
    # et coûteux en tokens ; ce qui compte (température, %, statut...) est
    # presque toujours une valeur simple.
    simple_attrs = {
        k: v for k, v in attrs.items()
        if k != "friendly_name" and isinstance(v, (str, int, float, bool))
    }
    return {
        "entity_id": entity["entity_id"],
        "name": attrs.get("friendly_name", entity["entity_id"]),
        "state": entity.get("state", "?"),
        "attributes": simple_attrs,
    }


def get_state(query: str, account_hint: str | None = None, limit: int = 10) -> list[dict]:
    """Toutes les entités dont le nom contient `query` (pas seulement la
    première trouvée) — pour couvrir un domaine entier plutôt qu'un seul
    appareil ("le serveur", "sécurité"...) qui peut correspondre à
    plusieurs capteurs distincts sur le tableau de bord Home Assistant.
    Attributs complets (pas juste l'état) pour ne rien perdre de ce qui est
    visible dans l'Aperçu."""
    account = _pick_account(account_hint)
    if not account:
        return [{"error": "Aucune instance Home Assistant connectée, Monsieur."}]
    try:
        states = _all_states(account)
    except RuntimeError as exc:
        return [{"error": str(exc)}]
    q = query.lower()
    matches = [s for s in states if q in s.get("attributes", {}).get("friendly_name", "").lower()]
    if not matches:
        return [{"error": f"Aucune entité trouvée pour « {query} », Monsieur."}]
    return [_entity_summary(s) for s in matches[:limit]]


def list_all(account_hint: str | None = None, domain: str | None = None) -> list[dict]:
    """Toutes les entités (ou filtrées par domaine, ex. "sensor",
    "binary_sensor", "persistent_notification") — pour explorer ce qui
    existe sur l'instance quand Monsieur ne connaît pas le nom exact
    d'une entité, ou pour balayer les notifications actives."""
    account = _pick_account(account_hint)
    if not account:
        return [{"error": "Aucune instance Home Assistant connectée, Monsieur."}]
    try:
        states = _all_states(account)
    except RuntimeError as exc:
        return [{"error": str(exc)}]
    if domain:
        states = [s for s in states if s["entity_id"].startswith(f"{domain}.")]
    return [_entity_summary(s) for s in states]


def network_status(account_hint: str | None = None) -> dict:
    """Compte les entités `device_tracker` (présence réseau — routeur,
    UniFi, etc.) en ligne/hors ligne. Requête agrégée, pas de nom d'entité
    à donner — différent de get_state qui cherche UNE entité par nom."""
    account = _pick_account(account_hint)
    if not account:
        return {"error": "Aucune instance Home Assistant connectée, Monsieur."}
    try:
        states = _all_states(account)
    except RuntimeError as exc:
        return {"error": str(exc)}

    trackers = [s for s in states if s["entity_id"].startswith("device_tracker.")]
    if not trackers:
        return {"error": "Aucune entité device_tracker trouvée, Monsieur — ton intégration réseau (routeur, UniFi…) n'expose peut-être pas ce domaine."}

    online = [t.get("attributes", {}).get("friendly_name", t["entity_id"]) for t in trackers if t.get("state") == "home"]
    offline = [t.get("attributes", {}).get("friendly_name", t["entity_id"]) for t in trackers if t.get("state") != "home"]
    return {"online": online, "offline": offline}


def _call_service(account: dict, domain: str, service: str, entity_id: str) -> dict:
    resp = requests.post(
        f"{_base_url(account)}/api/services/{domain}/{service}",
        headers=_headers(account), json={"entity_id": entity_id}, timeout=10,
    )
    if resp.status_code != 200:
        return {"error": f"Action refusée par Home Assistant ({resp.status_code}) : {resp.text[:200]}"}
    return {"ok": True}


def control(entity_query: str, action: str, account_hint: str | None = None) -> dict:
    """`action` : "on" (allumer/verrouiller/armer), "off" (éteindre/
    déverrouiller/désarmer), "toggle". Utilise le service générique
    homeassistant.turn_on/turn_off/toggle — fonctionne sur tous les
    domaines contrôlables sans avoir à connaître le nom exact du service
    propre à chaque domaine (light.turn_on vs switch.turn_on, etc.)."""
    if action not in ("on", "off", "toggle"):
        return {"error": f"Action inconnue : {action!r}, Monsieur."}
    account = _pick_account(account_hint)
    if not account:
        return {"error": "Aucune instance Home Assistant connectée, Monsieur."}
    try:
        entity = _find_entity(account, entity_query)
    except RuntimeError as exc:
        return {"error": str(exc)}
    if not entity:
        return {"error": f"Aucune entité trouvée pour « {entity_query} », Monsieur."}

    entity_id = entity["entity_id"]
    domain = entity_id.split(".", 1)[0]
    name = entity.get("attributes", {}).get("friendly_name", entity_query)

    if domain in _SENSITIVE_DOMAINS and action in ("off", "toggle"):
        verb = "désarmer" if domain == "alarm_control_panel" else "déverrouiller"
        summary = f"{verb.capitalize()} « {name} » (Home Assistant) — rend la maison moins sûre, Monsieur."
        if not confirm.request(summary):
            return {"error": "Action refusée par Monsieur ou confirmation expirée, Monsieur."}

    service = {"on": "turn_on", "off": "turn_off", "toggle": "toggle"}[action]
    result = _call_service(account, "homeassistant", service, entity_id)
    if "error" in result:
        return result
    return {"name": name, "action": action}


def set_temperature(entity_query: str, temperature: float, account_hint: str | None = None) -> dict:
    account = _pick_account(account_hint)
    if not account:
        return {"error": "Aucune instance Home Assistant connectée, Monsieur."}
    try:
        entity = _find_entity(account, entity_query)
    except RuntimeError as exc:
        return {"error": str(exc)}
    if not entity:
        return {"error": f"Aucune entité de chauffage trouvée pour « {entity_query} », Monsieur."}
    entity_id = entity["entity_id"]
    if not entity_id.startswith("climate."):
        return {"error": f"« {entity_query} » n'est pas un thermostat (domaine {entity_id.split('.')[0]}), Monsieur."}

    resp = requests.post(
        f"{_base_url(account)}/api/services/climate/set_temperature",
        headers=_headers(account), json={"entity_id": entity_id, "temperature": temperature}, timeout=10,
    )
    if resp.status_code != 200:
        return {"error": f"Réglage refusé par Home Assistant ({resp.status_code}) : {resp.text[:200]}"}
    return {"name": entity.get("attributes", {}).get("friendly_name", entity_query), "temperature": temperature}

"""Intégration Zoho Mail — même schéma que google_gmail.py, mécanique OAuth
séparée via zoho_oauth.py (Zoho n'est pas Google : multi-datacenter,
indirection par accountId numérique, endpoints propres).

Fiabilité des endpoints utilisés ici, à connaître avant de dépanner :
  - search()/read_message() : endpoints de LECTURE (GET), bien documentés
    et stables côté Zoho — fiables.
  - create_draft()/send_message() : l'API "compose" de Zoho Mail est moins
    limpide sur la frontière exacte brouillon/envoi que celle de Gmail (pas
    de séparation drafts.create / drafts.send aussi nette). Par prudence,
    LES DEUX déclenchent une confirmation humaine ici (pas seulement
    l'envoi comme pour Gmail) — mieux vaut une confirmation en trop que
    risquer un mail parti pour de vrai en pensant créer un brouillon. Si un
    des deux appels échoue en pratique, le message d'erreur inclut la
    réponse brute de Zoho (resp.text) pour corriger vite.

Chaque résultat de recherche encode l'accountId Zoho ET le folderId dans
son `id` (format "compte_id::folder_id::message_id", compte_id = id
interne de brain/integrations/store.py) — l'API Zoho a besoin des trois
pour relire un message, contrairement à Gmail où un seul id suffit.

Point d'API découvert à l'usage (donc: vérifié, pas juste supposé) : Zoho
Mail n'est PAS servi sous le domaine générique `api_domain` renvoyé par
l'échange OAuth (celui-là pointe vers `www.zohoapis.<région>`, le gateway
API commun aux autres produits Zoho) — Zoho Mail garde son propre domaine
`mail.zoho.<région>`, reconstruit ici à partir de la région choisie à la
connexion plutôt que depuis la réponse OAuth.
"""
from __future__ import annotations

import requests

from brain.integrations import confirm, settings, store, zoho_oauth

SERVICE_TYPE = "zoho_mail"
SCOPE = "ZohoMail.accounts.READ,ZohoMail.messages.READ,ZohoMail.messages.CREATE"

_REF_SEP = "::"


def configured() -> bool:
    return zoho_oauth.configured()


def build_auth_url() -> str:
    return zoho_oauth.build_auth_url(SERVICE_TYPE, SCOPE)


def _mail_domain(region: str) -> str:
    return f"https://mail.zoho.{region}"


def _fetch_account_info(access_token: str, _generic_api_domain: str) -> tuple[str, dict]:
    # _generic_api_domain (zohoapis.<région>, renvoyé par l'échange OAuth)
    # n'est PAS le bon hôte pour Zoho Mail — voir note d'en-tête. On
    # reconstruit le domaine Mail à partir de la région réglée dans la
    # Console, seule source fiable ici.
    _, _, region = settings.get_zoho_credentials()
    resp = requests.get(
        f"{_mail_domain(region)}/api/accounts", headers={"Authorization": f"Zoho-oauthtoken {access_token}"}, timeout=10,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Impossible de lister les comptes Zoho Mail : {resp.text[:300]}")
    accounts = resp.json().get("data", [])
    if not accounts:
        raise RuntimeError("Aucun compte Zoho Mail trouvé pour ce jeton, Monsieur.")
    acc = accounts[0]
    email = acc.get("primaryEmailAddress") or (acc.get("mailIds") or [{}])[0].get("mailId", "compte Zoho")
    return email, {"account_id": str(acc.get("accountId"))}


def handle_callback(code: str) -> dict:
    return zoho_oauth.handle_callback(SERVICE_TYPE, code, _fetch_account_info)


def _headers(account: dict) -> dict:
    return {"Authorization": f"Zoho-oauthtoken {zoho_oauth.access_token_for(account)}"}


def _api_domain(account: dict) -> str:
    region = account.get("extra", {}).get("region", "com")
    return _mail_domain(region)


def _zoho_account_id(account: dict) -> str:
    return account.get("extra", {}).get("account_id", "")


def _messages_for_account(account: dict, query: str | None, limit: int) -> list[dict]:
    api_domain = _api_domain(account)
    zoho_id = _zoho_account_id(account)
    if query:
        url = f"{api_domain}/api/accounts/{zoho_id}/messages/search"
        params = {"searchKey": query, "limit": limit}
    else:
        url = f"{api_domain}/api/accounts/{zoho_id}/messages/view"
        params = {"limit": limit}
    resp = requests.get(url, headers=_headers(account), params=params, timeout=10)
    if resp.status_code != 200:
        raise RuntimeError(f"{resp.status_code} : {resp.text[:200]}")
    messages = []
    for item in resp.json().get("data", []):
        folder_id = item.get("folderId", "")
        ref = f"{account['id']}{_REF_SEP}{folder_id}{_REF_SEP}{item.get('messageId', '')}"
        messages.append({
            "id": ref,
            "account": account["label"],
            "from": item.get("sender", ""),
            "subject": item.get("subject") or "(sans objet)",
            "date": item.get("receivedTime", ""),
            "snippet": item.get("summary", ""),
        })
    return messages


def search(query: str | None = None, limit: int = 10) -> list[dict]:
    """Messages de tous les comptes Zoho connectés correspondant à `query`
    (recherche Zoho native), ou les plus récents si vide. Un compte en
    erreur n'empêche pas les autres."""
    all_messages: list[dict] = []
    for account in store.list_for(SERVICE_TYPE):
        try:
            all_messages.extend(_messages_for_account(account, query, limit))
        except Exception as exc:
            all_messages.append({
                "id": None, "account": account["label"], "from": "", "subject": f"[erreur : {exc}]",
                "date": "", "snippet": "",
            })
    return all_messages[:limit]


def _parse_ref(ref: str) -> tuple[dict, str, str] | None:
    parts = ref.split(_REF_SEP)
    if len(parts) != 3:
        return None
    account_store_id, folder_id, message_id = parts
    account = next((a for a in store.list_for(SERVICE_TYPE) if a["id"] == account_store_id), None)
    if not account:
        return None
    return account, folder_id, message_id


def read_message(ref: str, max_chars: int = 12000) -> dict:
    """Contenu complet d'un message par son `id` (tel que retourné par
    search() — ne pas reconstruire ce ref à la main)."""
    parsed = _parse_ref(ref)
    if not parsed:
        return {"error": "Id de message Zoho invalide ou mal formé, Monsieur — utilise exactement celui retourné par zoho_search."}
    account, folder_id, message_id = parsed
    api_domain = _api_domain(account)
    zoho_id = _zoho_account_id(account)
    resp = requests.get(
        f"{api_domain}/api/accounts/{zoho_id}/folders/{folder_id}/messages/{message_id}/content",
        headers=_headers(account), timeout=10,
    )
    if resp.status_code != 200:
        return {"error": f"Lecture refusée par Zoho ({resp.status_code}) : {resp.text[:200]}"}
    data = resp.json().get("data", {})
    content = data.get("content", "")
    if isinstance(content, str) and "<" in content and ">" in content:
        import re
        content = re.sub(r"<[^>]+>", " ", content)
        content = re.sub(r"\s+", " ", content).strip()
    return {
        "from": data.get("sender", ""), "subject": data.get("subject") or "(sans objet)",
        "date": data.get("receivedTime", ""), "text": content[:max_chars],
        "truncated": len(content) > max_chars,
    }


def create_draft(to: str, subject: str, body: str, account_hint: str | None = None) -> dict:
    """Compose un message via l'API Zoho — voir l'avertissement en tête de
    fichier : confirmation humaine ICI AUSSI (pas seulement à l'envoi),
    parce que la frontière exacte brouillon/envoi de l'API Zoho n'est pas
    garantie côté code. Le résumé de confirmation le dit explicitement."""
    accounts = store.list_for(SERVICE_TYPE)
    if account_hint:
        accounts = [a for a in accounts if account_hint.lower() in a["label"].lower()] or accounts
    if not accounts:
        return {"error": "Aucun compte Zoho Mail connecté, Monsieur."}
    account = accounts[0]

    summary = (
        f"Composer un mail « {subject} » à {to} depuis {account['label']} (Zoho Mail) — "
        f"l'API Zoho ne garantit pas de rester un brouillon, il peut partir directement."
    )
    if not confirm.request(summary):
        return {"error": "Composition refusée par Monsieur ou confirmation expirée, Monsieur."}

    api_domain = _api_domain(account)
    zoho_id = _zoho_account_id(account)
    resp = requests.post(
        f"{api_domain}/api/accounts/{zoho_id}/messages",
        headers=_headers(account),
        json={"fromAddress": account["label"], "toAddress": to, "subject": subject, "content": body, "mailFormat": "plaintext"},
        timeout=10,
    )
    if resp.status_code not in (200, 201):
        return {"error": f"Refusé par Zoho ({resp.status_code}) : {resp.text[:200]}"}
    data = resp.json().get("data", {})
    return {"to": to, "subject": subject, "account": account["label"], "raw": data}

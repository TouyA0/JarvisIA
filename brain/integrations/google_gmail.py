"""Intégration Gmail — même schéma que google_calendar.py/google_drive.py,
mécanique OAuth partagée via google_oauth.py.

Scope : gmail.readonly (lecture) + gmail.compose (créer/lire des brouillons
ET les envoyer — Google ne propose pas de scope "brouillon sans envoi").
Cohérent avec la politique du projet : lecture et brouillon sans friction,
mais gmail_send passe systématiquement par brain/integrations/confirm.py —
jamais d'email parti sans qu'un humain ait vu le contenu exact à l'écran.

Gmail structure ses messages en MIME (RFC 2822) encodé base64url — ce
module construit/décode ça avec le strict stdlib (email.mime, base64),
aucune dépendance de plus.
"""
from __future__ import annotations

import base64
from email.mime.text import MIMEText

import requests

from brain.integrations import confirm, google_oauth, store

SERVICE_TYPE = "gmail"
SCOPE = "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.compose"
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"


def configured() -> bool:
    return google_oauth.configured()


def build_auth_url() -> str:
    return google_oauth.build_auth_url(SERVICE_TYPE, SCOPE)


def _fetch_account_email(access_token: str) -> str:
    resp = requests.get(
        f"{GMAIL_API}/profile", headers={"Authorization": f"Bearer {access_token}"}, timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("emailAddress", "compte Google")


def handle_callback(code: str) -> dict:
    return google_oauth.handle_callback(SERVICE_TYPE, code, _fetch_account_email)


def _b64url_decode(data: str) -> bytes:
    # Gmail encode en base64url sans padding — Python exige un padding
    # multiple de 4, on le complète avant de décoder.
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded)


def _header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def _messages_for_account(account: dict, query: str | None, limit: int) -> list[dict]:
    access_token = google_oauth.access_token_for(account)
    resp = requests.get(
        f"{GMAIL_API}/messages",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"q": query or "", "maxResults": limit},
        timeout=10,
    )
    resp.raise_for_status()
    ids = [m["id"] for m in resp.json().get("messages", [])]

    messages = []
    for msg_id in ids:
        detail = requests.get(
            f"{GMAIL_API}/messages/{msg_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"format": "metadata", "metadataHeaders": ["Subject", "From", "Date"]},
            timeout=10,
        )
        if detail.status_code != 200:
            continue
        data = detail.json()
        headers = data.get("payload", {}).get("headers", [])
        messages.append({
            "id": msg_id,
            "account": account["label"],
            "from": _header(headers, "From"),
            "subject": _header(headers, "Subject") or "(sans objet)",
            "date": _header(headers, "Date"),
            "snippet": data.get("snippet", ""),
            "unread": "UNREAD" in data.get("labelIds", []),
        })
    return messages


def search(query: str | None = None, account_id: str | None = None, limit: int = 10) -> list[dict]:
    """Messages de tous les comptes connectés (ou un seul) correspondant à
    `query` — syntaxe de recherche Gmail native (is:unread, from:x, subject:x,
    newer_than:7d, has:attachment…). Vide = messages récents (boîte de
    réception). Fusionnés, triés par ordre Gmail (déjà pertinence/date),
    tronqués à `limit`. Un compte en erreur n'empêche pas les autres."""
    accounts = store.list_for(SERVICE_TYPE)
    if account_id:
        accounts = [a for a in accounts if a["id"] == account_id]

    all_messages: list[dict] = []
    for account in accounts:
        try:
            all_messages.extend(_messages_for_account(account, query, limit))
        except Exception as exc:
            all_messages.append({
                "id": None, "account": account["label"], "from": "", "subject": f"[erreur : {exc}]",
                "date": "", "snippet": "", "unread": False,
            })
    return all_messages[:limit]


def _find_owning_account(message_id: str) -> tuple[dict, dict] | None:
    """Même logique que google_drive._find_owning_account : un id Gmail
    n'indique pas de lui-même quel compte connecté y a accès."""
    for account in store.list_for(SERVICE_TYPE):
        access_token = google_oauth.access_token_for(account)
        resp = requests.get(
            f"{GMAIL_API}/messages/{message_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"format": "full"}, timeout=10,
        )
        if resp.status_code == 200:
            return account, resp.json()
    return None


def _extract_body(payload: dict, max_chars: int) -> str:
    """Parcourt l'arbre MIME à la recherche d'une partie text/plain — se
    rabat sur text/html (tags grossièrement retirés) si aucune n'existe."""
    def walk(part: dict) -> tuple[str | None, str | None]:
        mime = part.get("mimeType", "")
        body = part.get("body", {})
        if mime == "text/plain" and body.get("data"):
            return _b64url_decode(body["data"]).decode("utf-8", errors="replace"), None
        if mime == "text/html" and body.get("data"):
            html = _b64url_decode(body["data"]).decode("utf-8", errors="replace")
            return None, html
        plain_found, html_found = None, None
        for sub in part.get("parts", []) or []:
            p, h = walk(sub)
            plain_found = plain_found or p
            html_found = html_found or h
        return plain_found, html_found

    plain, html = walk(payload)
    if plain:
        return plain[:max_chars]
    if html:
        import re
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:max_chars]
    return ""


def read_message(message_id: str, max_chars: int = 12000) -> dict:
    """Contenu complet d'un message (sujet, expéditeur, corps texte) par son
    id (tel que retourné par search()). {"error": "..."} si introuvable."""
    found = _find_owning_account(message_id)
    if not found:
        return {"error": "Message introuvable dans les comptes Gmail connectés, Monsieur — vérifie l'id."}
    _, data = found
    headers = data.get("payload", {}).get("headers", [])
    text = _extract_body(data.get("payload", {}), max_chars)
    return {
        "from": _header(headers, "From"),
        "to": _header(headers, "To"),
        "subject": _header(headers, "Subject") or "(sans objet)",
        "date": _header(headers, "Date"),
        "text": text or "(corps vide ou non lisible en texte — pièce jointe seule ?)",
        "truncated": len(text) >= max_chars,
    }


def create_draft(to: str, subject: str, body: str, account_hint: str | None = None, reply_to_id: str | None = None) -> dict:
    """Crée un brouillon — jamais envoyé automatiquement, pas de
    confirmation nécessaire ici (un brouillon ne part nulle part, Monsieur
    le relit forcément avant gmail_send). Si `reply_to_id` est fourni, le
    brouillon rejoint le même fil de discussion."""
    accounts = store.list_for(SERVICE_TYPE)
    if account_hint:
        accounts = [a for a in accounts if account_hint.lower() in a["label"].lower()] or accounts
    if not accounts:
        return {"error": "Aucun compte Gmail connecté, Monsieur."}
    account = accounts[0]
    access_token = google_oauth.access_token_for(account)

    thread_id = None
    if reply_to_id:
        found = _find_owning_account(reply_to_id)
        if found:
            _, original = found
            headers = original.get("payload", {}).get("headers", [])
            thread_id = original.get("threadId")
            if not subject:
                orig_subject = _header(headers, "Subject")
                subject = orig_subject if orig_subject.lower().startswith("re:") else f"Re: {orig_subject}"

    mime = MIMEText(body, "plain", "utf-8")
    mime["To"] = to
    mime["Subject"] = subject
    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode("ascii").rstrip("=")

    payload = {"message": {"raw": raw}}
    if thread_id:
        payload["message"]["threadId"] = thread_id

    resp = requests.post(
        f"{GMAIL_API}/drafts", headers={"Authorization": f"Bearer {access_token}"}, json=payload, timeout=10,
    )
    if resp.status_code != 200:
        return {"error": f"Création du brouillon refusée par Google ({resp.status_code}), Monsieur."}
    draft = resp.json()
    return {"draft_id": draft["id"], "to": to, "subject": subject, "account": account["label"]}


def send_draft(draft_id: str) -> dict:
    """Envoie un brouillon existant — confirmation humaine obligatoire,
    sans exception : c'est la seule action de ce module qui quitte
    définitivement le compte de Monsieur."""
    for account in store.list_for(SERVICE_TYPE):
        access_token = google_oauth.access_token_for(account)
        get_resp = requests.get(
            f"{GMAIL_API}/drafts/{draft_id}", headers={"Authorization": f"Bearer {access_token}"},
            params={"format": "metadata"}, timeout=10,
        )
        if get_resp.status_code != 200:
            continue
        draft = get_resp.json()
        headers = draft.get("message", {}).get("payload", {}).get("headers", [])
        to = _header(headers, "To")
        subject = _header(headers, "Subject") or "(sans objet)"

        summary = f"Envoyer le mail « {subject} » à {to} depuis {account['label']}, Monsieur — action irréversible."
        if not confirm.request(summary):
            return {"error": "Envoi refusé par Monsieur ou confirmation expirée, Monsieur."}

        send_resp = requests.post(
            f"{GMAIL_API}/drafts/send", headers={"Authorization": f"Bearer {access_token}"},
            json={"id": draft_id}, timeout=10,
        )
        if send_resp.status_code != 200:
            return {"error": f"Envoi refusé par Google ({send_resp.status_code}), Monsieur."}
        return {"to": to, "subject": subject}

    return {"error": "Brouillon introuvable dans les comptes Gmail connectés, Monsieur."}

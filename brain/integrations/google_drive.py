"""Intégration Google Drive — même schéma que google_calendar.py, mécanique
OAuth partagée via google_oauth.py.

Scope : `drive` (lecture ET écriture) — nécessaire pour que create/update/
trash puissent porter sur n'importe quel fichier trouvé par search(), pas
seulement ceux créés par Jarvis (ce que limiterait le scope plus étroit
`drive.file`). En contrepartie, toute écriture passe par
brain/integrations/confirm.py (confirmation humaine bloquante depuis la
Console web) — la largeur du scope OAuth n'est pas la barrière de sécurité,
la confirmation l'est, exactement comme run_powershell côté desktop a accès
à tout PowerShell mais confirme les commandes destructrices.

Si un compte a été connecté avant ce changement (scope `drive.readonly`
seul), son jeton n'a pas les droits d'écriture : le reconnecter depuis
Intégrations (même bouton, un nouveau consentement redemande le bon scope).

En plus de la recherche (search), ce module sait extraire le texte d'un
fichier trouvé (read_file) : Docs/Sheets/Slides Google (export natif),
PDF (pypdf), texte brut — de quoi répondre à « résume-moi le fichier X »
sans que Monsieur ait à l'ouvrir lui-même. Le lien `webViewLink` retourné
par search() reste utilisable tel quel avec le tool PC open_url si Monsieur
veut l'ouvrir dans un onglet.
"""
from __future__ import annotations

import io

import requests
from pypdf import PdfReader

from brain.integrations import confirm, google_oauth, store

SERVICE_TYPE = "google_drive"
SCOPE = "https://www.googleapis.com/auth/drive"
DRIVE_API = "https://www.googleapis.com/drive/v3"
DRIVE_UPLOAD_API = "https://www.googleapis.com/upload/drive/v3/files"

_FIELDS = "files(id,name,mimeType,modifiedTime,webViewLink,size)"

# Exports natifs Google (Docs/Sheets/Slides n'ont pas de "contenu brut" : il
# faut demander une conversion) — texte pour Docs/Slides, CSV pour Sheets
# (l'API Drive n'exporte que la 1re feuille en CSV, limite acceptée ici).
_GOOGLE_EXPORT_MIME = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.presentation": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
}
# Types dont le contenu se télécharge tel quel (alt=media) et se décode en
# UTF-8 directement, sans conversion.
_PLAIN_TEXT_PREFIXES = ("text/", "application/json")

_MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024  # 20 Mo — au-delà, autant ouvrir le lien


def configured() -> bool:
    return google_oauth.configured()


def build_auth_url() -> str:
    return google_oauth.build_auth_url(SERVICE_TYPE, SCOPE)


def _fetch_account_email(access_token: str) -> str:
    resp = requests.get(
        f"{DRIVE_API}/about", headers={"Authorization": f"Bearer {access_token}"},
        params={"fields": "user"}, timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("user", {}).get("emailAddress", "compte Google")


def handle_callback(code: str) -> dict:
    return google_oauth.handle_callback(SERVICE_TYPE, code, _fetch_account_email)


def _escape_query_term(term: str) -> str:
    # Syntaxe de requête Drive : les apostrophes dans une valeur littérale
    # doivent être échappées avec un backslash, sinon la requête casse.
    return term.replace("\\", "\\\\").replace("'", "\\'")


def _files_for_account(account: dict, query: str | None, limit: int) -> list[dict]:
    access_token = google_oauth.access_token_for(account)
    if query:
        term = _escape_query_term(query)
        q = f"(name contains '{term}' or fullText contains '{term}') and trashed = false"
    else:
        q = "trashed = false"
    resp = requests.get(
        f"{DRIVE_API}/files",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"q": q, "orderBy": "modifiedTime desc", "pageSize": limit, "fields": _FIELDS},
        timeout=10,
    )
    resp.raise_for_status()
    files = []
    for item in resp.json().get("files", []):
        files.append({
            "id": item.get("id"),
            "account": account["label"],
            "name": item.get("name", "(sans nom)"),
            "mime_type": item.get("mimeType", ""),
            "modified_time": item.get("modifiedTime"),
            "link": item.get("webViewLink"),
        })
    return files


def search(query: str | None = None, account_id: str | None = None, limit: int = 10) -> list[dict]:
    """Fichiers de tous les comptes connectés (ou un seul) correspondant à
    `query` (nom ou contenu), ou les plus récemment modifiés si `query` est
    vide. Fusionnés, triés par date de modification décroissante, tronqués
    à `limit`. Un compte en erreur (jeton expiré) n'empêche pas les autres,
    comme pour le calendrier."""
    accounts = store.list_for(SERVICE_TYPE)
    if account_id:
        accounts = [a for a in accounts if a["id"] == account_id]

    all_files: list[dict] = []
    for account in accounts:
        try:
            all_files.extend(_files_for_account(account, query, limit))
        except Exception as exc:
            all_files.append({
                "id": None, "account": account["label"], "name": f"[erreur : {exc}]",
                "mime_type": "", "modified_time": None, "link": None,
            })
    all_files.sort(key=lambda f: f["modified_time"] or "", reverse=True)
    return all_files[:limit]


def _find_owning_account(file_id: str) -> tuple[dict, dict] | None:
    """Un file_id Drive n'indique pas de lui-même quel compte connecté y a
    accès — on essaie chaque compte jusqu'à ce qu'un accepte (généralement
    1 à 3 comptes, donc négligeable en pratique). Retourne (compte,
    métadonnées) ou None si aucun compte connecté n'y a accès."""
    for account in store.list_for(SERVICE_TYPE):
        access_token = google_oauth.access_token_for(account)
        resp = requests.get(
            f"{DRIVE_API}/files/{file_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"fields": "id,name,mimeType,size"},
            timeout=10,
        )
        if resp.status_code == 200:
            return account, resp.json()
    return None


def _extract_pdf_text(raw: bytes, max_chars: int) -> str:
    reader = PdfReader(io.BytesIO(raw))
    parts = []
    total = 0
    for page in reader.pages:
        text = page.extract_text() or ""
        parts.append(text)
        total += len(text)
        if total >= max_chars:
            break
    return "\n".join(parts)


def read_file(file_id: str, max_chars: int = 12000) -> dict:
    """Extrait le texte d'un fichier Drive par son id (tel que retourné par
    search()). Gère les Docs/Sheets/Slides Google (export natif), le PDF
    (pypdf) et le texte brut. Retourne {"name","mime_type","text","truncated"}
    ou {"error": "..."} si le fichier est introuvable/illisible/trop gros."""
    found = _find_owning_account(file_id)
    if not found:
        return {"error": "Fichier introuvable dans les comptes Drive connectés, Monsieur — vérifie l'id."}
    account, meta = found
    name = meta.get("name", "(sans nom)")
    mime_type = meta.get("mimeType", "")
    size = int(meta.get("size") or 0)
    access_token = google_oauth.access_token_for(account)

    if mime_type in _GOOGLE_EXPORT_MIME:
        export_mime = _GOOGLE_EXPORT_MIME[mime_type]
        resp = requests.get(
            f"{DRIVE_API}/files/{file_id}/export",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"mimeType": export_mime}, timeout=20,
        )
        if resp.status_code != 200:
            return {"error": f"Export impossible pour {name} ({resp.status_code}), Monsieur."}
        text = resp.content.decode("utf-8", errors="replace")

    elif mime_type == "application/pdf":
        if size > _MAX_DOWNLOAD_BYTES:
            return {"error": f"{name} fait {size // 1_048_576} Mo, trop volumineux à lire directement — ouvre-le avec open_url, Monsieur."}
        resp = requests.get(
            f"{DRIVE_API}/files/{file_id}", headers={"Authorization": f"Bearer {access_token}"},
            params={"alt": "media"}, timeout=30,
        )
        if resp.status_code != 200:
            return {"error": f"Téléchargement impossible pour {name} ({resp.status_code}), Monsieur."}
        try:
            text = _extract_pdf_text(resp.content, max_chars)
        except Exception as exc:
            return {"error": f"PDF illisible ({exc}), Monsieur — ouvre-le avec open_url."}
        if not text.strip():
            return {"error": f"{name} semble être un PDF scanné sans texte extractible (image), Monsieur — ouvre-le avec open_url."}

    elif mime_type.startswith(_PLAIN_TEXT_PREFIXES):
        if size > _MAX_DOWNLOAD_BYTES:
            return {"error": f"{name} fait {size // 1_048_576} Mo, trop volumineux à lire directement — ouvre-le avec open_url, Monsieur."}
        resp = requests.get(
            f"{DRIVE_API}/files/{file_id}", headers={"Authorization": f"Bearer {access_token}"},
            params={"alt": "media"}, timeout=20,
        )
        if resp.status_code != 200:
            return {"error": f"Téléchargement impossible pour {name} ({resp.status_code}), Monsieur."}
        text = resp.content.decode("utf-8", errors="replace")

    else:
        return {"error": f"{name} est un fichier {mime_type or 'de type inconnu'}, pas lisible comme texte — ouvre-le avec open_url, Monsieur."}

    truncated = len(text) > max_chars
    return {"name": name, "mime_type": mime_type, "text": text[:max_chars], "truncated": truncated}


def _pick_account(account_hint: str | None) -> dict | None:
    """Compte à utiliser pour une écriture qui ne porte pas sur un fichier
    existant (create) : `account_hint` filtre par sous-chaîne de l'adresse
    (si Monsieur a nommé un compte), sinon le premier connecté — la plupart
    des configurations n'en ont qu'un, et create() le dit explicitement
    dans le résumé de confirmation pour que ça reste vérifiable."""
    accounts = store.list_for(SERVICE_TYPE)
    if account_hint:
        accounts = [a for a in accounts if account_hint.lower() in a["label"].lower()] or accounts
    return accounts[0] if accounts else None


def create_file(name: str, content: str, account_hint: str | None = None, mime_type: str = "text/plain") -> dict:
    """Crée un nouveau fichier texte dans Drive. Confirmation humaine
    obligatoire (voir confirm.py) — jamais d'écriture silencieuse."""
    account = _pick_account(account_hint)
    if not account:
        return {"error": "Aucun compte Google Drive connecté, Monsieur."}

    summary = f"Créer le fichier « {name} » sur Google Drive ({account['label']}) — {len(content)} caractères."
    if not confirm.request(summary):
        return {"error": "Création refusée par Monsieur ou confirmation expirée, Monsieur."}

    access_token = google_oauth.access_token_for(account)
    resp = requests.post(
        f"{DRIVE_API}/files", headers={"Authorization": f"Bearer {access_token}"},
        params={"fields": "id,name,webViewLink"}, json={"name": name}, timeout=10,
    )
    if resp.status_code != 200:
        return {"error": f"Création refusée par Google ({resp.status_code}), Monsieur."}
    created = resp.json()

    upload = requests.patch(
        f"{DRIVE_UPLOAD_API}/{created['id']}", headers={"Authorization": f"Bearer {access_token}", "Content-Type": mime_type},
        params={"uploadType": "media"}, data=content.encode("utf-8"), timeout=20,
    )
    if upload.status_code != 200:
        return {"error": f"Fichier créé mais contenu non écrit ({upload.status_code}), Monsieur — vide sur Drive."}

    return {"name": created["name"], "link": created.get("webViewLink")}


def update_file(file_id: str, content: str, mime_type: str | None = None) -> dict:
    """Remplace ENTIÈREMENT le contenu d'un fichier existant (pas de fusion
    ni d'ajout — écrase). Confirmation humaine obligatoire."""
    found = _find_owning_account(file_id)
    if not found:
        return {"error": "Fichier introuvable dans les comptes Drive connectés, Monsieur — vérifie l'id."}
    account, meta = found
    name = meta.get("name", "(sans nom)")
    effective_mime = mime_type or meta.get("mimeType") or "text/plain"
    if effective_mime in _GOOGLE_EXPORT_MIME:
        return {"error": f"{name} est un document Google natif (Docs/Sheets/Slides) — l'édition de contenu n'est pas prise en charge pour ce type, Monsieur."}

    summary = f"Remplacer le contenu de « {name} » sur Google Drive ({account['label']}) — {len(content)} caractères, écrase le contenu actuel."
    if not confirm.request(summary):
        return {"error": "Modification refusée par Monsieur ou confirmation expirée, Monsieur."}

    access_token = google_oauth.access_token_for(account)
    resp = requests.patch(
        f"{DRIVE_UPLOAD_API}/{file_id}", headers={"Authorization": f"Bearer {access_token}", "Content-Type": effective_mime},
        params={"uploadType": "media"}, data=content.encode("utf-8"), timeout=20,
    )
    if resp.status_code != 200:
        return {"error": f"Écriture refusée par Google ({resp.status_code}), Monsieur."}
    return {"name": name}


def trash_file(file_id: str) -> dict:
    """Déplace un fichier vers la corbeille Drive — JAMAIS de suppression
    définitive (files.delete) : la corbeille reste récupérable ~30 jours
    côté Google, une marge de sécurité qu'une suppression directe n'offrirait
    pas. Confirmation humaine obligatoire."""
    found = _find_owning_account(file_id)
    if not found:
        return {"error": "Fichier introuvable dans les comptes Drive connectés, Monsieur — vérifie l'id."}
    account, meta = found
    name = meta.get("name", "(sans nom)")

    summary = f"Mettre « {name} » à la corbeille sur Google Drive ({account['label']}) — récupérable ~30 jours depuis Drive."
    if not confirm.request(summary):
        return {"error": "Suppression refusée par Monsieur ou confirmation expirée, Monsieur."}

    access_token = google_oauth.access_token_for(account)
    resp = requests.patch(
        f"{DRIVE_API}/files/{file_id}", headers={"Authorization": f"Bearer {access_token}"},
        json={"trashed": True}, timeout=10,
    )
    if resp.status_code != 200:
        return {"error": f"Suppression refusée par Google ({resp.status_code}), Monsieur."}
    return {"name": name}

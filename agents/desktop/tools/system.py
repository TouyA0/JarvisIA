"""Outils système : PowerShell, fichiers, presse-papier."""
from __future__ import annotations

import os
import subprocess

from agents.desktop import config, state
from agents.desktop.tools.safety import is_destructive_command, wrap_untrusted


def _confirm_destructive(command: str) -> bool:
    """Bloque jusqu'à la décision de Monsieur. Timeout, fermeture, ou
    interruption vocale déjà en cours → refus par défaut.

    Utilise tts.speak(), pas la version avec écouteur d'interruption : cette
    fonction est appelée depuis l'intérieur de la boucle d'outils, déjà
    couverte par l'écouteur démarré par le runtime. Un second écouteur lirait
    le même flux micro en parallèle et couperait prématurément le premier.
    """
    if state.stop_agent.is_set() or state.stop_speaking.is_set():
        return False

    from agents.desktop.ui import dialogs
    from agents.desktop.ui.hud import overlay
    from agents.desktop.audio import tts

    # Ouvrir le dialogue D'ABORD, parler pendant qu'il est à l'écran, puis
    # attendre la décision — sinon la bulle n'apparaîtrait qu'après la phrase.
    holder = dialogs.open_confirm(command)
    if not overlay.is_muted():
        tts.speak("Cette action est irréversible, Monsieur. Confirmation requise à l'écran.")
    approved = dialogs.wait_confirm(holder, timeout=30)
    return approved and not state.stop_agent.is_set()


def run_powershell(command: str, force_confirm: bool = False) -> str:
    # force_confirm=True quand une donnée non fiable (OCR, contenu de fichier,
    # URL, capture d'écran) a été lue plus tôt dans le même tour : une page web
    # ou un document piégé qui contiendrait des instructions ne doit jamais
    # pouvoir déclencher du PowerShell sans qu'un humain n'approuve la commande.
    if force_confirm or is_destructive_command(command):
        if not _confirm_destructive(command):
            return "Commande refusée par Monsieur ou confirmation expirée. Aucune action effectuée."
    try:
        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-Command", command],
            capture_output=True, timeout=config.SHORT_REQUEST_TIMEOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            stdout = result.stdout.decode("utf-8").strip()
            stderr = result.stderr.decode("utf-8").strip()
        except UnicodeDecodeError:
            stdout = result.stdout.decode("cp1252", errors="replace").strip()
            stderr = result.stderr.decode("cp1252", errors="replace").strip()
        output = stdout or stderr or "Commande exécutée."
        return output[:2000]
    except subprocess.TimeoutExpired:
        return "Timeout : commande trop longue."
    except Exception as e:
        return f"Erreur PowerShell : {e}"


def read_clipboard() -> str:
    """Lit le presse-papier (contenu non fiable : peut venir du web)."""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
            capture_output=True, timeout=config.SHORT_REQUEST_TIMEOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        text = result.stdout.decode("utf-8", errors="replace").strip()
        if not text:
            return "Le presse-papier est vide."
        return wrap_untrusted(text[:3000])
    except Exception as e:
        return f"Erreur lecture presse-papier : {e}"


def write_clipboard(text: str) -> str:
    """Écrit dans le presse-papier local — utilisé pour coller le contenu
    reçu du presse-papier partagé (voir brain/clipboard.py, share_clipboard/
    get_shared_clipboard) directement prêt pour un Ctrl+V.

    Passe par base64 (pas d'argument -Command en clair) : le texte peut
    contenir guillemets, accents, backticks — aucun risque d'injection ou
    d'échappement cassé côté PowerShell.
    """
    text = text.strip()
    if not text:
        return "Rien à écrire dans le presse-papier."
    import base64
    b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
    ps = f"[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{b64}')) | Set-Clipboard"
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, timeout=config.SHORT_REQUEST_TIMEOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return "Collé dans le presse-papier, Monsieur."
    except Exception as e:
        return f"Erreur écriture presse-papier : {e}"


def search_file(name: str, location: str | None = None) -> str:
    if not location:
        location = os.path.expanduser("~")
    # Sanitize pour éviter l'injection dans la commande
    name_safe = name.replace("'", "").replace('"', "")[:80]
    location_safe = location.replace("'", "").replace('"', "")[:200]
    ps = (f"Get-ChildItem -Path '{location_safe}' -Recurse -ErrorAction SilentlyContinue "
          f"| Where-Object {{ $_.Name -like '*{name_safe}*' }} "
          f"| Select-Object -First 15 -ExpandProperty FullName")
    try:
        result = subprocess.run(
            ["powershell", "-command", ps],
            capture_output=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        output = result.stdout.decode("utf-8", errors="replace").strip()
        if output:
            return f"Fichiers trouvés :\n{output}"
        return f"Aucun fichier '{name}' trouvé dans {location}."
    except Exception as e:
        return f"Erreur recherche fichier : {e}"


def open_file(path: str) -> str:
    path = path.strip().strip('"').strip("'")
    try:
        os.startfile(path)
        return f"Ouvert : {os.path.basename(path)}, Monsieur."
    except Exception as e:
        try:
            subprocess.run(["powershell", f"Invoke-Item '{path}'"],
                           capture_output=True, timeout=5,
                           creationflags=subprocess.CREATE_NO_WINDOW)
            return "Fichier ouvert, Monsieur."
        except Exception:
            return f"Erreur ouverture fichier : {e}"


def list_folder(path: str) -> str:
    path = path.strip().strip('"').strip("'")
    try:
        if not os.path.exists(path):
            return f"Dossier '{path}' introuvable."
        items = os.listdir(path)
        folders = sorted(f"[D] {i}" for i in items if os.path.isdir(os.path.join(path, i)))
        files = sorted(f"[F] {i}" for i in items if os.path.isfile(os.path.join(path, i)))
        all_items = folders + files
        header = f"Contenu de {path} ({len(all_items)} éléments) :\n"
        return header + "\n".join(all_items[:60])
    except Exception as e:
        return f"Erreur liste dossier : {e}"


def read_file_content(path: str, max_lines: int = 100) -> str:
    path = path.strip().strip('"').strip("'")
    try:
        if not os.path.exists(path):
            return f"Fichier '{path}' introuvable."
        size = os.path.getsize(path)
        if size > 500_000:
            return f"Fichier trop volumineux ({size // 1024}KB). Utilisez un éditeur, Monsieur."
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        note = f"[{len(lines)} lignes au total, {max_lines} affichées]\n" if len(lines) > max_lines else ""
        return wrap_untrusted(note + "".join(lines[:max_lines]))
    except Exception as e:
        return f"Erreur lecture fichier : {e}"

"""Outils écran : capture avec vision réelle, OCR, URL du navigateur.

Nouveauté v2 : take_screenshot retourne l'IMAGE elle-même (JPEG réduit,
base64) en plus du texte — Claude Haiku est multimodal, il voit donc
réellement l'écran au lieu d'une simple liste de titres de fenêtres.
"""
from __future__ import annotations

import base64
import io
import os
import subprocess

from agents.desktop.tools.safety import wrap_untrusted

# Largeur maxi de l'image envoyée à Claude — 1568 px correspond au seuil
# documenté par Anthropic au-delà duquel Claude ne gagne plus rien en
# précision (l'image est redimensionnée côté API de toute façon), donc pas
# de perte de qualité côté vision à monter jusque-là.
_MAX_IMAGE_WIDTH = 1568
# Qualité JPEG : le coût en tokens de vision de Claude dépend des DIMENSIONS
# de l'image, pas de sa compression — remonter la qualité est donc gratuit
# côté API. 60 rendait le texte flou à l'écran une fois affiché en grand
# dans une carte (voir docs/ROADMAP_DISPLAY_INTEGRATIONS.md, capture
# affichée directement depuis F-screenshot-1) ; 85 reste raisonnable en
# poids pour une action ponctuelle (pas un flux répété — voir capture_frame
# plus bas pour ce cas-là).
_JPEG_QUALITY = 85


def take_screenshot() -> dict:
    """Capture l'écran ; retourne texte descriptif + image encodée pour Claude."""
    try:
        import pyautogui
        screenshot = pyautogui.screenshot()
        w, h = screenshot.size

        scale = 1.0
        img = screenshot
        if w > _MAX_IMAGE_WIDTH:
            scale = w / _MAX_IMAGE_WIDTH
            img = screenshot.resize((_MAX_IMAGE_WIDTH, int(h / scale)))

        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=_JPEG_QUALITY)
        image_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

        result = subprocess.run(
            ["powershell", "-command",
             "Get-Process | Where-Object {$_.MainWindowTitle} | "
             "Select-Object Name,MainWindowTitle | Format-Table -AutoSize | Out-String"],
            capture_output=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        try:
            windows = result.stdout.decode("utf-8").strip()
        except UnicodeDecodeError:
            windows = result.stdout.decode("cp1252", errors="replace").strip()

        browser_url = get_browser_url()
        url_line = (f"\nURL navigateur actif : {browser_url}"
                    if browser_url and "introuvable" not in browser_url
                    and "Aucun" not in browser_url else "")

        text = (
            f"Capture d'écran jointe (image visible ci-dessus).\n"
            f"Résolution réelle de l'écran : {w}x{h}. "
            f"L'image est réduite d'un facteur {scale:.2f} : pour mouse_click, "
            f"multiplie les coordonnées mesurées sur l'image par {scale:.2f}."
            f"{url_line}\nFenêtres ouvertes :\n{windows[:800]}"
        )
        return {"text": text, "image_b64": image_b64, "media_type": "image/jpeg"}
    except Exception as e:
        return {"text": f"Erreur screenshot : {e}"}


_STREAM_MAX_WIDTH = 1280  # aligné sur take_screenshot depuis que 960/qualité 45
# s'est révélé franchement pixelisé une fois affiché en grand dans Focus.jsx
# (`width: 100%` agrandit une petite image = flou d'upscale, pas juste un
# problème de compression) — la bande passante reste correcte en LAN/local,
# le compromis penche du côté lisibilité.


def capture_frame(quality: int = 65) -> dict:
    """Capture allégée pour le partage d'écran live (voir
    docs/ROADMAP_DISPLAY_INTEGRATIONS.md §4, V1) : juste l'image, sans le
    listage des fenêtres ni la détection d'URL navigateur de
    take_screenshot() — ces deux PowerShell coûtent une bonne partie du
    temps d'une capture et ne servent à rien pour un flux régulier destiné
    à être juste regardé. Jamais exposé à Claude (absent de PC_TOOLS/
    to_claude_tools) : uniquement dispatché directement par
    brain/server.py::stream_frame pour la vue Focus."""
    try:
        import pyautogui
        screenshot = pyautogui.screenshot()
        w, h = screenshot.size
        img = screenshot
        if w > _STREAM_MAX_WIDTH:
            scale = w / _STREAM_MAX_WIDTH
            img = screenshot.resize((_STREAM_MAX_WIDTH, int(h / scale)))
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=quality)
        return {"image_b64": base64.b64encode(buf.getvalue()).decode("ascii"), "media_type": "image/jpeg"}
    except Exception as e:
        return {"text": f"Erreur capture_frame : {e}"}


def read_screen() -> str:
    """OCR Windows natif sur une capture d'écran complète."""
    try:
        import pyautogui
        path = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "jarvis_ocr.png")
        pyautogui.screenshot().save(path)
        ps = r"""
param([string]$imgPath)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType=WindowsRuntime]
$null = [Windows.Media.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime]
function Await($task) { $task.GetAwaiter().GetResult() }
$file   = Await([Windows.Storage.StorageFile]::GetFileFromPathAsync($imgPath))
$stream = Await($file.OpenAsync([Windows.Storage.FileAccessMode]::Read))
$dec    = Await([Windows.Media.Imaging.BitmapDecoder]::CreateAsync($stream))
$bmp    = Await($dec.GetSoftwareBitmapAsync())
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
$res    = Await($engine.RecognizeAsync($bmp))
Write-Output $res.Text
"""
        result = subprocess.run(
            ["powershell", "-command", ps, "-imgPath", path],
            capture_output=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        text = result.stdout.decode("utf-8", errors="replace").strip()
        if text:
            return wrap_untrusted(text[:3000])
        err = result.stderr.decode("utf-8", errors="replace").strip()
        return f"OCR : aucun texte détecté.{' Erreur : ' + err[:200] if err else ''}"
    except Exception as e:
        return f"Erreur read_screen : {e}"


def get_browser_url() -> str:
    ps = r"""
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$procs = @('chrome','firefox','msedge','brave') | ForEach-Object {
    Get-Process -Name $_ -ErrorAction SilentlyContinue
} | Where-Object { $_.MainWindowTitle } | Select-Object -First 1
if (-not $procs) { Write-Output "Aucun navigateur ouvert"; exit }
$desktop = [System.Windows.Automation.AutomationElement]::RootElement
$cond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ProcessIdProperty, $procs.Id)
$win = $desktop.FindFirst([System.Windows.Automation.TreeScope]::Children, $cond)
if (-not $win) { Write-Output "Fenetre introuvable"; exit }
$editCond = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Edit)
$urlBar = $win.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $editCond)
if ($urlBar) {
    $vp = $urlBar.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
    Write-Output $vp.Current.Value
} else { Write-Output "Barre URL introuvable" }
"""
    try:
        result = subprocess.run(
            ["powershell", "-command", ps],
            capture_output=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        url = result.stdout.decode("utf-8", errors="replace").strip() or "URL non trouvée"
        return wrap_untrusted(url)
    except Exception as e:
        return f"Erreur get_browser_url : {e}"

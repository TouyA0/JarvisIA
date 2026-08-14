"""Outils clavier / souris."""
from __future__ import annotations

import base64
import subprocess
import time

from agents.desktop import config


def type_text(text: str) -> str:
    try:
        import pyautogui
        # Passer par le presse-papier pour supporter les accents français.
        # Le texte vient du LLM : il ne doit JAMAIS être interpolé dans la commande.
        # En base64 (alphabet A-Za-z0-9+/=) il ne peut contenir ni guillemet ni $(),
        # donc aucune injection PowerShell n'est possible.
        b64 = base64.b64encode(str(text).encode("utf-16-le")).decode("ascii")
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Set-Clipboard -Value ([Text.Encoding]::Unicode.GetString("
             f"[Convert]::FromBase64String('{b64}')))"],
            capture_output=True, timeout=config.SHORT_REQUEST_TIMEOUT,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        time.sleep(0.1)
        pyautogui.hotkey("ctrl", "v")
        return f"Texte tapé : {text[:80]}"
    except Exception as e:
        return f"Erreur type_text : {e}"


def press_keys(keys: str) -> str:
    try:
        import pyautogui
        parts = [k.strip() for k in keys.lower().split("+")]
        if len(parts) == 1:
            pyautogui.press(parts[0])
        else:
            pyautogui.hotkey(*parts)
        return f"Touches pressées : {keys}"
    except Exception as e:
        return f"Erreur press_keys : {e}"


def mouse_click(x: int, y: int, button: str = "left") -> str:
    try:
        import pyautogui
        # 0.05s : un mouvement plus lent n'a aucune utilité ici et ajoute de la
        # latence perçue à chaque clic de l'agent.
        pyautogui.moveTo(x, y, duration=0.05)
        if button == "double":
            pyautogui.doubleClick()
        elif button == "right":
            pyautogui.rightClick()
        else:
            pyautogui.click()
        return f"Clic {button} à ({x}, {y})"
    except Exception as e:
        return f"Erreur mouse_click : {e}"


def scroll(direction: str, clicks: int = 3) -> str:
    try:
        import pyautogui
        pyautogui.scroll(clicks if direction == "up" else -clicks)
        return f"Défilement {direction}, {clicks} crans"
    except Exception as e:
        return f"Erreur scroll : {e}"


def open_url(url: str) -> str:
    try:
        import webbrowser
        webbrowser.open(url)
        return f"URL ouverte : {url}"
    except Exception as e:
        return f"Erreur open_url : {e}"

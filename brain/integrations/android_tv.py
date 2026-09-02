"""Intégration Android TV / Google TV (stick salon) — ADB réseau direct,
pas d'OAuth ni de compte (voir brain/integrations/store.py) : un seul
appareil, une IP fixe en .env, comme brain/weather.py plutôt que le modèle
multi-comptes de home_assistant.py/jellyfin.py.

Pourquoi ADB plutôt que Home Assistant : l'intégration HA "Android TV
Remote" (androidtv_remote) ne gère pas media_player.select_source de façon
fiable sur ce stick (voir conversation), et ne renvoie que du TEXTE côté
service adb_command — aucune capture d'écran possible. Une connexion ADB
directe (bibliothèque pure Python `adb-shell`, pas de binaire `adb`
nécessaire) donne accès à la totalité de la surface de contrôle : touches,
lancement d'appli par lien profond, ET lecture de l'écran (uiautomator dump
pour une navigation structurée, screencap en dernier recours visuel).

Trois couches, de la plus rapide/fiable à la plus lente/universelle :
  1. send_key/volume/launch_app — instantané, à utiliser en priorité.
  2. ui_dump + tap/type_text — quand aucun lien profond ne marche
     (recherche dans une appli, Disney+…) : Claude lit le XML structuré
     (texte, position, cliquable) et décide où taper, sans avoir besoin de
     "voir" une image.
  3. screenshot — dernier recours si ui_dump ne renvoie rien d'exploitable
     (certaines interfaces "canvas" n'exposent pas d'arborescence
     standard). Renvoie {"image_b64":...} : brain/core/agent.py sait déjà
     transformer ça en bloc image pour Claude (voir _tool_result_content)
     et l'afficher en carte (voir tools.py::execute ici, même schéma que
     brain/vision.py).

Sécurité : ADB donne un accès quasi-shell complet à l'appareil — n'exposer
`ANDROID_TV_HOST` que sur le réseau local, jamais par redirection de port.
Première connexion : l'appareil affiche une popup "Autoriser le débogage
USB ?" à l'écran — à accepter une fois manuellement (télécommande), ensuite
la clé RSA générée ici (ANDROID_TV_ADB_KEY_PATH) est mémorisée par
l'appareil, plus rien à refaire.
"""
from __future__ import annotations

import base64
import re
import threading

from brain import config

_lock = threading.Lock()
_device = None  # AdbDeviceTcp connecté, mis en cache — une seule connexion réutilisée.

# Schémas de lien profond connus (Couche 1) — testés/confirmés fonctionnels
# pour ce stick pendant la mise en place (YouTube, Spotify). Les autres sont
# une meilleure estimation (schéma officiel documenté par l'éditeur) : si un
# nom ne matche rien ici, launch_app() tente quand même de le lancer par nom
# de package Android (best effort), voir _resolve_app().
_APP_SCHEMES = {
    "youtube": "vnd.youtube://",
    "spotify": "spotify://",
    "netflix": "nflx://",
    "disney+": "disneyplus://",
    "disney": "disneyplus://",
    "prime video": "com.amazon.amazonvideo.livingroom",
    "amazon prime": "com.amazon.amazonvideo.livingroom",
}

# Touches autorisées pour send_key — liste blanche volontaire (pas de passe-
# plat vers n'importe quel KEYCODE_* Android) : c'est la même logique de
# "outil borné" que le reste de brain/tools.py, aucune raison de laisser
# Claude viser des touches hors navigation/média.
_KEYCODES = {
    "DPAD_UP": "KEYCODE_DPAD_UP",
    "DPAD_DOWN": "KEYCODE_DPAD_DOWN",
    "DPAD_LEFT": "KEYCODE_DPAD_LEFT",
    "DPAD_RIGHT": "KEYCODE_DPAD_RIGHT",
    "DPAD_CENTER": "KEYCODE_DPAD_CENTER",
    "BACK": "KEYCODE_BACK",
    "HOME": "KEYCODE_HOME",
    "ENTER": "KEYCODE_ENTER",
    "PLAY_PAUSE": "KEYCODE_MEDIA_PLAY_PAUSE",
}


def configured() -> bool:
    return bool(config.ANDROID_TV_HOST)


def _signer():
    """Génère la paire de clés RSA au premier lancement, la réutilise
    ensuite — évite de redemander l'autorisation à l'écran à chaque
    redémarrage du brain (voir docstring du module)."""
    from adb_shell.auth.keygen import keygen
    from adb_shell.auth.sign_pythonrsa import PythonRSASigner

    key_path = str(config.ANDROID_TV_ADB_KEY_PATH)
    if not config.ANDROID_TV_ADB_KEY_PATH.exists():
        config.ensure_dirs()
        keygen(key_path)
    with open(key_path) as f:
        priv = f.read()
    with open(key_path + ".pub") as f:
        pub = f.read()
    return PythonRSASigner(pub, priv)


def _connect():
    """Connexion ADB TCP, mise en cache. Lève RuntimeError (jamais
    d'exception ADB brute) si l'appareil est injoignable ou refuse
    l'autorisation — message actionnable (vérifier IP / accepter la popup
    à l'écran) plutôt qu'une trace Python illisible pour Claude."""
    global _device
    from adb_shell.adb_device import AdbDeviceTcp
    from adb_shell.exceptions import DeviceAuthError

    with _lock:
        if _device is not None:
            try:
                # Sonde légère : une commande no-op confirme que la connexion
                # tenue en cache est toujours valide avant de la réutiliser.
                _device.shell("echo ok")
                return _device
            except Exception:
                _device = None

        device = AdbDeviceTcp(config.ANDROID_TV_HOST, config.ANDROID_TV_PORT, default_transport_timeout_s=9.0)
        try:
            device.connect(rsa_keys=[_signer()], auth_timeout_s=10.0)
        except DeviceAuthError as exc:
            raise RuntimeError(
                "Autorisation ADB refusée par le stick — accepte la popup "
                "« Autoriser le débogage USB ? » sur l'écran de la télé, "
                f"puis réessaie ({exc})."
            ) from exc
        except Exception as exc:
            raise RuntimeError(f"Stick TV injoignable à {config.ANDROID_TV_HOST}:{config.ANDROID_TV_PORT} ({exc}).") from exc
        _device = device
        return device


def _shell(cmd: str) -> str:
    device = _connect()
    try:
        return device.shell(cmd)
    except Exception as exc:
        # Une seule tentative de reconnexion — la connexion en cache a pu
        # expirer côté appareil (veille, redémarrage) sans que la sonde
        # _connect() l'ait détecté à temps.
        global _device
        _device = None
        device = _connect()
        try:
            return device.shell(cmd)
        except Exception as exc2:
            raise RuntimeError(f"Commande ADB refusée ({exc2}).") from exc2


def probe() -> None:
    """Sonde active (C7, voir brain/health.py) — un aller-retour minimal
    pour distinguer un stick injoignable/désautorisé d'un stick qui
    marche, avant que ça ne ressemble à un bug côté Console (T2). Lève
    RuntimeError (message actionnable, voir _connect()) sinon rien."""
    _shell("echo ok")


def volume(direction: str) -> dict:
    keys = {"up": "KEYCODE_VOLUME_UP", "down": "KEYCODE_VOLUME_DOWN", "mute": "KEYCODE_VOLUME_MUTE"}
    key = keys.get(direction)
    if not key:
        return {"error": f"Direction de volume inconnue : {direction!r}, Monsieur."}
    try:
        _shell(f"input keyevent {key}")
    except RuntimeError as exc:
        return {"error": str(exc)}
    return {"ok": True, "direction": direction}


def send_key(command: str) -> dict:
    key = _KEYCODES.get(command.upper())
    if not key:
        return {"error": f"Touche inconnue : {command!r}, Monsieur — valeurs possibles : {', '.join(_KEYCODES)}."}
    try:
        _shell(f"input keyevent {key}")
    except RuntimeError as exc:
        return {"error": str(exc)}
    return {"ok": True, "command": command}


def _resolve_app(target: str) -> str:
    """`target` en texte libre ("youtube", "disney+"…) → schéma de lien
    profond connu, ou tel quel si c'est déjà une URI (contient "://") ou un
    nom de package Android (contient un point, ex. "com.spotify.tv.android")."""
    t = target.strip().lower()
    if t in _APP_SCHEMES:
        return _APP_SCHEMES[t]
    return target.strip()


def launch_app(target: str) -> dict:
    """Lance une appli ou un contenu par lien profond — `target` : nom
    connu (voir _APP_SCHEMES), schéma d'URI complet ("vnd.youtube://ID"
    pour une vidéo précise), ou nom de package Android. Best effort : pas
    de garantie que l'appli respecte le lien profond (Disney+ notamment,
    voir conversation) — si Claude n'observe pas le changement attendu via
    un ui_dump ensuite, basculer sur la navigation manuelle (Couche 2/3)."""
    if not target or not target.strip():
        return {"error": "Nom d'application ou lien manquant, Monsieur."}
    resolved = _resolve_app(target)
    try:
        _shell(f'am start -a android.intent.action.VIEW -d "{resolved}"')
    except RuntimeError as exc:
        return {"error": str(exc)}
    return {"ok": True, "target": target, "resolved": resolved}


def list_apps() -> dict:
    """Liste les applis tierces installées (pas les composants système) —
    pour que Claude sache ce qui existe réellement sur ce stick avant de
    tenter un lancement, plutôt que de deviner un nom de package."""
    try:
        raw = _shell("pm list packages -3")
    except RuntimeError as exc:
        return {"error": str(exc)}
    packages = sorted(line.split(":", 1)[1].strip() for line in raw.splitlines() if line.startswith("package:"))
    return {"packages": packages}


_BOUNDS_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")


def _parse_ui_dump(xml_text: str) -> list[dict]:
    """Extrait les éléments utiles d'un dump uiautomator : texte visible OU
    description d'accessibilité, uniquement s'ils sont cliquables/focusables
    (le reste — conteneurs de mise en page — n'aide pas Claude à choisir où
    taper et gonflerait le texte pour rien)."""
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    elements = []
    for node in root.iter("node"):
        text = node.get("text", "").strip()
        desc = node.get("content-desc", "").strip()
        label = text or desc
        clickable = node.get("clickable") == "true"
        focusable = node.get("focusable") == "true"
        if not label or not (clickable or focusable):
            continue
        m = _BOUNDS_RE.match(node.get("bounds", ""))
        if not m:
            continue
        x1, y1, x2, y2 = map(int, m.groups())
        elements.append({
            "label": label,
            "x": (x1 + x2) // 2,
            "y": (y1 + y2) // 2,
            "resource_id": node.get("resource-id", ""),
        })
    return elements


def ui_dump() -> dict:
    """Couche 2 — capture l'arborescence de l'écran courant (texte +
    position exacte + cliquable) sans avoir besoin d'une image. Claude lit
    la liste, choisit l'élément pertinent (ex. l'icône "Recherche"), puis
    appelle tap() avec ses coordonnées x/y."""
    try:
        _shell("uiautomator dump /sdcard/jarvis_dump.xml")
        xml_text = _shell("cat /sdcard/jarvis_dump.xml")
    except RuntimeError as exc:
        return {"error": str(exc)}
    elements = _parse_ui_dump(xml_text)
    if not elements:
        return {
            "error": (
                "Aucun élément exploitable trouvé sur cet écran (interface non "
                "standard) — utilise tv_screenshot pour voir l'écran directement, Monsieur."
            )
        }
    lines = [f'- "{e["label"]}" à ({e["x"]},{e["y"]})' for e in elements]
    return {"text": "Éléments visibles à l'écran :\n" + "\n".join(lines)}


def tap(x: int, y: int) -> dict:
    try:
        _shell(f"input tap {int(x)} {int(y)}")
    except RuntimeError as exc:
        return {"error": str(exc)}
    return {"ok": True, "x": x, "y": y}


def type_text(text: str) -> dict:
    if not text:
        return {"error": "Texte manquant, Monsieur."}
    # `input text` d'Android casse sur les espaces bruts dans certaines
    # versions — %s est le remplacement standard, documenté depuis des
    # années dans l'écosystème ADB.
    escaped = text.replace(" ", "%s").replace('"', "")
    try:
        _shell(f'input text "{escaped}"')
    except RuntimeError as exc:
        return {"error": str(exc)}
    return {"ok": True, "text": text}


def screenshot() -> dict:
    """Couche 3, dernier recours — capture l'écran en image. Écrit sur la
    carte SD de l'appareil puis rapatrie le fichier (device.pull, transfert
    binaire propre) plutôt qu'une capture "shell" texte qui corromprait les
    octets PNG."""
    device = None
    try:
        device = _connect()
        device.shell("screencap -p /sdcard/jarvis_screen.png")
        import io
        buf = io.BytesIO()
        device.pull("/sdcard/jarvis_screen.png", buf)
        data = buf.getvalue()
    except Exception as exc:
        return {"error": f"Capture d'écran refusée ({exc})."}
    if not data:
        return {"error": "Capture d'écran vide, Monsieur."}
    return {
        "text": "Capture d'écran de la télé — repère l'élément voulu et appelle tv_tap avec ses coordonnées approximatives.",
        "image_b64": base64.b64encode(data).decode("ascii"),
        "media_type": "image/png",
    }

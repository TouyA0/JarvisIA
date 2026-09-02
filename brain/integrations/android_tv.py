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

Sécurité (T15) : ADB donne un accès quasi-shell complet à l'appareil —
`_connect_to()` refuse toute IP publique pour `ANDROID_TV_HOST`/l'hôte
redécouvert (voir `_is_lan_host()`), jamais de redirection de port. Et
`send_key()` exige une confirmation à l'écran (voir confirm.py) avant les
commandes qui coupent ce que quelqu'un est peut-être en train de regarder
(STOP — voir `_DISRUPTIVE_KEYS`) ; la navigation et les autres touches
média (pause, volume…) restent immédiates, elles se rattrapent d'un appui.
Première connexion : l'appareil affiche une popup "Autoriser le débogage
USB ?" à l'écran — à accepter une fois manuellement (télécommande), ensuite
la clé RSA générée ici (ANDROID_TV_ADB_KEY_PATH) est mémorisée par
l'appareil, plus rien à refaire.
"""
from __future__ import annotations

import base64
import ipaddress
import json
import re
import threading
import time

from brain import config
from brain.integrations import confirm

_lock = threading.Lock()
_device = None  # AdbDeviceTcp connecté, mis en cache — une seule connexion réutilisée.

# IP effectivement utilisée pour la dernière connexion réussie — peut
# diverger de config.ANDROID_TV_HOST (bail DHCP qui a bougé, voir
# _discover_host() / T13). Chargée paresseusement depuis le cache disque
# dans _connect() pour survivre à un redémarrage du brain.
_resolved_host: str | None = None

# mDNS/DNS-SD : la plupart des Android TV / Google TV annoncent le service
# ADB réseau ("Débogage réseau" dans Options développeur) sous l'un de ces
# deux noms selon le fabricant/la version — on essaie les deux, best effort,
# et on abandonne silencieusement si rien ne répond (réseau qui filtre le
# multicast, appareil qui n'annonce rien : l'IP fixe en .env reste la voie
# normale, ceci n'est qu'un filet de secours).
_MDNS_SERVICE_TYPES = ("_adb-tls-connect._tcp.local.", "_adb._tcp.local.")
_MDNS_DISCOVERY_TIMEOUT_S = 4.0

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

# Nom d'app → package Android, pour vérifier APRÈS coup que le lien profond a
# vraiment amené la bonne appli au premier plan (voir launch_app()). Un lien
# profond qui échoue ne lève aucune erreur ADB — `am start` répond toujours
# "started" même quand l'appli ignore le lien et reste sur son écran d'accueil
# (Disney+ notamment) ou que rien ne se passe : sans cette vérification,
# launch_app() ne peut pas distinguer un lancement réussi d'un échec silencieux,
# et rien n'imposait à Claude de basculer sur la recherche manuelle (Couche 2).
_APP_PACKAGES = {
    "youtube": "com.google.android.youtube.tv",
    "spotify": "com.spotify.tv.android",
    "netflix": "com.netflix.ninja",
    "disney+": "com.disney.disneyplus",
    "disney": "com.disney.disneyplus",
    "prime video": "com.amazon.amazonvideo.livingroom",
    "amazon prime": "com.amazon.amazonvideo.livingroom",
}

_LAUNCH_VERIFY_DELAY_SECONDS = 1.5  # laisse l'appli le temps de passer au premier plan avant de vérifier

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
    "NEXT": "KEYCODE_MEDIA_NEXT",
    "PREVIOUS": "KEYCODE_MEDIA_PREVIOUS",
    "FAST_FORWARD": "KEYCODE_MEDIA_FAST_FORWARD",
    "REWIND": "KEYCODE_MEDIA_REWIND",
    "STOP": "KEYCODE_MEDIA_STOP",
}


def configured() -> bool:
    return bool(config.ANDROID_TV_HOST)


def _load_cached_host() -> str | None:
    try:
        data = json.loads(config.ANDROID_TV_HOST_CACHE_FILE.read_text(encoding="utf-8"))
        host = data.get("host")
        return host or None
    except (FileNotFoundError, ValueError, OSError):
        return None


def _save_cached_host(host: str) -> None:
    try:
        config.ensure_dirs()
        config.ANDROID_TV_HOST_CACHE_FILE.write_text(json.dumps({"host": host}), encoding="utf-8")
    except OSError:
        pass  # best effort — une IP non persistée force juste une redécouverte au prochain redémarrage.


def _discover_host() -> str | None:
    """Sonde mDNS du réseau local (T13) : quand l'IP fixe en .env ne répond
    plus (bail DHCP qui a bougé), cherche un appareil qui annonce le service
    ADB réseau plutôt que de laisser Monsieur aller chercher la nouvelle IP
    à la main sur l'appareil. Un seul stick attendu sur le réseau — le
    premier répondant est pris tel quel, aucune tentative de désambiguïser
    entre plusieurs appareils Android."""
    try:
        from zeroconf import ServiceBrowser, Zeroconf
    except ImportError:
        return None

    found: list[str] = []

    class _Listener:
        def add_service(self, zc, service_type, name):
            info = zc.get_service_info(service_type, name, timeout=2000)
            if info and info.parsed_addresses():
                found.append(info.parsed_addresses()[0])

        def update_service(self, zc, service_type, name):
            pass

        def remove_service(self, zc, service_type, name):
            pass

    zc = Zeroconf()
    try:
        ServiceBrowser(zc, list(_MDNS_SERVICE_TYPES), _Listener())
        deadline = time.monotonic() + _MDNS_DISCOVERY_TIMEOUT_S
        while time.monotonic() < deadline and not found:
            time.sleep(0.1)
    except Exception:
        return None
    finally:
        zc.close()
    return found[0] if found else None


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


class _PublicHostRefused(RuntimeError):
    """Distingue le refus délibéré d'une IP publique (config à corriger,
    voir _is_lan_host()) d'une simple panne réseau — _connect() ne doit pas
    l'avaler dans le message générique "injoignable" ni tenter mDNS/repli,
    sans quoi Monsieur ne comprendrait jamais pourquoi ça ne marche pas."""


def _is_lan_host(host: str) -> bool:
    """False seulement si `host` est reconnaissable comme une IP publique —
    voir docstring du module : ADB donne un accès quasi-shell complet à
    l'appareil, `ANDROID_TV_HOST` ne doit jamais sortir du LAN (redirection
    de port, tunnel, DDNS mal configuré…). Un nom d'hôte (pas une IP)
    passe tel quel : pas de résolution DNS ici, et ce n'est de toute façon
    pas le format attendu (IP fixe en .env, voir config.py)."""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not ip.is_global


def _connect_to(host: str):
    """Une tentative de connexion ADB à `host`, sans repli. Laisse remonter
    les exceptions brutes (ConnectionRefusedError, TimeoutError,
    DeviceAuthError…) — c'est `_connect()` qui les interprète pour choisir
    entre repli mDNS et message d'erreur (T13)."""
    from adb_shell.adb_device import AdbDeviceTcp

    if not _is_lan_host(host):
        raise _PublicHostRefused(
            f"{host} est une adresse IP publique — ANDROID_TV_HOST ne doit jamais "
            "sortir du réseau local (ADB donne un accès quasi-shell complet à "
            "l'appareil), connexion refusée, Monsieur."
        )

    device = AdbDeviceTcp(host, config.ANDROID_TV_PORT, default_transport_timeout_s=9.0)
    device.connect(rsa_keys=[_signer()], auth_timeout_s=10.0)
    return device


def _connect():
    """Connexion ADB TCP, mise en cache. Lève RuntimeError (jamais
    d'exception ADB brute) si l'appareil est injoignable ou refuse
    l'autorisation — message actionnable plutôt qu'une trace Python
    illisible pour Claude.

    T13 — deux pannes fréquentes sur ce genre de stick, distinguées ici pour
    ne pas les confondre dans un message générique "injoignable" :
      - port 5555 fermé (ConnectionRefusedError, hôte joignable mais rien
        n'écoute) : le débogage ADB réseau se désactive au redémarrage du
        stick sur beaucoup d'appareils — message qui dit explicitement de
        le réactiver, plutôt que de laisser croire à un problème réseau.
      - hôte injoignable (timeout) : l'IP a pu changer (bail DHCP) — avant
        d'abandonner, on tente une découverte mDNS sur le réseau local, et
        si elle trouve l'appareil on met à jour l'IP utilisée (mémoire +
        cache disque) pour que les appels suivants n'aient plus à la
        redécouvrir.
    """
    global _device, _resolved_host
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

        if _resolved_host is None:
            _resolved_host = _load_cached_host()

        # Hôte fixe en .env d'abord (voie normale) ; si un autre hôte a
        # fonctionné précédemment (IP redécouverte), on le tente ensuite
        # sans repasser par une sonde mDNS à chaque appel.
        candidates = [config.ANDROID_TV_HOST]
        if _resolved_host and _resolved_host != config.ANDROID_TV_HOST:
            candidates.append(_resolved_host)

        last_exc: Exception | None = None
        auth_failed = False
        for host in candidates:
            try:
                device = _connect_to(host)
            except _PublicHostRefused:
                raise
            except DeviceAuthError as exc:
                auth_failed = True
                last_exc = exc
                continue
            except Exception as exc:
                last_exc = exc
                continue
            _device = device
            _resolved_host = host
            _save_cached_host(host)
            return device

        if auth_failed:
            raise RuntimeError(
                "Autorisation ADB refusée par le stick — accepte la popup "
                "« Autoriser le débogage USB ? » sur l'écran de la télé, "
                f"puis réessaie ({last_exc})."
            ) from last_exc

        if isinstance(last_exc, ConnectionRefusedError):
            raise RuntimeError(
                f"Le stick TV refuse la connexion sur le port {config.ANDROID_TV_PORT} à "
                f"{candidates[-1]} — le débogage ADB réseau s'est probablement désactivé "
                "au redémarrage du stick (fréquent sur ce genre d'appareil) : réactive "
                "« Débogage réseau » dans Options développeur puis réessaie."
            ) from last_exc

        # Timeout/hôte injoignable : l'IP a peut-être changé (DHCP) — tente
        # une découverte mDNS avant d'abandonner complètement.
        discovered = _discover_host()
        if discovered and discovered not in candidates:
            try:
                device = _connect_to(discovered)
            except Exception as exc:
                last_exc = exc
            else:
                _device = device
                _resolved_host = discovered
                _save_cached_host(discovered)
                return device

        raise RuntimeError(
            f"Stick TV injoignable à {config.ANDROID_TV_HOST}:{config.ANDROID_TV_PORT} "
            f"({last_exc}) — l'IP a peut-être changé (DHCP) et aucun appareil n'a répondu "
            "à la découverte réseau (mDNS) ; vérifie l'IP actuelle du stick et mets à "
            "jour ANDROID_TV_HOST si besoin."
        ) from last_exc


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


_RECONNECT_INTERVAL_S = 120  # T13 — reconnexion planifiée, pas seulement "à la volée"
# au prochain outil tv_* : détecte/répare une IP qui a bougé (DHCP) ou un port 5555
# qui s'est refermé (redémarrage du stick) en tâche de fond, pour que la première
# commande de Monsieur après un tel incident ne paie pas le coût de la découverte.


def _reconnect_loop() -> None:
    while True:
        time.sleep(_RECONNECT_INTERVAL_S)
        if not configured():
            continue
        try:
            probe()
        except RuntimeError as exc:
            print(f"[brain][android_tv] reconnexion planifiée en échec : {exc}")


_reconnect_started = False


def start_reconnect_loop() -> None:
    """Démarre le thread de reconnexion planifiée (T13, voir
    _reconnect_loop()) — tourne même si l'intégration n'est pas configurée
    au démarrage : `configured()` est relu à chaque tour, pour qu'un
    ANDROID_TV_HOST ajouté après coup soit pris en compte sans redémarrer
    le brain."""
    global _reconnect_started
    if _reconnect_started:
        return
    _reconnect_started = True
    threading.Thread(target=_reconnect_loop, daemon=True).start()


_STREAM_MUSIC = 3  # AudioManager.STREAM_MUSIC — flux utilisé par la quasi-totalité des apps média sur Android TV.
_VOLUME_GET_RE = re.compile(r"volume is (\d+) in range \[(-?\d+)\.\.(\d+)\]")


def _read_volume() -> dict:
    """`media volume --stream 3 --get` (VolumeShellCommand AOSP) → index
    courant + index max réel de l'appareil (varie selon le fabricant, pas
    de valeur en dur possible) — sert à la fois à *lire* le niveau (T6) et
    à convertir un pourcentage absolu en index avant `--set`."""
    raw = _shell(f"media volume --stream {_STREAM_MUSIC} --get")
    m = _VOLUME_GET_RE.search(raw)
    if not m:
        raise RuntimeError(f"Format de sortie de volume inattendu, Monsieur ({raw.strip()!r}).")
    current, _min, maximum = (int(g) for g in m.groups())
    percent = round(current * 100 / maximum) if maximum else 0
    return {"index": current, "max_index": maximum, "percent": percent}


def volume(direction: str | None = None, level: int | None = None) -> dict:
    """Réglage relatif (`direction` : up/down/mute, touches matérielles,
    comportement historique) OU absolu (`level` 0-100, "le son à 30 %") via
    `media volume --stream 3 --set` — seule commande qui connaisse l'index
    maximum réel de l'appareil. Sans argument : lit le niveau actuel."""
    if level is not None:
        if not isinstance(level, (int, float)) or not 0 <= level <= 100:
            return {"error": "Le niveau doit être un pourcentage entre 0 et 100, Monsieur."}
        try:
            current = _read_volume()
            index = round(level * current["max_index"] / 100)
            _shell(f"media volume --stream {_STREAM_MUSIC} --set {index}")
        except RuntimeError as exc:
            return {"error": str(exc)}
        return {"ok": True, "level_percent": int(level)}

    if direction is None:
        try:
            current = _read_volume()
        except RuntimeError as exc:
            return {"error": str(exc)}
        return {"ok": True, "level_percent": current["percent"]}

    keys = {"up": "KEYCODE_VOLUME_UP", "down": "KEYCODE_VOLUME_DOWN", "mute": "KEYCODE_VOLUME_MUTE"}
    key = keys.get(direction)
    if not key:
        return {"error": f"Direction de volume inconnue : {direction!r}, Monsieur."}
    try:
        _shell(f"input keyevent {key}")
    except RuntimeError as exc:
        return {"error": str(exc)}
    return {"ok": True, "direction": direction}


_DISRUPTIVE_KEYS = {"STOP"}  # coupe la lecture en cours — quelqu'un peut être en train de
# regarder (voir docstring du module, T15) : confirmation obligatoire, contrairement à la
# navigation/aux touches média non destructives (pause/volume se rattrapent d'un appui).


def send_key(command: str) -> dict:
    key = _KEYCODES.get(command.upper())
    if not key:
        return {"error": f"Touche inconnue : {command!r}, Monsieur — valeurs possibles : {', '.join(_KEYCODES)}."}
    if command.upper() in _DISRUPTIVE_KEYS:
        summary = "Arrêter la lecture en cours sur la télé du salon, Monsieur — quelqu'un est peut-être en train de regarder."
        if not confirm.request(summary):
            return {"error": "Action refusée par Monsieur ou confirmation expirée, Monsieur."}
    try:
        _shell(f"input keyevent {key}")
    except RuntimeError as exc:
        return {"error": str(exc)}
    return {"ok": True, "command": command}


_SEEK_STEP_SECONDS = 10  # pas de KEYCODE_MEDIA_SKIP_FORWARD/BACKWARD (AOSP) — la
# plupart des apps média Android (YouTube, Netflix…) l'implémentent ainsi ; aucun
# moyen générique via ADB de sauter à une durée arbitraire exacte.
_SEEK_MAX_PRESSES = 12  # borne à 2 min pour éviter une rafale de commandes sur une durée mal comprise.
_SEEK_KEYS = {"forward": "KEYCODE_MEDIA_SKIP_FORWARD", "backward": "KEYCODE_MEDIA_SKIP_BACKWARD"}


def seek(direction: str, seconds: int | float = _SEEK_STEP_SECONDS) -> dict:
    """Avance/recule dans la lecture en cours (« recule de 30 secondes ») par
    appuis répétés de KEYCODE_MEDIA_SKIP_FORWARD/BACKWARD, chacun valant
    ~10 s dans la plupart des apps média. Best effort comme launch_app() :
    certaines apps ignorent ces touches ou utilisent un pas différent — pour
    un bouton précis dans l'appli (« saute le générique »), passer par
    ui_dump()+tap() plutôt que par ici."""
    key = _SEEK_KEYS.get(direction)
    if not key:
        return {"error": f"Direction de seek inconnue : {direction!r}, Monsieur — 'forward' ou 'backward'."}
    if not isinstance(seconds, (int, float)) or seconds <= 0:
        return {"error": "La durée doit être un nombre de secondes positif, Monsieur."}
    presses = min(max(round(seconds / _SEEK_STEP_SECONDS), 1), _SEEK_MAX_PRESSES)
    try:
        for i in range(presses):
            _shell(f"input keyevent {key}")
            if i + 1 < presses:
                time.sleep(0.15)  # laisse l'appli enregistrer chaque appui séparément
    except RuntimeError as exc:
        return {"error": str(exc)}
    return {"ok": True, "direction": direction, "seconds": presses * _SEEK_STEP_SECONDS}


def _resolve_app(target: str) -> str:
    """`target` en texte libre ("youtube", "disney+"…) → schéma de lien
    profond connu, ou tel quel si c'est déjà une URI (contient "://") ou un
    nom de package Android (contient un point, ex. "com.spotify.tv.android")."""
    t = target.strip().lower()
    if t in _APP_SCHEMES:
        return _APP_SCHEMES[t]
    return target.strip()


_PACKAGE_NAME_RE = re.compile(r"^[a-zA-Z]\w*(\.[a-zA-Z]\w*)+$")


def _looks_like_package(s: str) -> bool:
    """Distingue un nom de package Android ("com.spotify.tv.android", ce
    que renvoie list_apps()) d'une URI de lien profond ("vnd.youtube://",
    "nflx://…") — les deux peuvent contenir un point, seule l'absence de
    "://" et la forme package.name.style permettent de trancher (T12)."""
    return "://" not in s and bool(_PACKAGE_NAME_RE.match(s))


def launch_app(target: str) -> dict:
    """Lance une appli ou un contenu par lien profond — `target` : nom
    connu (voir _APP_SCHEMES), schéma d'URI complet ("vnd.youtube://ID"
    pour une vidéo précise), ou nom de package Android. Best effort : pas
    de garantie que l'appli respecte le lien profond (Disney+ notamment,
    voir conversation).

    `am start -a VIEW -d "<uri>"` ne fonctionne que pour un vrai lien
    profond (schéma "scheme://…") ; pour un nom de package brut (ex.
    "com.spotify.tv.android", ce que renvoie list_apps()), `-d` attend une
    donnée/URI et non un package — la commande "réussit" côté ADB sans rien
    lancer. Dans ce cas on utilise `monkey -p <pkg> -c
    android.intent.category.LAUNCHER 1`, qui résout et lance l'activité
    principale du package (T12).

    `am start`/`monkey` répondent toujours "started"/"injected" même quand
    l'appli ignore le lien et reste sur son écran d'accueil, donc l'échec
    est silencieux côté ADB — pour les apps connues (voir _APP_PACKAGES) ou
    quand `target` est déjà un nom de package, on vérifie donc après coup
    via `dumpsys activity activities` que l'appli attendue est bien passée
    au premier plan. Si ce n'est pas le cas, le dict renvoyé porte lui-même
    l'instruction de repli générique (recherche + tv_tap + tv_type_text)
    dans "text", pour que Claude bascule sur la Couche 2 au lieu de
    répéter le même lancement ou de considérer la tâche terminée."""
    if not target or not target.strip():
        return {"error": "Nom d'application ou lien manquant, Monsieur."}
    t = target.strip().lower()
    resolved = _resolve_app(target)
    expected_package = _APP_PACKAGES.get(t) or (resolved if _looks_like_package(resolved) else None)
    try:
        if _looks_like_package(resolved):
            _shell(f"monkey -p {resolved} -c android.intent.category.LAUNCHER 1")
        else:
            _shell(f'am start -a android.intent.action.VIEW -d "{resolved}"')
    except RuntimeError as exc:
        return {"error": str(exc)}

    if not expected_package:
        # Pas de package connu pour vérifier (URI de contenu précis, ou app
        # inconnue de _APP_PACKAGES) : impossible de confirmer le succès
        # automatiquement — même consigne de repli que l'échec vérifié, mais
        # formulée comme "à vérifier toi-même" plutôt qu'affirmée.
        return {
            "ok": True,
            "target": target,
            "resolved": resolved,
            "verified": None,
            "text": (
                f"Lien profond envoyé pour {target!r}, mais aucune vérification "
                "automatique possible pour cette appli. Confirme via tv_screen_dump "
                "que ça a bien mené au bon endroit ; si ce n'est pas le cas, bascule "
                "sur la recherche manuelle : tv_screen_dump pour repérer l'icône ou "
                "le champ de recherche, tv_tap dessus, puis tv_type_text avec le "
                "titre recherché."
            ),
        }

    time.sleep(_LAUNCH_VERIFY_DELAY_SECONDS)
    try:
        activity_raw = _shell("dumpsys activity activities")
        foreground = _foreground_app(activity_raw)
    except RuntimeError:
        foreground = None

    if foreground == expected_package:
        return {"ok": True, "target": target, "resolved": resolved, "verified": True}

    return {
        "ok": True,
        "target": target,
        "resolved": resolved,
        "verified": False,
        "foreground_app": foreground,
        "text": (
            f"Le lien profond n'a pas amené {target} au premier plan (appli "
            f"actuellement affichée : {foreground or 'inconnue'}) — ne réessaie pas "
            "ce même lancement. Bascule immédiatement sur la recherche manuelle : "
            "tv_screen_dump pour repérer l'icône ou le champ de recherche de "
            f"l'appli, tv_tap dessus, puis tv_type_text avec le titre recherché."
        ),
    }


_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "music.youtube.com"}
_YOUTUBE_ID_RE = re.compile(r"^[\w-]{11}$")
_YOUTUBE_TIMESTAMP_RE = re.compile(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$")


def _parse_youtube_timestamp(raw: str) -> int | None:
    """Le paramètre `t=`/`start=` d'une URL YouTube prend deux formes selon
    comment le lien a été copié : un entier brut de secondes ("90") ou un
    format "1h2m3s" (parties optionnelles) — les deux vus en usage réel."""
    raw = raw.strip()
    if raw.isdigit():
        return int(raw)
    m = _YOUTUBE_TIMESTAMP_RE.match(raw)
    if not m or not any(m.groups()):
        return None
    h, mnt, s = (int(g) if g else 0 for g in m.groups())
    return h * 3600 + mnt * 60 + s


def _extract_youtube(url: str) -> tuple[str, int | None] | None:
    """URL de page YouTube (youtube.com/watch?v=ID, youtu.be/ID, /shorts/ID,
    /live/ID, /embed/ID) → (id_vidéo, horodatage en secondes ou None). None
    si `url` n'est pas reconnaissable comme une page YouTube — send_to_tv()
    passe alors l'URL telle quelle en lien profond générique (C1)."""
    from urllib.parse import urlparse, parse_qs

    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if parsed.hostname not in _YOUTUBE_HOSTS:
        return None

    qs = parse_qs(parsed.query)
    video_id = None
    if parsed.hostname == "youtu.be":
        video_id = parsed.path.strip("/").split("/")[0] or None
    elif "v" in qs:
        video_id = qs["v"][0]
    else:
        for prefix in ("/shorts/", "/live/", "/embed/"):
            if parsed.path.startswith(prefix):
                video_id = parsed.path[len(prefix):].split("/")[0]
                break

    if not video_id or not _YOUTUBE_ID_RE.match(video_id):
        return None

    t_raw = (qs.get("t") or qs.get("start") or [None])[0]
    seconds = _parse_youtube_timestamp(t_raw) if t_raw else None
    return video_id, seconds


def send_to_tv(url: str) -> dict:
    """C1 — transfère l'URL de l'onglet actif du PC (voir outil PC
    get_browser_url) vers la télé du salon. YouTube : extrait l'ID de la
    vidéo et l'horodatage éventuel (&t=) pour lancer directement le lien
    profond natif 'vnd.youtube://ID?t=SECONDS' — reprend exactement où
    Monsieur en était, sans passer par un navigateur (qui n'existe pas sur
    ce stick). Tout le reste (Netflix, Prime Video, une page quelconque) :
    transmet l'URL telle quelle à launch_app(), qui l'envoie en intent VIEW
    — Android résout lui-même vers l'appli installée compatible (App Links),
    même mécanique que pour un lien profond ou un nom de package inconnu."""
    if not url or not url.strip():
        return {"error": "Aucune URL à envoyer sur la télé, Monsieur."}
    url = url.strip()

    youtube = _extract_youtube(url)
    if youtube:
        video_id, seconds = youtube
        target = f"vnd.youtube://{video_id}"
        if seconds:
            target += f"?t={seconds}"
        return launch_app(target)

    return launch_app(url)


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


_PLAYBACK_STATES = {
    # Codes PlaybackStateCompat (AOSP) — https://developer.android.com/reference/androidx/media3/session/PlaybackStateCompat
    "1": "arrêtée",
    "2": "en pause",
    "3": "en lecture",
    "4": "avance rapide",
    "5": "retour rapide",
    "6": "en chargement",
    "7": "en erreur",
    "8": "en connexion",
    "9": "en lecture",
    "10": "en lecture",
    "11": "en lecture",
}


def _screen_on(raw: str) -> bool | None:
    """`dumpsys power` → écran allumé/éteint. Deux formats vus selon la
    version d'Android : `mWakefulness=Awake|Asleep|Dozing` (le plus fiable,
    reflète l'état réel du CPU/écran) ou `Display Power: state=ON|OFF` en
    repli. None si aucun des deux ne matche (format inattendu)."""
    m = re.search(r"mWakefulness=(\w+)", raw)
    if m:
        return m.group(1) == "Awake"
    m = re.search(r"Display Power:\s*state=(\w+)", raw)
    if m:
        return m.group(1) == "ON"
    return None


def _foreground_app(raw: str) -> str | None:
    """`dumpsys activity activities` → nom de package au premier plan.
    `mResumedActivity` est le champ présent sur toutes les versions
    Android testées ; `mFocusedApp` en repli (certaines versions TV)."""
    m = re.search(r"mResumedActivity.*?\s([\w.]+)/[\w.$]+[\s}]", raw)
    if m:
        return m.group(1)
    m = re.search(r"mFocusedApp=.*?\s([\w.]+)/[\w.$]+[\s}]", raw)
    if m:
        return m.group(1)
    return None


def _parse_media_session(raw: str) -> dict | None:
    """`dumpsys media_session` → titre/artiste/état/position de la session
    la plus prioritaire (la première listée). Best effort : le format
    exact de la ligne `description=` varie selon la version d'Android et
    l'appli (objet `MediaDescription{mTitle=..., mSubtitle=...}` sur les
    versions récentes, triplet `Titre, null, Artiste` séparé par virgules
    sur les plus anciennes) — on tente les deux, None si rien n'est
    exploitable plutôt qu'un titre inventé."""
    if not raw.strip() or "no sessions" in raw.lower():
        return None

    package_m = re.search(r"package=(\S+)", raw)
    state_m = re.search(r"state=PlaybackState\s*\{state=(\d+)[^,]*,\s*position=(-?\d+)", raw)

    title = artist = media_id = None
    desc_m = re.search(r"description=(.+)", raw)
    if desc_m:
        desc = desc_m.group(1).strip()
        obj_m = re.search(r"mTitle=([^,}]*),\s*mSubtitle=([^,}]*)", desc)
        if obj_m:
            title = obj_m.group(1).strip() or None
            artist = obj_m.group(2).strip() or None
        else:
            parts = [p.strip() for p in desc.split(",")]
            if parts and parts[0] and parts[0].lower() != "null":
                title = parts[0]
            if len(parts) > 2 and parts[2] and parts[2].lower() != "null":
                artist = parts[2]
        # mMediaId (C2) : sur ce stick, correspond à l'ID vidéo pour l'appli
        # YouTube TV — best effort, pas garanti pour les autres apps (voir
        # now_playing_url()). Absent de l'ancien format triplet ci-dessus,
        # uniquement dans l'objet MediaDescription{...}.
        id_m = re.search(r"mMediaId=([^,}]*)", desc)
        if id_m:
            candidate = id_m.group(1).strip()
            if candidate and candidate.lower() != "null":
                media_id = candidate

    if not package_m and not title:
        return None

    position = int(state_m.group(2)) if state_m and int(state_m.group(2)) >= 0 else None
    return {
        "package": package_m.group(1) if package_m else None,
        "title": title,
        "artist": artist,
        "state": _PLAYBACK_STATES.get(state_m.group(1)) if state_m else None,
        "position_ms": position,
        "media_id": media_id,
    }


def status() -> dict:
    """État réel de la télé (T3) : écran allumé/éteint, appli au premier
    plan, session multimédia active — sans ça Jarvis pilote la télé à
    l'aveugle et ne peut pas répondre à « qu'est-ce qui joue ? », « la
    télé est allumée ? » ou « on en est où dans l'épisode ? »."""
    try:
        power_raw = _shell("dumpsys power")
        activity_raw = _shell("dumpsys activity activities")
        media_raw = _shell("dumpsys media_session")
    except RuntimeError as exc:
        return {"error": str(exc)}
    return {
        "screen_on": _screen_on(power_raw),
        "foreground_app": _foreground_app(activity_raw),
        "media": _parse_media_session(media_raw),
    }


_YOUTUBE_PACKAGES = {"com.google.android.youtube.tv", "com.google.android.youtube"}


def now_playing_url() -> dict:
    """C2 — l'inverse de send_to_tv (C1) : reconstruit l'URL PC permettant
    de reprendre exactement ce qui joue sur la télé, à la bonne position, à
    partir de dumpsys media_session (T3, voir _parse_media_session).

    Best effort, comme launch_app()/send_to_tv() : ADB ne donne jamais
    directement une URL, seulement les métadonnées de la session média
    active. `mMediaId` correspond à l'ID vidéo pour l'appli YouTube TV
    (constaté sur ce stick) — quand il est présent et exploitable, l'URL est
    reconstruite exactement. Pour les autres apps (Netflix, Prime Video…),
    aucun ID exploitable n'est exposé par media_session : plutôt que
    d'inventer un lien, renvoie titre/artiste/position et laisse Claude
    chercher (web_search) avant d'appeler open_url — jamais de faux lien."""
    try:
        media_raw = _shell("dumpsys media_session")
    except RuntimeError as exc:
        return {"error": str(exc)}
    info = _parse_media_session(media_raw)
    if not info or not (info.get("title") or info.get("media_id")):
        return {"error": "Rien ne joue actuellement sur la télé, Monsieur."}

    seconds = (info["position_ms"] // 1000) if info.get("position_ms") is not None else None
    package = info.get("package") or ""
    media_id = info.get("media_id")

    if package in _YOUTUBE_PACKAGES and media_id and _YOUTUBE_ID_RE.match(media_id):
        url = f"https://www.youtube.com/watch?v={media_id}"
        if seconds:
            url += f"&t={seconds}s"
        return {"ok": True, "url": url, "title": info.get("title"), "position_seconds": seconds}

    return {
        "ok": True,
        "url": None,
        "title": info.get("title"),
        "artist": info.get("artist"),
        "package": package or None,
        "position_seconds": seconds,
        "text": (
            "Impossible de reconstruire un lien direct depuis la télé pour cette application "
            f"— titre détecté : {info.get('title') or 'inconnu'}"
            + (f", à {seconds}s" if seconds else "")
            + ". Cherche ce titre (web_search) pour retrouver l'URL exacte avant d'appeler open_url."
        ),
    }


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

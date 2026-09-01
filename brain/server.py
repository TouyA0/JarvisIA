"""Serveur central (brain) : FastAPI + WebSocket.

Deux canaux distincts :
  /ws/agent  — un agent (agents/desktop, plus tard agents/mobile) s'y
               connecte, s'enregistre, répond aux commandes.
  /ws/chat   — la Console web (Phase 2) y envoie du texte, reçoit la
               réponse en streaming phrase par phrase.

Depuis la Phase 10 : /ws/chat peut aussi déclencher du pilotage PC
(brain.core.agent.ask_with_tools, dispatché sur le réseau vers un
appareil) quand la question ressemble à une commande PC
(agents/desktop/brain/router.py::is_pc_command) — sinon conversation
pure comme avant (brain.core.chat.ask_stream, aucun tool-use).
"""
from __future__ import annotations

import asyncio
import threading
import time
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from agents.desktop.brain.router import is_pc_command
from agents.protocol.auth import generate_token
from agents.protocol.messages import (
    CommandResult,
    DeviceRegister,
    DeviceStatus,
    RegisterAck,
    parse_message,
)
from brain import activity, cards, config, device_store, diagnostics, pairing, routines, speech, weather
from brain import tools as brain_tools
from brain.core import agent as pc_agent
from brain.core import convlog
from brain.core import memory as core_memory
from brain.core import modes as core_modes
from brain.core import usage as core_usage
from brain.core.chat import ask_stream
from brain.devices import Device, registry
from brain.integrations import confirm as integrations_confirm
from brain.integrations import google_calendar, google_contacts, google_drive, google_gmail, google_oauth, settings as integrations_settings
from brain.integrations import home_assistant
from brain.integrations import jellyfin
from brain.integrations import spotify, spotify_oauth
from brain.integrations import store as integrations_store
from brain.integrations import tisseo
from brain.integrations import zoho_mail, zoho_oauth

# Un module par service Google, tous partagent la même mécanique OAuth
# (google_oauth.py) et le même callback — seul auth-url/callback ont besoin
# de savoir lequel appeler ; calendar_events/drive_search/gmail_search
# (brain/tools.py) importent directement le module qui les concerne.
_GOOGLE_SERVICES = {
    google_calendar.SERVICE_TYPE: google_calendar,
    google_drive.SERVICE_TYPE: google_drive,
    google_gmail.SERVICE_TYPE: google_gmail,
    google_contacts.SERVICE_TYPE: google_contacts,
}
# Même principe pour Zoho (aujourd'hui un seul service, zoho_mail — mais
# Zoho a d'autres API sur le même mécanisme OAuth si un jour utile).
_ZOHO_SERVICES = {
    zoho_mail.SERVICE_TYPE: zoho_mail,
}

config.ensure_dirs()

app = FastAPI(title="Jarvis Brain")

if not config.CONSOLE_PASSWORD:
    print("[brain] CONSOLE_PASSWORD non défini — API et Console accessibles sans "
          "authentification à quiconque atteint ce serveur (VPN/LAN compris). "
          "À définir dans .env avant toute exposition au-delà de 127.0.0.1.")


@app.middleware("http")
async def _require_console_auth(request: Request, call_next):
    """Rempart unique devant toute l'API : sans lui, quiconque atteint le
    brain sur le réseau (VPN, LAN) peut déjà tout faire — lire les
    appareils, dispatcher des commandes, déclencher des routines. Devient
    plus sensible depuis que le chat peut piloter le PC en langage libre,
    pas seulement via les boutons figés de Focus. /api/health reste ouvert
    (sondes de démarrage, aucune donnée sensible)."""
    path = request.url.path
    # Google/Zoho appellent ces routes directement (redirection navigateur
    # après consentement) : pas de moyen d'y joindre notre bearer token. Sûr
    # quand même — le `state` à usage unique émis par nous seuls fait office
    # de jeton anti-CSRF pour cet échange (google_oauth.py / zoho_oauth.py).
    if path in (
        "/api/integrations/google/callback",
        "/api/integrations/zoho/callback",
        "/api/integrations/spotify/callback",
    ):
        return await call_next(request)
    if config.CONSOLE_PASSWORD and path.startswith("/api/") and path != "/api/health":
        auth = request.headers.get("authorization", "")
        token = auth[7:] if auth.lower().startswith("bearer ") else ""
        if token != config.CONSOLE_PASSWORD:
            return JSONResponse({"detail": "authentification requise"}, status_code=401)
    return await call_next(request)


_SENTINEL = object()


async def _stream_sync_generator(gen_func: Callable[..., Any], *args, **kwargs):
    """Pont thread → asyncio : consomme un générateur synchrone (I/O bloquante,
    requests vers Ollama/Claude) sans geler la boucle d'événements FastAPI."""
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def worker() -> None:
        try:
            for item in gen_func(*args, **kwargs):
                loop.call_soon_threadsafe(queue.put_nowait, item)
        except Exception as exc:  # remonté au consommateur, jamais avalé en silence
            loop.call_soon_threadsafe(queue.put_nowait, exc)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _SENTINEL)

    threading.Thread(target=worker, daemon=True).start()
    while True:
        item = await queue.get()
        if item is _SENTINEL:
            return
        if isinstance(item, Exception):
            raise item
        yield item


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "devices": [d.device_id for d in registry.list()]}


@app.get("/api/devices")
async def list_devices() -> list[dict]:
    """Tous les appareils appairés (connus), en ligne ou pas — l'écran Centre
    d'appareils affiche aussi ceux actuellement hors ligne."""
    live = {d.device_id: d for d in registry.list()}
    result = []
    for known in device_store.list_known():
        device_id = known["device_id"]
        live_dev = live.get(device_id)
        result.append({
            "device_id": device_id,
            "name": known["name"],
            "device_type": known["device_type"],
            "paired_at": known["paired_at"],
            "capabilities": live_dev.capabilities if live_dev else [],
            "status": live_dev.status if live_dev else "offline",
        })
    return result


@app.get("/api/devices/{device_id}")
async def get_device(device_id: str) -> dict:
    live_dev = registry.get(device_id)
    known = next((d for d in device_store.list_known() if d["device_id"] == device_id), None)
    if not known:
        raise HTTPException(404, f"appareil {device_id!r} inconnu")
    return {
        "device_id": device_id,
        "name": known["name"],
        "device_type": known["device_type"],
        "paired_at": known["paired_at"],
        "capabilities": live_dev.capabilities if live_dev else [],
        "status": live_dev.status if live_dev else "offline",
    }


@app.post("/api/pairing/code")
async def create_pairing_code() -> dict:
    """Génère un code d'appairage à usage unique (5 min) — affiché côté
    Centre d'appareils, à saisir sur le nouvel agent."""
    return {"code": pairing.create_code()}


@app.delete("/api/devices/{device_id}")
async def forget_device(device_id: str) -> dict:
    """Révoque un appareil appairé — il devra être ré-appairé pour revenir."""
    live_dev = registry.get(device_id)
    if live_dev:
        await live_dev.websocket.close()
        registry.unregister(device_id)
    if not device_store.forget(device_id):
        raise HTTPException(404, f"appareil {device_id!r} inconnu")
    return {"ok": True}


@app.post("/api/devices/{device_id}/dispatch")
async def dispatch_command(device_id: str, body: dict) -> dict:
    """Envoie une commande à un agent connecté et attend son résultat.

    Utilisé pour l'instant pour valider la Phase 3 en conditions réelles ;
    deviendra le point d'entrée du bouton « exécuter » côté Focus appareil
    (Phase 4).
    """
    tool = body.get("tool")
    if not tool:
        raise HTTPException(400, "tool manquant")
    try:
        result = await registry.dispatch(device_id, tool, body.get("args", {}))
    except KeyError:
        raise HTTPException(404, f"appareil {device_id!r} non connecté")
    except asyncio.TimeoutError:
        activity.record(device_id, tool, ok=False, error="timeout")
        raise HTTPException(504, "l'appareil n'a pas répondu à temps")
    activity.record(device_id, tool, ok=result.ok, error=result.error)
    return result.model_dump()


@app.get("/api/devices/{device_id}/activity")
async def device_activity(device_id: str) -> list[dict]:
    return activity.for_device(device_id)


@app.post("/api/devices/{device_id}/stream/frame")
async def stream_frame(device_id: str) -> dict:
    """Une image du partage d'écran live (voir Focus.jsx) — appelé en
    boucle par la Console pendant que la fenêtre est ouverte (§4 V1 de
    docs/ROADMAP_DISPLAY_INTEGRATIONS.md). Volontairement séparé de
    /dispatch : pas de passage par activity.record (des dizaines d'images
    par minute pollueraient le journal d'activité pour rien) et un tool
    dédié plus léger côté agent (capture_frame, pas take_screenshot —
    voir agents/desktop/tools/screen.py)."""
    try:
        result = await registry.dispatch(device_id, "capture_frame", {}, timeout=5.0)
    except KeyError:
        raise HTTPException(404, f"appareil {device_id!r} non connecté")
    except asyncio.TimeoutError:
        raise HTTPException(504, "l'appareil n'a pas répondu à temps")
    if not result.ok:
        raise HTTPException(502, result.error or "capture refusée")
    return result.result or {}


@app.get("/api/routines")
async def list_routines() -> list[dict]:
    return routines.list_routines()


@app.post("/api/routines")
async def create_routine(body: dict) -> dict:
    name = (body.get("name") or "").strip()
    steps = body.get("steps") or []
    if not name:
        raise HTTPException(400, "nom manquant")
    if not steps:
        raise HTTPException(400, "au moins une étape requise")
    return routines.create(name, steps)


@app.delete("/api/routines/{routine_id}")
async def delete_routine(routine_id: str) -> dict:
    if not routines.delete(routine_id):
        raise HTTPException(404, f"routine {routine_id!r} inconnue")
    return {"ok": True}


@app.post("/api/routines/{routine_id}/run")
async def run_routine(routine_id: str) -> dict:
    if not routines.exists(routine_id):
        raise HTTPException(404, f"routine {routine_id!r} inconnue")
    asyncio.create_task(routines.run(routine_id))
    return {"ok": True}


@app.get("/api/routines/{routine_id}/status")
async def routine_status(routine_id: str) -> dict:
    return routines.status(routine_id) or {"status": "idle"}


@app.get("/api/integrations")
async def list_integrations() -> list[dict]:
    """Tous les comptes tiers connectés (jamais les jetons), tous types
    confondus (google_calendar, google_drive…)."""
    return integrations_store.list_public()


@app.get("/api/integrations/google/settings")
async def google_settings() -> dict:
    """Configuré ou non, et d'où vient le réglage (Console ou .env) — jamais
    le client secret lui-même, voir integrations_settings.google_status."""
    return integrations_settings.google_status()


@app.post("/api/integrations/google/settings")
async def set_google_settings(body: dict) -> dict:
    """Enregistre le Client ID / Client Secret Google saisis dans la
    Console — évite d'avoir à éditer .env à la main (voir README.md pour
    comment les obtenir, cette étape-là reste dans Google Cloud Console,
    aucune API tierce ne permet de la sauter)."""
    client_id = (body.get("client_id") or "").strip()
    client_secret = (body.get("client_secret") or "").strip()
    if not client_id or not client_secret:
        raise HTTPException(400, "client_id et client_secret requis")
    integrations_settings.set_google_credentials(client_id, client_secret)
    return integrations_settings.google_status()


@app.delete("/api/integrations/google/settings")
async def clear_google_settings() -> dict:
    integrations_settings.clear_google_credentials()
    return integrations_settings.google_status()


@app.get("/api/integrations/google/auth-url")
async def google_auth_url(service: str = "google_calendar") -> dict:
    """URL de consentement Google à ouvrir dans un nouvel onglet — la
    Console (Integrations.jsx) fait juste `window.open(url)`. `service`
    identifie le module à utiliser (google_calendar, google_drive…) ; il est
    aussi encodé dans le `state` OAuth pour que le callback partagé (un seul
    redirect_uri possible côté Google) sache où router le code reçu."""
    module = _GOOGLE_SERVICES.get(service)
    if not module:
        raise HTTPException(400, f"service inconnu : {service!r}")
    if not google_oauth.configured():
        raise HTTPException(400, "Identifiants Google manquants — voir Paramètres Google dans la Console")
    return {"url": module.build_auth_url()}


@app.get("/api/integrations/google/callback")
async def google_callback(request: Request) -> Response:
    """Cible de la redirection Google après consentement — pas d'auth
    Console ici (voir middleware), et pas de JSON : cette route est ouverte
    par le navigateur, pas appelée en fetch. Répond avec une page qui se
    referme et prévient l'onglet Console d'où la connexion a été lancée.
    Le `state` (émis par google_oauth.build_auth_url) indique quel module
    appeler — seul lui sait quel scope/quelle API a été demandé."""
    code = request.query_params.get("code")
    state = request.query_params.get("state", "")
    error = request.query_params.get("error")

    def _page(ok: bool, message: str) -> Response:
        html = f"""<!doctype html><html><body style="background:#0a0e14;color:{'#5eead4' if ok else '#f87171'};
font-family:system-ui;display:grid;place-items:center;height:100vh;margin:0">
<div style="text-align:center">
<p>{message}</p>
<p style="opacity:.6;font-size:13px">Cet onglet peut être fermé.</p>
</div>
<script>
if (window.opener) {{ window.opener.postMessage({{ jarvisIntegration: {str(ok).lower()} }}, "*"); }}
setTimeout(() => window.close(), 1500);
</script>
</body></html>"""
        return Response(content=html, media_type="text/html")

    if error:
        return _page(False, f"Connexion refusée par Google ({error}).")
    if not code:
        return _page(False, "Réponse Google incomplète (code manquant).")

    service_type = google_oauth.consume_state(state)
    if not service_type:
        return _page(False, "État OAuth invalide ou expiré — relance la connexion depuis la Console.")
    module = _GOOGLE_SERVICES.get(service_type)
    if not module:
        return _page(False, f"Service inconnu : {service_type!r}")

    try:
        account = module.handle_callback(code)
    except Exception as exc:
        # RuntimeError attendu (Google refuse/jeton manquant) mais aussi
        # requests.HTTPError si l'appel d'identification du compte échoue
        # (_fetch_primary_email/_fetch_account_email) — dans tous les cas
        # mieux vaut un message clair côté Console qu'une 500 muette.
        return _page(False, str(exc))
    return _page(True, f"Compte {account['label']} connecté.")


@app.delete("/api/integrations/{account_id}")
async def remove_integration(account_id: str) -> dict:
    if not integrations_store.remove(account_id):
        raise HTTPException(404, f"compte {account_id!r} inconnu")
    return {"ok": True}


@app.get("/api/integrations/zoho/settings")
async def zoho_settings() -> dict:
    return integrations_settings.zoho_status()


@app.post("/api/integrations/zoho/settings")
async def set_zoho_settings(body: dict) -> dict:
    client_id = (body.get("client_id") or "").strip()
    client_secret = (body.get("client_secret") or "").strip()
    region = (body.get("region") or "").strip()
    if not client_id or not client_secret or not region:
        raise HTTPException(400, "client_id, client_secret et region requis")
    try:
        integrations_settings.set_zoho_credentials(client_id, client_secret, region)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return integrations_settings.zoho_status()


@app.delete("/api/integrations/zoho/settings")
async def clear_zoho_settings() -> dict:
    integrations_settings.clear_zoho_credentials()
    return integrations_settings.zoho_status()


@app.get("/api/integrations/zoho/auth-url")
async def zoho_auth_url(service: str = "zoho_mail") -> dict:
    module = _ZOHO_SERVICES.get(service)
    if not module:
        raise HTTPException(400, f"service inconnu : {service!r}")
    if not zoho_oauth.configured():
        raise HTTPException(400, "Identifiants Zoho manquants — voir Paramètres Zoho dans la Console")
    return {"url": module.build_auth_url()}


@app.get("/api/integrations/zoho/callback")
async def zoho_callback(request: Request) -> Response:
    """Cible de la redirection Zoho après consentement — même principe que
    google_callback ci-dessus (pas d'auth Console, page auto-fermante)."""
    code = request.query_params.get("code")
    state = request.query_params.get("state", "")
    error = request.query_params.get("error")

    def _page(ok: bool, message: str) -> Response:
        html = f"""<!doctype html><html><body style="background:#0a0e14;color:{'#5eead4' if ok else '#f87171'};
font-family:system-ui;display:grid;place-items:center;height:100vh;margin:0">
<div style="text-align:center">
<p>{message}</p>
<p style="opacity:.6;font-size:13px">Cet onglet peut être fermé.</p>
</div>
<script>
if (window.opener) {{ window.opener.postMessage({{ jarvisIntegration: {str(ok).lower()} }}, "*"); }}
setTimeout(() => window.close(), 1500);
</script>
</body></html>"""
        return Response(content=html, media_type="text/html")

    if error:
        return _page(False, f"Connexion refusée par Zoho ({error}).")
    if not code:
        return _page(False, "Réponse Zoho incomplète (code manquant).")

    service_type = zoho_oauth.consume_state(state)
    if not service_type:
        return _page(False, "État OAuth invalide ou expiré — relance la connexion depuis la Console.")
    module = _ZOHO_SERVICES.get(service_type)
    if not module:
        return _page(False, f"Service inconnu : {service_type!r}")

    try:
        account = module.handle_callback(code)
    except Exception as exc:
        return _page(False, str(exc))
    return _page(True, f"Compte {account['label']} connecté.")


@app.get("/api/integrations/spotify/settings")
async def spotify_settings() -> dict:
    return integrations_settings.spotify_status()


@app.post("/api/integrations/spotify/settings")
async def set_spotify_settings(body: dict) -> dict:
    client_id = (body.get("client_id") or "").strip()
    client_secret = (body.get("client_secret") or "").strip()
    if not client_id or not client_secret:
        raise HTTPException(400, "client_id et client_secret requis")
    integrations_settings.set_spotify_credentials(client_id, client_secret)
    return integrations_settings.spotify_status()


@app.delete("/api/integrations/spotify/settings")
async def clear_spotify_settings() -> dict:
    integrations_settings.clear_spotify_credentials()
    return integrations_settings.spotify_status()


@app.get("/api/integrations/spotify/auth-url")
async def spotify_auth_url() -> dict:
    if not spotify_oauth.configured():
        raise HTTPException(400, "Identifiants Spotify manquants — voir Paramètres Spotify dans la Console")
    return {"url": spotify.build_auth_url()}


@app.get("/api/integrations/spotify/callback")
async def spotify_callback(request: Request) -> Response:
    """Cible de la redirection Spotify après consentement — même principe
    que google_callback/zoho_callback ci-dessus."""
    code = request.query_params.get("code")
    state = request.query_params.get("state", "")
    error = request.query_params.get("error")

    def _page(ok: bool, message: str) -> Response:
        html = f"""<!doctype html><html><body style="background:#0a0e14;color:{'#5eead4' if ok else '#f87171'};
font-family:system-ui;display:grid;place-items:center;height:100vh;margin:0">
<div style="text-align:center">
<p>{message}</p>
<p style="opacity:.6;font-size:13px">Cet onglet peut être fermé.</p>
</div>
<script>
if (window.opener) {{ window.opener.postMessage({{ jarvisIntegration: {str(ok).lower()} }}, "*"); }}
setTimeout(() => window.close(), 1500);
</script>
</body></html>"""
        return Response(content=html, media_type="text/html")

    if error:
        return _page(False, f"Connexion refusée par Spotify ({error}).")
    if not code:
        return _page(False, "Réponse Spotify incomplète (code manquant).")
    if not spotify_oauth.consume_state(state):
        return _page(False, "État OAuth invalide ou expiré — relance la connexion depuis la Console.")

    try:
        account = spotify.handle_callback(code)
    except Exception as exc:
        return _page(False, str(exc))
    return _page(True, f"Compte {account['label']} connecté.")


@app.post("/api/integrations/jellyfin/connect")
async def connect_jellyfin(body: dict) -> dict:
    """Pas d'OAuth ici — serveur perso, clé API saisie directement (voir
    jellyfin.py::connect). Un seul aller-retour, pas de popup/callback."""
    base_url = (body.get("base_url") or "").strip()
    api_key = (body.get("api_key") or "").strip()
    username = (body.get("username") or "").strip() or None
    if not base_url or not api_key:
        raise HTTPException(400, "base_url et api_key requis")
    try:
        account = jellyfin.connect(base_url, api_key, username)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))
    return account


@app.post("/api/integrations/home_assistant/connect")
async def connect_home_assistant(body: dict) -> dict:
    """Pas d'OAuth — instance perso, token longue durée saisi directement
    (voir home_assistant.py::connect)."""
    base_url = (body.get("base_url") or "").strip()
    token = (body.get("token") or "").strip()
    if not base_url or not token:
        raise HTTPException(400, "base_url et token requis")
    try:
        account = home_assistant.connect(base_url, token)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))
    return account


@app.get("/api/integrations/tisseo/settings")
async def tisseo_settings() -> dict:
    return integrations_settings.tisseo_status()


@app.post("/api/integrations/tisseo/settings")
async def set_tisseo_settings(body: dict) -> dict:
    api_key = (body.get("api_key") or "").strip()
    if not api_key:
        raise HTTPException(400, "api_key requis")
    integrations_settings.set_tisseo_api_key(api_key)
    return integrations_settings.tisseo_status()


@app.delete("/api/integrations/tisseo/settings")
async def clear_tisseo_settings() -> dict:
    integrations_settings.clear_tisseo_api_key()
    return integrations_settings.tisseo_status()


@app.post("/api/integrations/tisseo/connect")
async def connect_tisseo(body: dict) -> dict:
    """Pas d'OAuth — enregistre un arrêt favori (résolu par nom via
    l'API Tisséo), voir tisseo.py::connect."""
    stop_query = (body.get("stop") or "").strip()
    if not stop_query:
        raise HTTPException(400, "stop requis")
    try:
        account = tisseo.connect(stop_query)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))
    return account


@app.get("/api/integrations/ors/settings")
async def ors_settings() -> dict:
    return integrations_settings.ors_status()


@app.post("/api/integrations/ors/settings")
async def set_ors_settings(body: dict) -> dict:
    api_key = (body.get("api_key") or "").strip()
    if not api_key:
        raise HTTPException(400, "api_key requis")
    integrations_settings.set_ors_api_key(api_key)
    return integrations_settings.ors_status()


@app.delete("/api/integrations/ors/settings")
async def clear_ors_settings() -> dict:
    integrations_settings.clear_ors_api_key()
    return integrations_settings.ors_status()


@app.post("/api/integrations/ors/home-address")
async def set_home_address(body: dict) -> dict:
    """Adresse par défaut pour directions() quand Monsieur ne donne que la
    destination — séparé de la clé API pour rester modifiable sans la
    ressaisir (voir settings.py::get_home_address)."""
    address = (body.get("address") or "").strip()
    if not address:
        raise HTTPException(400, "address requis")
    integrations_settings.set_home_address(address)
    return integrations_settings.ors_status()


@app.delete("/api/integrations/ors/home-address")
async def clear_home_address() -> dict:
    integrations_settings.clear_home_address()
    return integrations_settings.ors_status()


@app.get("/api/integrations/brave/settings")
async def brave_settings() -> dict:
    return integrations_settings.brave_status()


@app.post("/api/integrations/brave/settings")
async def set_brave_settings(body: dict) -> dict:
    api_key = (body.get("api_key") or "").strip()
    if not api_key:
        raise HTTPException(400, "api_key requis")
    integrations_settings.set_brave_api_key(api_key)
    return integrations_settings.brave_status()


@app.delete("/api/integrations/brave/settings")
async def clear_brave_settings() -> dict:
    integrations_settings.clear_brave_api_key()
    return integrations_settings.brave_status()


@app.get("/api/confirmations")
async def list_confirmations() -> list[dict]:
    """Actions d'écriture (Drive create/update/trash…) en attente d'un
    humain — la Console web poll ceci pour afficher sa bannière de
    confirmation (voir brain/integrations/confirm.py)."""
    return integrations_confirm.list_pending()


@app.post("/api/confirmations/{confirmation_id}/resolve")
async def resolve_confirmation(confirmation_id: str, body: dict) -> dict:
    approved = bool(body.get("approved"))
    if not integrations_confirm.resolve(confirmation_id, approved):
        raise HTTPException(404, "confirmation inconnue ou déjà expirée")
    return {"ok": True}


@app.post("/api/speech/transcribe")
async def transcribe_speech(file: UploadFile) -> dict:
    """Transcrit un segment audio envoyé par la Console web (Phase 9).

    Appel bloquant (I/O réseau vers Speaches) exécuté dans le threadpool
    de FastAPI par défaut pour les endpoints `def` synchrones — mais ici
    la fonction est `async`, donc on le fait explicitement pour ne pas
    geler la boucle d'événements pendant l'appel à Speaches.
    """
    audio_bytes = await file.read()
    text = await asyncio.to_thread(
        speech.transcribe, audio_bytes, file.filename or "audio.webm", file.content_type or "audio/webm",
    )
    return {"text": text}


@app.post("/api/speech/synthesize")
async def synthesize_speech(body: dict) -> Response:
    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text manquant")
    audio = await asyncio.to_thread(speech.synthesize, text)
    if audio is None:
        raise HTTPException(502, "synthèse vocale indisponible")
    return Response(content=audio, media_type="audio/mpeg")


# ── Système : mémoire, modes, consommation, journal ──────────────────────────
# Ces quatre choses existaient depuis longtemps côté brain (data/memory.json,
# data/modes.json, data/usage.json, data/logs/) mais n'étaient visibles que
# sur le HUD Qt du PC fixe. La Console web les expose maintenant aussi : sans
# ça, impossible de savoir depuis un téléphone ce que Jarvis retient de vous,
# dans quel mode il est, ni ce que l'API a coûté ce mois-ci.


@app.post("/api/tools/execute")
async def execute_tool(body: dict) -> dict:
    """Exécute un outil brain directement, sans passer par Claude — pour
    les boutons d'action posés sur une carte (pause/suivant sur la carte
    Spotify, etc., voir card.actions dans brain/cards.py). Réutilise
    brain_tools.execute() telle quelle : les mêmes garde-fous s'appliquent
    (confirmation humaine pour une action sensible), c'est le même code que
    la boucle d'agent appelle pour un tool_use de Claude, juste sans LLM au
    milieu — un bouton n'a pas besoin d'un aller-retour Claude pour dire
    "mets en pause"."""
    tool = body.get("tool", "")
    if tool not in brain_tools.NAMES:
        raise HTTPException(400, f"outil inconnu ou non actionnable depuis une carte : {tool!r}")
    result = await asyncio.to_thread(brain_tools.execute, tool, body.get("args") or {})
    return {"text": result if isinstance(result, str) else result.get("text", "")}


_AMBIENT_TTL_S = 180  # (J3) quelques minutes — voir Hud.jsx::Ambient
_ambient_cache: dict = {"at": 0.0, "data": None}


def _ambient_snapshot() -> dict:
    """Panorama silencieux du pupitre : météo, agenda du jour, santé
    système — chacun optionnel selon ce qui est configuré/joignable, pour
    qu'un compte Google absent ou l'API météo en panne n'empêche pas les
    deux autres de s'afficher."""
    out: dict = {}

    w = weather.get()
    if w and w["temp"] is not None:
        out["weather"] = {
            "temp": w["temp"], "description": weather.description(w["code"]),
            "wind": w["wind"], "city": config.WEATHER_CITY,
        }

    if google_calendar.configured() and integrations_store.list_public("google_calendar"):
        try:
            time_min, time_max = google_calendar.range_for("today")
            out["agenda"] = {"events": google_calendar.list_events(time_min, time_max), "range": "today"}
        except Exception as exc:
            print(f"[brain][ambient] agenda : {exc}")

    try:
        out["diagnostics"] = diagnostics.snapshot()
    except Exception as exc:
        print(f"[brain][ambient] diagnostics : {exc}")

    return out


@app.get("/api/ambient")
async def ambient() -> dict:
    """Ce que le pupitre affiche tant que personne n'a rien demandé (F29,
    voir Hud.jsx::Ambient) — volontairement à part de `cards.emit` : un
    rafraîchissement périodique de tous les pupitres ouverts ne doit ni
    diffuser sur /ws/cards (ça illuminerait les autres écrans pour rien),
    ni polluer le journal `cards-*.jsonl`. Cache en mémoire (quelques
    minutes) pour ne pas retaper Google Calendar/psutil à chaque appel."""
    now = time.time()
    cached = _ambient_cache["data"]
    if cached is not None and now - _ambient_cache["at"] < _AMBIENT_TTL_S:
        return cached
    data = await asyncio.to_thread(_ambient_snapshot)
    _ambient_cache.update(at=now, data=data)
    return data


@app.get("/api/cards")
async def list_cards(limit: int = 30) -> list[dict]:
    """Cartes récentes — ce que Jarvis a affiché dernièrement (agenda,
    mails, capture d'écran…). Sert à repeupler le pupitre après un
    rafraîchissement de page ; le flux temps réel passe par /ws/cards."""
    return cards.recent(max(1, min(limit, 30)))


@app.get("/api/cards/history")
async def cards_history(limit: int = 100) -> list[dict]:
    """Cartes passées, au-delà des 30 dernières gardées en mémoire —
    relit le journal disque (voir cards.py::history), survit à un
    redémarrage du brain. Les captures d'écran y perdent leur image
    (jamais écrite sur disque), le reste de la donnée est intact."""
    return cards.history(max(1, min(limit, 200)))


@app.delete("/api/cards")
async def clear_cards() -> dict:
    cards.clear()
    return {"ok": True}


@app.websocket("/ws/cards")
async def ws_cards(websocket: WebSocket) -> None:
    """Diffusion des cartes et des tours de conversation vers TOUTES les
    Consoles ouvertes, quelle que soit l'origine de la demande.

    Canal distinct de /ws/chat, volontairement : /ws/chat est un dialogue
    (une question, ses réponses, pour ce client-là), celui-ci est une
    diffusion. C'est ce qui permet de poser une question à voix haute au
    PC fixe et de voir l'écran d'à côté afficher la réponse."""
    await websocket.accept()
    if config.CONSOLE_PASSWORD and websocket.query_params.get("token") != config.CONSOLE_PASSWORD:
        await websocket.close(code=4401)
        return
    queue = cards.subscribe()
    # Ce canal est à sens unique : sans lecture en parallèle, une Console
    # fermée ne serait détectée qu'au prochain envoi — et resterait
    # abonnée d'ici là. Avec un onglet rouvert dix fois dans la journée,
    # les abonnés fantômes s'accumulent pour la durée de vie du process.
    closed = asyncio.create_task(websocket.receive_text())
    try:
        while True:
            nxt = asyncio.create_task(queue.get())
            done, _ = await asyncio.wait({nxt, closed}, return_when=asyncio.FIRST_COMPLETED)
            if closed in done:
                nxt.cancel()
                break
            await websocket.send_json(nxt.result())
    except WebSocketDisconnect:
        pass
    finally:
        closed.cancel()
        cards.unsubscribe(queue)


@app.get("/api/conversations")
async def list_conversations(limit: int = 40) -> list[dict]:
    """Derniers échanges journalisés — la Console s'en sert pour retrouver
    la conversation après un rafraîchissement de page (avant, tout
    disparaissait à chaque F5, seule la dernière réponse restait à
    l'écran)."""
    return convlog.recent(max(1, min(limit, 200)))


@app.get("/api/memory")
async def get_memory() -> dict:
    data = core_memory.load()
    return {"facts": data.get("facts", []), "last_updated": data.get("last_updated", "")}


@app.post("/api/memory")
async def add_memory_fact(body: dict) -> dict:
    """Ajout manuel d'un fait. Passe par le même `clean_fact` que la
    mémorisation vocale : un fait ajouté ici doit obéir aux mêmes règles
    (longueur, mots bannis) que ceux extraits automatiquement, sinon la
    Console devient une porte dérobée pour polluer le prompt système."""
    fact = core_memory.clean_fact((body.get("fact") or "").strip())
    if not fact:
        raise HTTPException(400, "fait vide, trop long (80 caractères max) ou non retenu")
    data = core_memory.load()
    if fact in data.get("facts", []):
        return {"ok": True, "fact": fact, "added": False}
    data.setdefault("facts", []).append(fact)
    data["last_updated"] = str(time.time())
    core_memory.save(data)
    return {"ok": True, "fact": fact, "added": True}


@app.put("/api/memory/{index}")
async def update_memory_fact(index: int, body: dict) -> dict:
    """Corriger un fait sans le perdre. Sans ça, rectifier une faute de
    frappe obligeait à supprimer puis retaper — et à retrouver la
    formulation exacte de mémoire."""
    fact = core_memory.clean_fact((body.get("fact") or "").strip())
    if not fact:
        raise HTTPException(400, "fait vide, trop long (80 caractères max) ou non retenu")
    data = core_memory.load()
    facts = data.get("facts", [])
    if index < 0 or index >= len(facts):
        raise HTTPException(404, "fait inconnu")
    facts[index] = fact
    data["last_updated"] = str(time.time())
    core_memory.save(data)
    return {"ok": True, "fact": fact}


@app.delete("/api/memory/{index}")
async def delete_memory_fact(index: int) -> dict:
    data = core_memory.load()
    facts = data.get("facts", [])
    if index < 0 or index >= len(facts):
        raise HTTPException(404, "fait inconnu")
    removed = facts.pop(index)
    data["last_updated"] = str(time.time())
    core_memory.save(data)
    return {"ok": True, "removed": removed}


@app.get("/api/modes")
async def list_modes() -> dict:
    """Modes contextuels + celui qui est actif. Le prompt système complet
    de chaque mode n'est pas renvoyé : c'est du texte long, sans intérêt
    pour l'affichage, et ça alourdirait un poll."""
    data = core_modes.load()
    return {
        "modes": [
            {
                "id": m["id"],
                "name": m.get("name", m["id"]),
                "description": m.get("description", ""),
                "response_style": m.get("response_style", ""),
                "notification_level": m.get("notification_level", ""),
                "focus_topics": m.get("focus_topics", []),
            }
            for m in data.get("modes", [])
        ],
        "current": core_modes.get_current(),
    }


@app.post("/api/modes/current")
async def set_current_mode(body: dict) -> dict:
    mode_id = (body.get("mode_id") or "").strip()
    activated = core_modes.set_mode(mode_id, source="console")
    if not activated:
        raise HTTPException(404, "mode inconnu")
    return {"ok": True, "mode": {"id": activated["id"], "name": activated.get("name", activated["id"])}}


@app.get("/api/usage")
async def get_usage() -> dict:
    """Consommation de l'API Claude : mois en cours, dernier appel, et
    l'historique mensuel pour situer la tendance."""
    summary = core_usage.summary()
    raw = core_usage.snapshot()
    return {
        **summary,
        "current": raw.get("current", {}),
        "last_call": raw.get("last_call", {}),
        "history": raw.get("history", [])[-12:],
    }


@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket) -> None:
    """Chat texte — utilisé par la Console web (Phase 2) et, depuis la
    Phase 3 suite, par la boucle vocale de l'agent desktop elle-même
    (voir agents/desktop/brain/remote_chat.py) : les deux partagent
    maintenant la même conversation/mémoire, un seul brain qui décide.
    Depuis la Phase 10, décide aussi entre conversation pure et pilotage
    PC dispatché sur le réseau (brain.core.agent) selon is_pc_command.
    """
    await websocket.accept()
    if config.CONSOLE_PASSWORD and websocket.query_params.get("token") != config.CONSOLE_PASSWORD:
        # Pas de header custom possible au handshake WebSocket depuis un
        # navigateur — le token passe donc en paramètre de requête, comme
        # web/src/lib/useConsoleAuth.js le construit.
        await websocket.close(code=4401)
        return
    try:
        while True:
            data = await websocket.receive_json()
            question = (data.get("question") or "").strip()
            if not question:
                continue

            if is_pc_command(question):
                # `device_id` peut rester None : beaucoup de questions
                # aiguillées ici ne concernent aucune machine (agenda,
                # mails, itinéraire — brain/tools.py). Refuser tout tant
                # qu'aucun agent n'est connecté rendait la Console
                # inutilisable seule, alors que le brain sait répondre.
                device_id = registry.pick_default_device()

                async def _send_status(text: str) -> None:
                    try:
                        await websocket.send_json({"type": "chat.status", "text": text})
                    except Exception:
                        pass  # connexion fermée entre-temps — sans conséquence, juste cosmétique

                def _on_activity(text: str) -> None:
                    asyncio.create_task(_send_status(text))

                # Rempli par pc_agent (F7 phase 2) : "ollama-agent" si le
                # modèle local a répondu, "claude-agent" sinon — reflète
                # dans la Console qui a réellement traité la question,
                # plutôt qu'une étiquette figée.
                answered_by = {"source": "claude-agent"}

                def _on_source(source: str) -> None:
                    answered_by["source"] = source

                pc_agent.on_activity = _on_activity
                pc_agent.on_source = _on_source
                try:
                    answer = await pc_agent.ask_with_tools(question, device_id)
                finally:
                    pc_agent.on_activity = None
                    pc_agent.on_source = None
                await websocket.send_json({"type": "chat.phrase", "text": answer or ""})
                await websocket.send_json({"type": "chat.done", "source": answered_by["source"]})
                continue

            brain_state: dict = {}
            async for phrase in _stream_sync_generator(ask_stream, question, brain_state):
                await websocket.send_json({"type": "chat.phrase", "text": phrase})
            await websocket.send_json({"type": "chat.done", "source": brain_state.get("source")})
    except WebSocketDisconnect:
        pass


@app.websocket("/ws/agent")
async def ws_agent(websocket: WebSocket) -> None:
    """Canal de contrôle d'un agent : enregistrement, heartbeat, résultats de commande."""
    await websocket.accept()
    device_id: str | None = None
    try:
        raw = await websocket.receive_json()
        try:
            msg = parse_message(raw)
        except (ValueError, ValidationError) as exc:
            await websocket.send_json(RegisterAck(device_id="", ok=False, reason=str(exc)).model_dump())
            await websocket.close()
            return

        if not isinstance(msg, DeviceRegister):
            await websocket.send_json(RegisterAck(
                device_id="", ok=False, reason="premier message attendu : device.register",
            ).model_dump())
            await websocket.close()
            return

        issued_token = None
        known = device_store.find_by_token(msg.token) if msg.token else None

        if known:
            # Reconnexion normale : le token présenté est déjà celui émis à
            # l'appairage. On fait confiance au device_id qu'il porte déjà.
            pass
        elif msg.token and pairing.consume(msg.token):
            # Premier appairage : msg.token était en fait le code affiché
            # côté Centre d'appareils, pas un vrai token — on en émet un
            # définitif que l'agent devra sauvegarder pour la suite.
            issued_token = generate_token()
            device_store.register(msg.device_id, msg.name, msg.device_type, issued_token)
        else:
            await websocket.send_json(RegisterAck(
                device_id=msg.device_id, ok=False,
                reason="token invalide, expiré, ou appareil non appairé",
            ).model_dump())
            await websocket.close()
            return

        device_id = msg.device_id
        registry.register(Device(
            device_id=msg.device_id,
            name=msg.name,
            device_type=msg.device_type,
            capabilities=list(msg.capabilities),
            websocket=websocket,
        ))
        await websocket.send_json(RegisterAck(
            device_id=msg.device_id, ok=True, issued_token=issued_token,
        ).model_dump())
        print(f"[brain] appareil connecté : {msg.name} ({msg.device_id})"
              + (" [nouvel appairage]" if issued_token else ""))

        while True:
            raw = await websocket.receive_json()
            msg = parse_message(raw)
            if isinstance(msg, DeviceStatus):
                registry.touch(msg.device_id, msg.status)
            elif isinstance(msg, CommandResult):
                registry.resolve(msg)
    except WebSocketDisconnect:
        pass
    finally:
        if device_id:
            registry.unregister(device_id)
            print(f"[brain] appareil déconnecté : {device_id}")


# Doit être monté APRÈS toutes les routes /api et /ws ci-dessus : Starlette
# essaie les routes dans l'ordre d'enregistrement, donc /api/... continue de
# matcher ses handlers avant que ce montage catch-all ne s'en charge.
# Nécessaire pour la Phase 9 (détection locale du mot d'éveil) : le
# navigateur importe dynamiquement des fichiers .wasm/.mjs, ce que le
# serveur de dev Vite refuse pour les fichiers de web/public — brain sert
# le vrai build (web/dist) sans cette restriction. `npm run build` d'abord.
_WEB_DIST = config.ROOT / "web" / "dist"
if _WEB_DIST.exists():
    app.mount("/", StaticFiles(directory=str(_WEB_DIST), html=True), name="web")
else:
    print(f"[brain] {_WEB_DIST} introuvable — lance `npm run build` dans web/ pour servir la Console ici.")


def start() -> None:
    import uvicorn
    uvicorn.run(app, host=config.HOST, port=config.PORT)


if __name__ == "__main__":
    start()

"""Configuration du brain (serveur central).

Séparée de `agents/desktop/config.py` : le brain ne connaît rien à l'audio,
au wake word ou aux seuils de barge-in — uniquement les modèles, les
chemins de données qu'il possède (mémoire, modes, usage, contexte), et le
réseau. `data/` reste physiquement le même dossier partagé qu'aujourd'hui ;
seule la logique qui le lit/l'écrit a changé de process.
"""
from __future__ import annotations

import os
import pathlib

# ── Chemins ───────────────────────────────────────────────────────────────────
ROOT = pathlib.Path(__file__).resolve().parent.parent      # …/Jarvis
DATA_DIR = ROOT / "data"
LOGS_DIR = DATA_DIR / "logs"

MEMORY_FILE = DATA_DIR / "memory.json"
MODES_FILE = DATA_DIR / "modes.json"
CURRENT_MODE_FILE = DATA_DIR / "current_mode.json"
USAGE_FILE = DATA_DIR / "usage.json"
CONTEXT_FILE = DATA_DIR / "context.json"
DEVICES_FILE = DATA_DIR / "devices.json"
# Nom délibérément différent de agents/desktop/config.py::ROUTINES_FILE
# (data/routines.json) — formats et systèmes distincts, ne pas fusionner :
# celui-ci cible plusieurs appareils via dispatch réseau, l'autre est
# mono-appareil et exécuté en local par l'agent desktop.
CROSS_DEVICE_ROUTINES_FILE = DATA_DIR / "cross_device_routines.json"
# Comptes tiers connectés (Google Calendar…) — jetons chiffrés, voir
# brain/integrations/. Jamais versionné (.gitignore), clé de chiffrement
# auto-générée à côté au premier lancement (data/integrations.key).
INTEGRATIONS_FILE = DATA_DIR / "integrations.json"
INTEGRATIONS_KEY_FILE = DATA_DIR / "integrations.key"


def ensure_dirs() -> None:
    for d in (DATA_DIR, LOGS_DIR):
        d.mkdir(parents=True, exist_ok=True)


# ── .env ──────────────────────────────────────────────────────────────────────
def _load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_env()

# ── Cerveaux ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:14b")
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
OLLAMA_CONNECT_TIMEOUT = 2
OLLAMA_READ_TIMEOUT = 150

# Prix Claude Haiku 4.5 (USD par token)
HAIKU_PRICES = {
    "input":       1.00 / 1_000_000,
    "output":      5.00 / 1_000_000,
    "cache_write": 1.25 / 1_000_000,
    "cache_read":  0.10 / 1_000_000,
}

# Utilisé par modes.match_trigger() pour ignorer un « jarvis » résiduel en
# tête de phrase transcrite — pas un réglage audio ici, juste du texte.
WAKE_WORD = "jarvis"

# ── Voix (Phase 9 — voix dans le navigateur) ─────────────────────────────────
# Mêmes valeurs que agents/desktop/config.py : même conteneur Speaches, pas de
# nouvelle dépendance. Utilisé par brain/speech.py pour la Console web.
SPEACHES_STT_URL = os.getenv("SPEACHES_STT_URL", "http://localhost:8000/v1/audio/transcriptions")
SPEACHES_TTS_URL = os.getenv("SPEACHES_TTS_URL", "http://localhost:8000/v1/audio/speech")
STT_MODEL = os.getenv("STT_MODEL", "Systran/faster-whisper-small")
TTS_MODEL = os.getenv("TTS_MODEL", "speaches-ai/piper-fr_FR-siwis-medium")
TTS_VOICE = os.getenv("TTS_VOICE", "siwis")
SPEECH_REQUEST_TIMEOUT = 20

# ── Réseau ────────────────────────────────────────────────────────────────────
HOST = os.getenv("BRAIN_HOST", "0.0.0.0")
PORT = int(os.getenv("BRAIN_PORT", "8420"))

# ── Accès Console ─────────────────────────────────────────────────────────────
# Seul rempart aujourd'hui entre "atteint le brain sur le réseau/VPN" et
# "peut piloter le PC" — vide = auth désactivée (pratique en dev local),
# à définir dans .env dès que le brain est exposé au-delà de 127.0.0.1.
CONSOLE_PASSWORD = os.getenv("CONSOLE_PASSWORD", "")

# ── Intégrations externes (Google Calendar…) ────────────────────────────────
# Client OAuth "Application Web" créé dans Google Cloud Console (API
# Calendar activée), avec GOOGLE_REDIRECT_URI déclaré tel quel comme URI de
# redirection autorisée. Voir docs/ROADMAP_DISPLAY_INTEGRATIONS.md pour la
# marche à suivre complète. Vide = le panneau Intégrations de la Console
# affiche "non configuré" au lieu du bouton de connexion.
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv(
    "GOOGLE_REDIRECT_URI", f"http://127.0.0.1:{PORT}/api/integrations/google/callback",
)
# Zoho Mail — client OAuth créé dans la Console API Zoho (api-console.zoho.<region>),
# identifiants saisis depuis la Console web (voir settings.py::set_zoho_credentials),
# pas de repli .env pour ce fournisseur (voir settings.py).
ZOHO_REDIRECT_URI = os.getenv(
    "ZOHO_REDIRECT_URI", f"http://127.0.0.1:{PORT}/api/integrations/zoho/callback",
)
# Spotify — client OAuth créé sur developer.spotify.com/dashboard, identifiants
# saisis depuis la Console web (voir settings.py::set_spotify_credentials).
SPOTIFY_REDIRECT_URI = os.getenv(
    "SPOTIFY_REDIRECT_URI", f"http://127.0.0.1:{PORT}/api/integrations/spotify/callback",
)
# Fuseau pour délimiter "aujourd'hui"/"demain"/"cette semaine" (calendar_events) —
# calculer ces bornes en UTC décalerait la journée de 1-2h par rapport à la
# réalité locale (été/hiver), faisant rater ou déborder des événements en
# bordure de journée.
TIMEZONE = os.getenv("TIMEZONE", "Europe/Paris")

# Météo (carte "weather", voir brain/weather.py) — mêmes valeurs par défaut
# que agents/desktop/config.py, dupliquées ici volontairement : le brain ne
# doit pas dépendre du package agent desktop (Windows-only par endroits)
# pour un simple appel Open-Meteo.
WEATHER_LAT = float(os.getenv("WEATHER_LAT", "43.6047"))
WEATHER_LON = float(os.getenv("WEATHER_LON", "1.4442"))
WEATHER_CITY = os.getenv("WEATHER_CITY", "Toulouse")

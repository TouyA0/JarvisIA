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

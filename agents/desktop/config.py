"""Configuration centrale de Jarvis.

Tout ce qui est réglable vit ici : chemins, URLs, modèles, seuils audio.
Les valeurs surchargeables par l'utilisateur passent par le fichier .env
à la racine du projet (mêmes noms de clés que les versions précédentes).
"""
from __future__ import annotations

import os
import pathlib

# ── Chemins ───────────────────────────────────────────────────────────────────
AGENT_DIR = pathlib.Path(__file__).resolve().parent          # …/Jarvis/agents/desktop
ROOT = AGENT_DIR.parent.parent                                 # …/Jarvis (racine projet, .env + data/ partagés)
DATA_DIR = ROOT / "data"
NOTES_DIR = DATA_DIR / "notes"
LOGS_DIR = DATA_DIR / "logs"

MEMORY_FILE = DATA_DIR / "memory.json"
COMMANDS_FILE = DATA_DIR / "commands.json"
MODES_FILE = DATA_DIR / "modes.json"
CURRENT_MODE_FILE = DATA_DIR / "current_mode.json"
USAGE_FILE = DATA_DIR / "usage.json"
CONTEXT_FILE = DATA_DIR / "context.json"
ROUTINES_FILE = DATA_DIR / "routines.json"

WAKE_WORD_MODEL_PATH = AGENT_DIR / "wakeword" / "jarvis_wakeword.tflite"
BUILD_PREVIEW_DIR = AGENT_DIR / "build_preview"


def ensure_dirs() -> None:
    for d in (DATA_DIR, NOTES_DIR, LOGS_DIR):
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

# Cerveau hybride : la conversation pure (sans outils) part d'abord vers un
# modèle local Ollama — gratuit, privé, hors-ligne. Claude reste seul à piloter
# le PC (brain.agent), là où la fiabilité du tool-use compte vraiment.
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:14b")
# Le modèle reste chargé en VRAM ce délai après la dernière question, pour
# éviter de repayer le chargement (~2 min pour un 14B) à chaque question isolée.
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
OLLAMA_CONNECT_TIMEOUT = 2    # échec rapide si Ollama n'est pas lancé du tout
OLLAMA_READ_TIMEOUT = 150     # tolère un chargement à froid du modèle (~2 min)

# Prix Claude Haiku 4.5 (USD par token)
HAIKU_PRICES = {
    "input":       1.00 / 1_000_000,
    "output":      5.00 / 1_000_000,
    "cache_write": 1.25 / 1_000_000,
    "cache_read":  0.10 / 1_000_000,
}

# ── STT / TTS (Speaches, local via Docker) ────────────────────────────────────
SPEACHES_STT_URL = os.getenv("SPEACHES_STT_URL", "http://localhost:8000/v1/audio/transcriptions")
SPEACHES_TTS_URL = os.getenv("SPEACHES_TTS_URL", "http://localhost:8000/v1/audio/speech")
STT_MODEL = os.getenv("STT_MODEL", "Systran/faster-whisper-small")
TTS_MODEL = os.getenv("TTS_MODEL", "speaches-ai/piper-fr_FR-siwis-medium")
TTS_VOICE = os.getenv("TTS_VOICE", "siwis")
REQUEST_TIMEOUT = 20
SHORT_REQUEST_TIMEOUT = 8

# ── Wake word ─────────────────────────────────────────────────────────────────
WAKE_WORD = "jarvis"
WAKE_WORD_SAMPLE_RATE = 16000
WAKE_WORD_WINDOW_SECONDS = 1.5
WAKE_WORD_WINDOW_SAMPLES = int(WAKE_WORD_SAMPLE_RATE * WAKE_WORD_WINDOW_SECONDS)
WAKE_WORD_STEP_CHUNKS = 4
WAKE_WORD_THRESHOLD = 0.90
WAKE_WORD_CONSECUTIVE_HITS = 2
WAKE_WORD_COOLDOWN_SECONDS = 2.0
# Niveau de référence après normalisation — DOIT être identique à TARGET_RMS
# dans wakeword/entrainer.py, sinon le modèle score hors de sa distribution.
WAKE_WORD_TARGET_RMS = 0.05
# Filtre « y a-t-il du son ? » avant de scorer. Depuis la normalisation il ne
# sert plus qu'à éviter de scorer du silence.
WAKE_WORD_MIN_RMS = 0.0012

# ── Interruption (barge-in) ───────────────────────────────────────────────────
# Profils selon la sortie audio. Au casque il n'y a aucune boucle acoustique :
# on peut être sensible. Sur haut-parleurs le micro réentend Jarvis — sans
# annulation d'écho il faut être nettement plus strict, sinon il s'interrompt
# lui-même en permanence.
INTERRUPT_PROFILES = {
    "casque":       {"start_delay": 0.20, "vad": 0.55, "min_consecutive": 2, "min_rms": 0.006},
    "haut-parleur": {"start_delay": 0.60, "vad": 0.80, "min_consecutive": 5, "min_rms": 0.020},
}
INTERRUPT_PROFILES["inconnu"] = INTERRUPT_PROFILES["haut-parleur"]  # défaut prudent
OUTPUT_DEVICE_RECHECK_SECONDS = 5.0

HEADSET_HINTS = ("casque", "ecouteur", "headset", "headphone", "earphone", "earbud",
                 "airpod", "arctis", "hyperx", "steelseries", "jabra", "bose",
                 "sennheiser", "wh-1000", "buds", "quietcomfort")
SPEAKER_HINTS = ("haut-parleur", "hautparleur", "speaker", "hdmi", "display",
                 "monitor", "televiseur", "realtek digital")

# ── Services ──────────────────────────────────────────────────────────────────
# Météo : Open-Meteo, gratuit et sans clé. Coordonnées par défaut : Toulouse.
WEATHER_LAT = float(os.getenv("WEATHER_LAT", "43.6047"))
WEATHER_LON = float(os.getenv("WEATHER_LON", "1.4442"))
WEATHER_CITY = os.getenv("WEATHER_CITY", "Toulouse")
WEATHER_REFRESH_MINUTES = 30

BOOT_SOUND = os.getenv("BOOT_SOUND", "1") != "0"
GLOBAL_HOTKEY = os.getenv("GLOBAL_HOTKEY", "1") != "0"   # Ctrl+Alt+J

# ── Brain (connexion réseau, agent_client.py) ────────────────────────────────
# Désactivé par défaut : le brain ne fait pas encore partie du lancement
# quotidien (start_jarvis.bat ne le démarre pas). Activer avec BRAIN_ENABLED=1
# dans .env une fois prêt à tester — sinon aucun changement de comportement.
BRAIN_ENABLED = os.getenv("BRAIN_ENABLED", "0") == "1"
BRAIN_URL = os.getenv("BRAIN_URL", "ws://127.0.0.1:8420/ws/agent")
DEVICE_ID_FILE = DATA_DIR / "device_id.json"

# ── Divers ────────────────────────────────────────────────────────────────────
# Timeout d'écoute après le wake word avant retour en veille (secondes)
CONVERSATION_TIMEOUT = 20
# Nombre de questions entre deux consolidations de mémoire en arrière-plan
MEMORY_UPDATE_EVERY = 5

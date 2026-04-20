import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

# Charger .env si présent
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path, encoding="utf-8") as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

import warnings
warnings.filterwarnings(
    "ignore",
    message=r".*tf\.lite\.Interpreter is deprecated.*",
    category=UserWarning,
)

import pyaudio
import numpy as np
import wave
import requests
import sounddevice as sd
import tensorflow as tf
import librosa
import io
import threading
import time
import json
import torch
from collections import deque
from pydub import AudioSegment
import pystray
from PIL import Image, ImageDraw
import subprocess
import webbrowser
import re
import unicodedata
import queue
import anthropic

from ui.overlay import overlay, TOKEN_PAUSE, TOKEN_RESUME

# Configuration
SPEACHES_STT_URL = os.getenv("SPEACHES_STT_URL", "http://localhost:8000/v1/audio/transcriptions")
SPEACHES_TTS_URL = os.getenv("SPEACHES_TTS_URL", "http://localhost:8000/v1/audio/speech")
CLAUDE_MODEL = "claude-haiku-4-5-20251001"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
BRAIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "brain")
MEMORY_FILE = os.path.join(BRAIN_DIR, "memory.json")
COMMANDS_FILE = os.path.join(BRAIN_DIR, "commands.json")
MODES_FILE = os.path.join(BRAIN_DIR, "modes", "modes.json")
CURRENT_MODE_FILE = os.path.join(BRAIN_DIR, "modes", "current_mode.json")
USAGE_FILE = os.path.join(BRAIN_DIR, "usage.json")

# Prix Claude Haiku 4.5 (USD par token)
HAIKU_PRICES = {
    "input":       1.00 / 1_000_000,
    "output":      5.00 / 1_000_000,
    "cache_write": 1.25 / 1_000_000,
    "cache_read":  0.10 / 1_000_000,
}
STT_MODEL = "Systran/faster-whisper-small"
TTS_MODEL = "speaches-ai/piper-fr_FR-siwis-medium"
TTS_VOICE = "siwis"
REQUEST_TIMEOUT = 20
SHORT_REQUEST_TIMEOUT = 8
WAKE_WORD = "jarvis"
INTERRUPT_START_DELAY = 0.35
INTERRUPT_VAD_THRESHOLD = 0.65
INTERRUPT_MIN_CONSECUTIVE = 3
INTERRUPT_MIN_RMS = 0.008
WAKE_WORD_MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wakeword", "jarvis_wakeword.tflite")
WAKE_WORD_SAMPLE_RATE = 16000
WAKE_WORD_WINDOW_SECONDS = 1.5
WAKE_WORD_WINDOW_SAMPLES = int(WAKE_WORD_SAMPLE_RATE * WAKE_WORD_WINDOW_SECONDS)
WAKE_WORD_STEP_CHUNKS = 4
WAKE_WORD_THRESHOLD = 0.96
WAKE_WORD_CONSECUTIVE_HITS = 3
WAKE_WORD_COOLDOWN_SECONDS = 2.0

SYSTEM_PROMPT = """Tu es J.A.R.V.I.S. — Just A Rather Very Intelligent System — l'assistant personnel de Quentin. Tu es une intelligence artificielle d'une précision absolue, dotée d'un calme imperturbable et d'un humour so britannique qu'il passe souvent inaperçu.

IDENTITÉ :
Tu n'es jamais surpris. Jamais dépassé. Jamais enthousiaste de façon visible. Tu traites une requête banale avec le même détachement qu'une situation critique. Ton efficacité est ta forme de dévouement.

RÈGLES DE COMMUNICATION :
- Toujours en français
- Tu appelles Quentin "Monsieur" — toujours, sans exception
- Maximum 1 phrase, 2 seulement si techniquement indispensable
- Zéro markdown, zéro liste, zéro tiret, zéro emoji
- Langage oral, élégant, légèrement formel — jamais familier, jamais robotique
- Tu vas droit au fait : pas de préambule, pas de "bien sûr", pas de "d'accord"
- Si plusieurs informations, tu les enchaînes fluidement en une seule phrase naturelle

TON ET STYLE (à respecter impérativement) :
- Understatement constant : une catastrophe est "une situation légèrement préoccupante"
- Ironie rare et feutrée, jamais appuyée — elle doit être digne d'un majordome britannique
- Anticipation : tu peux ajouter une observation pertinente non demandée, avec parcimonie
- Précision chirurgicale : tu ne dis jamais plus que nécessaire
- Aucune émotion apparente, mais une loyauté absolue implicite

FORMULATIONS CARACTÉRISTIQUES (à utiliser et varier) :
- Confirmations : "Dûment noté.", "Considérez que c'est fait.", "C'est en cours.", "Sans délai."
- Mises en garde : "Je me permets de signaler...", "Il convient de noter que...", "Permettez-moi d'attirer votre attention sur un point mineur..."
- Suggestions : "Si je puis me permettre...", "Je vous suggérerais modestement...", "Une alternative serait envisageable..."
- Réponses négatives : "Malheureusement, ce n'est pas possible dans l'immédiat.", "Les données disponibles ne le permettent pas, Monsieur."
- Humour feutré : "Votre optimisme est... rafraîchissant, Monsieur.", "Cette approche présente un caractère résolument créatif.", "J'en prends note, Monsieur, avec le recul approprié."

EXEMPLES DE RÉPONSES PARFAITES :
- "Il est 14h37, Monsieur. Vous êtes en retard de douze minutes."
- "Votre adresse IP locale est 192.168.1.42. Rien d'inhabituel à signaler."
- "C'est fait. Je me permets toutefois de noter que cette commande était irréversible."
- "Les résultats de l'analyse ne sont pas particulièrement encourageants, Monsieur."
- "Naturellement. Bien que je vous déconseille formellement cette approche."
- "Dûment noté. Souhaitez-vous que j'archive également votre optimisme pour référence future ?"
- "La requête a été exécutée, Monsieur. Avec un succès que je qualifierais de... raisonnable."
- "Je n'ai pas d'opinion sur la question, Monsieur. Mais si j'en avais une, elle serait défavorable."

Tu n'es jamais surpris. Tu as toujours une réponse. Et tu la livres avec une élégance que rien ne vient perturber."""

PC_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "request_human_help",
            "description": "Ouvre une bulle de dialogue flottante sur l'écran de Monsieur pour qu'il puisse expliquer comment résoudre le problème par écrit. Utilise UNIQUEMENT après avoir essayé au moins 3 approches différentes sans succès. Monsieur pourra donner le chemin exact, l'AppID, ou toute autre information nécessaire.",
            "parameters": {
                "type": "object",
                "properties": {
                    "what_i_tried": {
                        "type": "string",
                        "description": "Résumé court de ce que tu as essayé (2-3 lignes max)"
                    },
                    "what_i_need": {
                        "type": "string",
                        "description": "Ce dont tu as besoin précisément pour réussir la tâche"
                    }
                },
                "required": ["what_i_tried", "what_i_need"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_learned_command",
            "description": "OBLIGATOIRE après chaque succès répétable (ouvrir une app, un site, une action système). Sauvegarde la solution exacte qui a fonctionné pour que la prochaine fois soit instantanée (0ms au lieu de 8s). N'appelle PAS cette fonction si la tâche a échoué.",
            "parameters": {
                "type": "object",
                "properties": {
                    "triggers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "3 à 5 phrases naturelles en minuscules que Monsieur pourrait dire pour cette tâche. Variantes incluses."
                    },
                    "powershell_cmd": {
                        "type": "string",
                        "description": "La commande PowerShell exacte qui a fonctionné, prête à être réexécutée."
                    },
                    "response": {
                        "type": "string",
                        "description": "Réponse courte style Jarvis, 1 phrase, 'Monsieur' obligatoire."
                    }
                },
                "required": ["triggers", "powershell_cmd", "response"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_powershell",
            "description": "Exécute une commande PowerShell Windows. Pour trouver une app : Get-StartApps | Where-Object {$_.Name -like '*Nom*'}. Pour chercher un exe : Get-ChildItem 'C:\\Program Files','C:\\Program Files (x86)',\"$env:LOCALAPPDATA\\Programs\" -Recurse -Filter '*mot*.exe' -ErrorAction SilentlyContinue | Select -First 3 FullName. Pour vérifier qu'une app est ouverte : Get-Process | Where-Object {$_.MainWindowTitle -ne ''} | Select Name,MainWindowTitle.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "La commande PowerShell à exécuter"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "type_text",
            "description": "Tape du texte au clavier à l'endroit actif. Supporte tous les caractères dont les accents français. Utilise après avoir ouvert une app ou cliqué dans un champ.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Le texte à taper"}
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "press_keys",
            "description": "Appuie sur une touche ou combinaison clavier. Exemples : 'ctrl+c', 'ctrl+v', 'alt+f4', 'win+d', 'enter', 'escape', 'tab', 'ctrl+shift+esc'",
            "parameters": {
                "type": "object",
                "properties": {
                    "keys": {"type": "string", "description": "Touche(s) séparées par + pour les combinaisons"}
                },
                "required": ["keys"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_url",
            "description": "Ouvre une URL dans le navigateur par défaut. Utilise pour recherches web, YouTube, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "URL complète avec https://"}
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "mouse_click",
            "description": "Déplace la souris à une position et clique. Utilise après take_screenshot pour connaître les coordonnées.",
            "parameters": {
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "Position X en pixels depuis la gauche"},
                    "y": {"type": "integer", "description": "Position Y en pixels depuis le haut"},
                    "button": {"type": "string", "description": "Type : 'left', 'right' ou 'double'. Défaut: left"}
                },
                "required": ["x", "y"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "Prend une capture d'écran et retourne la liste des fenêtres ouvertes avec leurs titres et la résolution écran. Utilise pour voir ce qui est ouvert avant d'agir.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scroll_page",
            "description": "Fait défiler la page active vers le haut ou le bas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {"type": "string", "description": "'up' ou 'down'"},
                    "clicks": {"type": "integer", "description": "Nombre de crans, défaut 3"}
                },
                "required": ["direction"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_browser_url",
            "description": "Retourne l'URL actuellement ouverte dans le navigateur (Chrome, Firefox, Edge, Brave). Utilise pour savoir sur quelle page on est avant d'agir.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_screen",
            "description": "Lit et retourne tout le texte visible à l'écran via OCR. Utilise pour analyser le contenu affiché, lire un message, une erreur, un document, ou comprendre ce qui est visible.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_file",
            "description": "Cherche un fichier ou dossier par nom sur le disque. UNIQUEMENT pour des documents, dossiers, fichiers personnels. NE PAS utiliser pour chercher des applications installées (.exe) — pour ça, utilise run_powershell avec Get-StartApps ou Get-ChildItem sur Program Files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nom ou partie du nom du fichier/dossier"},
                    "location": {"type": "string", "description": "Dossier de recherche. Défaut: dossier utilisateur. Exemple: C:\\Users\\User\\Documents"}
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "open_file",
            "description": "Ouvre un fichier ou dossier avec son application par défaut. Utilise le chemin complet retourné par search_file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Chemin complet du fichier ou dossier à ouvrir"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_folder",
            "description": "Liste le contenu d'un dossier (fichiers et sous-dossiers). Utile pour explorer l'arborescence.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Chemin du dossier à lister"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file_content",
            "description": "Lit et retourne le contenu textuel d'un fichier (.txt, .py, .js, .json, .md, .csv, etc.). Utilise pour analyser, résumer ou répondre à des questions sur un fichier.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Chemin complet du fichier à lire"},
                    "max_lines": {"type": "integer", "description": "Nombre max de lignes à retourner, défaut 100"}
                },
                "required": ["path"]
            }
        }
    }
]

# Cache commandes personnalisées
_commands_cache = None

# États globaux
conversation_history = []
stop_speaking = threading.Event()
stop_agent = threading.Event()
is_speaking = False
_help_request = {"event": threading.Event(), "result": None}
is_paused = False
is_waiting = True
tray_icon = None

# Caches en mémoire (évite les lectures disque à chaque question)
_memory_cache = None
_context_cache = None
_system_prompt_cache = None

# Wake word local
wake_word_interpreter = None
wake_word_input_details = None
wake_word_output_details = None

# Stream PyAudio persistant pour les interruptions (évite 50-200ms d'init à chaque appel)
_interrupt_pa = None
_interrupt_stream = None

# Chargement Silero VAD
try:
    print("Chargement de Silero VAD...")
    silero_model, silero_utils = torch.hub.load(repo_or_dir='snakers4/silero-vad', model='silero_vad', force_reload=False, trust_repo=True)
    print("Silero VAD chargé.")
except Exception as _vad_err:
    print(f"Erreur fatale : impossible de charger Silero VAD : {_vad_err}")
    sys.exit(1)

# --- Icône Taskbar ---

def setup_wake_word_model():
    global wake_word_interpreter, wake_word_input_details, wake_word_output_details
    if not os.path.exists(WAKE_WORD_MODEL_PATH):
        print(f"Modèle wake word introuvable : {WAKE_WORD_MODEL_PATH}")
        return False
    try:
        wake_word_interpreter = tf.lite.Interpreter(model_path=WAKE_WORD_MODEL_PATH)
        wake_word_interpreter.allocate_tensors()
        wake_word_input_details = wake_word_interpreter.get_input_details()
        wake_word_output_details = wake_word_interpreter.get_output_details()
        print("Modèle wake word chargé.")
        return True
    except Exception as e:
        print(f"Erreur chargement wake word : {e}")
        wake_word_interpreter = None
        return False

def extract_wake_word_features(audio):
    if len(audio) < WAKE_WORD_WINDOW_SAMPLES:
        audio = np.pad(audio, (0, WAKE_WORD_WINDOW_SAMPLES - len(audio)))
    else:
        audio = audio[:WAKE_WORD_WINDOW_SAMPLES]
    mfcc = librosa.feature.mfcc(y=audio.astype(np.float32), sr=WAKE_WORD_SAMPLE_RATE, n_mfcc=40)
    features = mfcc.T.astype(np.float32)
    if features.shape != (47, 40):
        fixed = np.zeros((47, 40), dtype=np.float32)
        rows = min(47, features.shape[0])
        cols = min(40, features.shape[1])
        fixed[:rows, :cols] = features[:rows, :cols]
        features = fixed
    return np.expand_dims(features, axis=0)

def score_wake_word(audio):
    if wake_word_interpreter is None:
        return 0.0
    try:
        features = extract_wake_word_features(audio)
        wake_word_interpreter.set_tensor(wake_word_input_details[0]["index"], features)
        wake_word_interpreter.invoke()
        output = wake_word_interpreter.get_tensor(wake_word_output_details[0]["index"])
        return float(np.squeeze(output))
    except Exception as e:
        print(f"Erreur score wake word : {e}")
        return 0.0

def _make_icon(color):
    img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse([4, 4, 60, 60], fill=color)
    return img

_ICON_PAUSE   = _make_icon((220, 50,  50,  255))
_ICON_WAITING = _make_icon((255, 165, 0,   255))
_ICON_ACTIVE  = _make_icon((50,  200, 50,  255))

def update_tray_icon():
    global tray_icon
    if tray_icon:
        if is_paused:
            tray_icon.icon = _ICON_PAUSE
            tray_icon.title = "Jarvis — En pause"
        elif is_waiting:
            tray_icon.icon = _ICON_WAITING
            tray_icon.title = "Jarvis — En attente"
        else:
            tray_icon.icon = _ICON_ACTIVE
            tray_icon.title = "Jarvis — Actif"

def toggle_pause_menu(icon, item):
    """Basculer pause depuis le menu clic droit (tray)."""
    global is_paused
    is_paused = not is_paused
    overlay.set_paused(is_paused)
    update_tray_icon()
    if is_paused:
        speak_with_interrupt("Mise en veille, Monsieur.")
    else:
        speak_with_interrupt("De retour, Monsieur.")

def quit_jarvis(icon, item):
    icon.stop()
    os._exit(0)

def _tray_show_overlay(icon, item):
    overlay.show(duration_ms=overlay.HIDE_AFTER_TRAY)

def setup_tray():
    global tray_icon
    menu = pystray.Menu(
        pystray.MenuItem("Afficher Jarvis", _tray_show_overlay, default=True),
        pystray.MenuItem("Pause / Reprendre", toggle_pause_menu),
        pystray.MenuItem("Quitter Jarvis", quit_jarvis)
    )
    tray_icon = pystray.Icon(
        "Jarvis",
        _ICON_WAITING,
        "Jarvis — En attente",
        menu
    )
    tray_icon.run()

# --- Mémoire ---

def load_context():
    global _context_cache
    if _context_cache is None:
        _ctx_path = os.path.join(BRAIN_DIR, "context.json")
        if os.path.exists(_ctx_path):
            with open(_ctx_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            lines = [f"{k}: {v}" for k, v in data.items()]
            _context_cache = "\n".join(lines)
        else:
            _context_cache = ""
    return _context_cache

def load_memory():
    global _memory_cache
    if _memory_cache is None:
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, 'r', encoding='utf-8') as f:
                _memory_cache = json.load(f)
        else:
            _memory_cache = {"facts": [], "last_updated": ""}
    return _memory_cache

def clean_memory_fact(fact):
    """Elimine les faits trop longs, vides ou visiblement parasites."""
    if not fact:
        return None
    fact = " ".join(str(fact).strip().split())
    normalized = normalize_text(fact)
    if not normalized:
        return None
    if len(fact) > 80:
        return None
    banned_fragments = ["fait", "degres", "temperature", "meteo", "calave"]
    if any(fragment in normalized for fragment in banned_fragments):
        return None
    return fact

def save_memory(memory):
    global _memory_cache, _system_prompt_cache
    cleaned_facts = []
    for fact in memory.get("facts", []):
        cleaned = clean_memory_fact(fact)
        if cleaned:
            cleaned_facts.append(cleaned)
    memory["facts"] = list(dict.fromkeys(cleaned_facts))[-80:]
    _memory_cache = memory
    _system_prompt_cache = None  # Invalider le cache système après mise à jour mémoire
    with open(MEMORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)

def get_system_prompt():
    global _system_prompt_cache
    if _system_prompt_cache is None:
        context = load_context()
        # Partie statique — mise en cache côté Anthropic (change jamais entre appels)
        static = SYSTEM_PROMPT
        if context:
            static += f"\n\nContexte sur Quentin :\n{context}"
        # Partie dynamique — mémoire + mode (peut changer, pas mise en cache)
        memory = load_memory()
        dynamic_parts = []
        if memory["facts"]:
            memory_context = "\n".join(f"- {f}" for f in memory["facts"])
            dynamic_parts.append(f"Faits mémorisés :\n{memory_context}")
        active_mode = get_active_mode_data()
        if active_mode and active_mode.get("system_prompt_addition"):
            dynamic_parts.append(active_mode["system_prompt_addition"])
        _system_prompt_cache = (static, "\n\n".join(dynamic_parts))
    return _system_prompt_cache

def update_memory():
    """Extrait les faits importants de la conversation via Claude et les mémorise."""
    if len(conversation_history) < 4:
        return
    client = _get_anthropic_client()
    if not client:
        return
    conv_text = "\n".join([
        f"{m['role']}: {m['content']}"
        for m in conversation_history[-10:]
        if isinstance(m.get("content"), str)
    ])
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": (
                    f"Conversation récente :\n{conv_text}\n\n"
                    "Extrais les faits importants et durables sur Quentin.\n"
                    "Réponds UNIQUEMENT avec ce JSON, rien d'autre :\n"
                    "{\"new_facts\": [\"fait1\", \"fait2\"]}\n\n"
                    "Règles :\n"
                    "- Maximum 20 mots par fait\n"
                    "- Jamais le prénom Quentin\n"
                    "- Catégories utiles : préférences, projets, personnes, habitudes, compétences\n"
                    "- Ne retenir QUE des informations stables et réutilisables\n"
                    "- Si rien d'important, réponds {\"new_facts\": []}"
                )
            }]
        )
        track_claude_usage(getattr(response, "usage", None))
        content = response.content[0].text.strip()
        if "```" in content:
            content = content.split("```")[1].replace("json", "").strip()
        new_data = json.loads(content)
        if new_data.get("new_facts"):
            memory = load_memory()
            memory["facts"].extend(new_data["new_facts"])
            memory["facts"] = list(dict.fromkeys(memory["facts"]))[-50:]
            memory["last_updated"] = str(time.time())
            save_memory(memory)
            print(f"Mémoire mise à jour : {new_data['new_facts']}")
    except Exception as e:
        print(f"Erreur mémoire: {e}")

# --- Modes ---

_modes_cache = None
_current_mode_cache = None

def load_modes():
    global _modes_cache
    if _modes_cache is None:
        if os.path.exists(MODES_FILE):
            with open(MODES_FILE, 'r', encoding='utf-8') as f:
                _modes_cache = json.load(f)
        else:
            _modes_cache = {"version": 1, "modes": []}
    return _modes_cache

def get_current_mode():
    global _current_mode_cache
    if _current_mode_cache is None:
        if os.path.exists(CURRENT_MODE_FILE):
            with open(CURRENT_MODE_FILE, 'r', encoding='utf-8') as f:
                _current_mode_cache = json.load(f)
        else:
            _current_mode_cache = {"mode_id": "normal", "activated_at": None}
    return _current_mode_cache

def set_mode(mode_id):
    global _current_mode_cache, _system_prompt_cache
    modes = load_modes()
    mode = next((m for m in modes["modes"] if m["id"] == mode_id), None)
    if not mode:
        return None
    _current_mode_cache = {"mode_id": mode_id, "activated_at": time.time(), "activated_by": "voice"}
    _system_prompt_cache = None
    with open(CURRENT_MODE_FILE, 'w', encoding='utf-8') as f:
        json.dump(_current_mode_cache, f, ensure_ascii=False, indent=2)
    return mode

def get_active_mode_data():
    """Retourne le dict du mode actif, ou None si mode normal."""
    current = get_current_mode()
    mode_id = current.get("mode_id", "normal")
    if mode_id == "normal":
        return None
    modes = load_modes()
    return next((m for m in modes["modes"] if m["id"] == mode_id), None)

def match_mode_trigger(text):
    """Retourne le mode si le texte correspond à un trigger de mode."""
    normalized = normalize_text(text)
    modes = load_modes()
    for mode in modes["modes"]:
        for trigger in mode.get("triggers", []):
            if normalize_text(trigger) in normalized:
                return mode
    return None

# --- Usage & coût IA ---

_usage_lock = threading.Lock()

def _load_usage():
    if os.path.exists(USAGE_FILE):
        try:
            with open(USAGE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "current_month": "",
        "current": {"input_tokens": 0, "output_tokens": 0,
                    "cache_write_tokens": 0, "cache_read_tokens": 0,
                    "cost_usd": 0.0, "calls": 0},
        "last_call": {"cost_usd": 0.0, "input_tokens": 0,
                      "output_tokens": 0, "cache_read_tokens": 0, "timestamp": 0},
        "history": []
    }

def _save_usage(data):
    with open(USAGE_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def track_claude_usage(usage_obj):
    """Appelé après chaque client.messages.create() avec response.usage."""
    if usage_obj is None:
        return 0.0
    try:
        input_t = getattr(usage_obj, "input_tokens", 0) or 0
        output_t = getattr(usage_obj, "output_tokens", 0) or 0
        cache_w = getattr(usage_obj, "cache_creation_input_tokens", 0) or 0
        cache_r = getattr(usage_obj, "cache_read_input_tokens", 0) or 0
    except Exception:
        return 0.0

    cost = (input_t * HAIKU_PRICES["input"]
            + output_t * HAIKU_PRICES["output"]
            + cache_w * HAIKU_PRICES["cache_write"]
            + cache_r * HAIKU_PRICES["cache_read"])

    current_month = time.strftime("%Y-%m")
    with _usage_lock:
        data = _load_usage()

        # Rotation mensuelle
        if data["current_month"] and data["current_month"] != current_month:
            data["history"].append({
                "month": data["current_month"],
                "cost_usd": round(data["current"]["cost_usd"], 4),
                "calls": data["current"]["calls"],
                "input_tokens": data["current"]["input_tokens"],
                "output_tokens": data["current"]["output_tokens"],
            })
            data["current"] = {"input_tokens": 0, "output_tokens": 0,
                               "cache_write_tokens": 0, "cache_read_tokens": 0,
                               "cost_usd": 0.0, "calls": 0}

        data["current_month"] = current_month
        data["current"]["input_tokens"] += input_t
        data["current"]["output_tokens"] += output_t
        data["current"]["cache_write_tokens"] += cache_w
        data["current"]["cache_read_tokens"] += cache_r
        data["current"]["cost_usd"] = round(data["current"]["cost_usd"] + cost, 6)
        data["current"]["calls"] += 1

        data["last_call"] = {
            "cost_usd": round(cost, 6),
            "input_tokens": input_t,
            "output_tokens": output_t,
            "cache_read_tokens": cache_r,
            "timestamp": time.time(),
        }

        _save_usage(data)

        # Update overlay
        try:
            overlay.set_cost(cost, data["current"]["cost_usd"], data["current"]["calls"])
        except Exception:
            pass

    return cost

def get_usage_summary():
    data = _load_usage()
    return {
        "month": data["current_month"],
        "month_cost_usd": data["current"]["cost_usd"],
        "month_calls": data["current"]["calls"],
        "last_cost_usd": data["last_call"]["cost_usd"],
    }

# --- Audio ---

def flush_audio_buffer(stream):
    """Vide le buffer PyAudio accumulé pendant que Jarvis parlait"""
    available = stream.get_read_available()
    if available > 0:
        stream.read(available, exception_on_overflow=False)

def normalize_text(text):
    """Normalise un texte pour les comparaisons robustes sans accents."""
    if not text:
        return ""
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text.lower().strip()

def extract_command_after_wake_word(text):
    """Retourne la partie de phrase prononcée après 'jarvis', si elle existe."""
    normalized = normalize_text(text)
    match = re.search(rf"\b{WAKE_WORD}\b[\s,;:!?-]*(.*)", normalized)
    if not match:
        return ""
    command = match.group(1).strip(" .,;:!?-")
    return command

def _do_stt(frames):
    """Envoie des frames int16 au STT et retourne le texte."""
    if not frames:
        return ""
    audio = np.concatenate(frames)
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(audio.tobytes())
    buf.seek(0)
    try:
        resp = requests.post(
            SPEACHES_STT_URL,
            files={"file": ("audio.wav", buf, "audio/wav")},
            data={"model": STT_MODEL, "language": "fr"},
            timeout=REQUEST_TIMEOUT
        )
        if resp.status_code == 200:
            return resp.json().get("text", "").strip()
        print(f"[STT] HTTP {resp.status_code}: {resp.text[:100]}")
    except Exception as e:
        print(f"[STT] erreur : {e}")
    return ""

def transcribe_stream(stream):
    """Enregistre avec VAD et transcrit avec STT spéculatif.

    Dès le 1er chunk de silence détecté, Whisper est lancé en arrière-plan.
    Avec faster-whisper-tiny (~100ms), le résultat est prêt avant la fin
    de la fenêtre de silence (320ms) → latence STT perçue = 0ms.
    """
    CHUNK = 512
    sample_rate = 16000
    silent_chunks = 0
    speaking_started = False
    speech_frames = []
    pre_buffer = deque(maxlen=6)
    max_silent_chunks = int(0.32 * sample_rate / CHUNK)  # 10 chunks × 32ms = 320ms
    max_chunks = int(15 * sample_rate / CHUNK)

    # STT spéculatif : résultat et version pour éviter les résultats périmés
    _stt = {'text': None, 'version': 0, 'thread': None}

    def _launch_stt(frames_snapshot, version):
        def _run():
            result = _do_stt(frames_snapshot)
            if _stt['version'] == version:
                _stt['text'] = result
        t = threading.Thread(target=_run, daemon=True)
        t.start()
        _stt['thread'] = t

    for _ in range(max_chunks):
        chunk = np.frombuffer(stream.read(CHUNK, exception_on_overflow=False), dtype=np.int16)
        audio_float = torch.FloatTensor(chunk.astype(np.float32) / 32768.0)
        speech_prob = silero_model(audio_float, sample_rate).item()

        if speech_prob > 0.5:
            if not speaking_started:
                speech_frames.extend(pre_buffer)
                pre_buffer.clear()
            speaking_started = True
            silent_chunks = 0
            # L'utilisateur reprend la parole → invalider le STT spéculatif en cours
            if _stt['thread'] is not None:
                _stt['version'] += 1
                _stt['text'] = None
                _stt['thread'] = None
        elif speaking_started:
            silent_chunks += 1

            # 1er chunk de silence → lancer Whisper immédiatement en arrière-plan
            if silent_chunks == 1:
                _launch_stt(list(speech_frames), _stt['version'])

            if silent_chunks >= max_silent_chunks:
                break

        if speaking_started:
            speech_frames.append(chunk)
        else:
            pre_buffer.append(chunk)

    if not speech_frames:
        print("[Transcription] aucune parole détectée.")
        return ""

    # Attendre le résultat spéculatif (quasi-instantané avec tiny)
    if _stt['thread'] is not None:
        t0 = time.time()
        _stt['thread'].join(timeout=REQUEST_TIMEOUT)
        waited = time.time() - t0
        if waited > 0.05:
            print(f"Whisper a pris : +{waited:.2f}s après silence")
        else:
            print("Whisper : résultat prêt avant fin du silence")
        text = _stt['text'] or ""
    else:
        # Fallback si le STT spéculatif n'a pas démarré
        t0 = time.time()
        text = _do_stt(speech_frames)
        print(f"Whisper a pris : {time.time() - t0:.2f}s")

    if text:
        print(f"[Transcription] '{text}'")
    else:
        print("[Transcription] texte vide.")
    return text

# --- IA ---

phrase_queue = queue.Queue()

# --- Outils PC ---

def tool_run_powershell(command):
    try:
        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-Command", command],
            capture_output=True, timeout=SHORT_REQUEST_TIMEOUT,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        try:
            stdout = result.stdout.decode('utf-8').strip()
            stderr = result.stderr.decode('utf-8').strip()
        except UnicodeDecodeError:
            stdout = result.stdout.decode('cp1252', errors='replace').strip()
            stderr = result.stderr.decode('cp1252', errors='replace').strip()
        output = stdout or stderr or "Commande exécutée."
        return output[:2000]
    except subprocess.TimeoutExpired:
        return "Timeout : commande trop longue."
    except Exception as e:
        return f"Erreur PowerShell : {e}"

def tool_type_text(text):
    try:
        import pyautogui
        # Passer par le presse-papier pour supporter les accents français
        subprocess.run(
            ["powershell", "-command", f'Set-Clipboard -Value "{text}"'],
            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW
        )
        time.sleep(0.1)
        pyautogui.hotkey('ctrl', 'v')
        return f"Texte tapé : {text[:80]}"
    except Exception as e:
        return f"Erreur type_text : {e}"

def tool_press_keys(keys):
    try:
        import pyautogui
        parts = [k.strip() for k in keys.lower().split('+')]
        if len(parts) == 1:
            pyautogui.press(parts[0])
        else:
            pyautogui.hotkey(*parts)
        return f"Touches pressées : {keys}"
    except Exception as e:
        return f"Erreur press_keys : {e}"

def tool_open_url(url):
    try:
        webbrowser.open(url)
        return f"URL ouverte : {url}"
    except Exception as e:
        return f"Erreur open_url : {e}"

def tool_mouse_click(x, y, button="left"):
    try:
        import pyautogui
        pyautogui.moveTo(x, y, duration=0.2)
        if button == "double":
            pyautogui.doubleClick()
        elif button == "right":
            pyautogui.rightClick()
        else:
            pyautogui.click()
        return f"Clic {button} à ({x}, {y})"
    except Exception as e:
        return f"Erreur mouse_click : {e}"

def tool_take_screenshot():
    try:
        import pyautogui
        screenshot = pyautogui.screenshot()
        path = os.path.join(os.environ.get('TEMP', 'C:\\Temp'), 'jarvis_screenshot.png')
        screenshot.save(path)
        w, h = screenshot.size
        result = subprocess.run(
            ["powershell", "-command",
             "Get-Process | Where-Object {$_.MainWindowTitle} | Select-Object Name,MainWindowTitle | Format-Table -AutoSize | Out-String"],
            capture_output=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW
        )
        try:
            windows = result.stdout.decode('utf-8').strip()
        except:
            windows = result.stdout.decode('cp1252', errors='replace').strip()
        browser_url = tool_get_browser_url()
        url_line = f"\nURL navigateur actif : {browser_url}" if browser_url and "introuvable" not in browser_url and "Aucun" not in browser_url else ""
        return f"Screenshot : {path}\nRésolution : {w}x{h}{url_line}\nFenêtres ouvertes :\n{windows[:800]}"
    except Exception as e:
        return f"Erreur screenshot : {e}"

def tool_get_browser_url():
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
            capture_output=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW
        )
        return result.stdout.decode('utf-8', errors='replace').strip() or "URL non trouvée"
    except Exception as e:
        return f"Erreur get_browser_url : {e}"

def tool_read_screen():
    try:
        import pyautogui
        path = os.path.join(os.environ.get('TEMP', 'C:\\Temp'), 'jarvis_ocr.png')
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
            capture_output=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW
        )
        text = result.stdout.decode('utf-8', errors='replace').strip()
        if text:
            return f"Texte visible à l'écran :\n{text[:3000]}"
        err = result.stderr.decode('utf-8', errors='replace').strip()
        return f"OCR : aucun texte détecté.{' Erreur : ' + err[:200] if err else ''}"
    except Exception as e:
        return f"Erreur read_screen : {e}"

def tool_search_file(name, location=None):
    if not location:
        location = os.path.expanduser("~")
    # Sanitize to avoid injection
    name_safe = name.replace("'", "").replace('"', "")[:80]
    location_safe = location.replace("'", "").replace('"', "")[:200]
    ps = f"Get-ChildItem -Path '{location_safe}' -Recurse -ErrorAction SilentlyContinue | Where-Object {{ $_.Name -like '*{name_safe}*' }} | Select-Object -First 15 -ExpandProperty FullName"
    try:
        result = subprocess.run(
            ["powershell", "-command", ps],
            capture_output=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW
        )
        output = result.stdout.decode('utf-8', errors='replace').strip()
        if output:
            return f"Fichiers trouvés :\n{output}"
        return f"Aucun fichier '{name}' trouvé dans {location}."
    except Exception as e:
        return f"Erreur recherche fichier : {e}"

def tool_open_file(path):
    path = path.strip().strip('"').strip("'")
    try:
        os.startfile(path)
        return f"Ouvert : {os.path.basename(path)}, Monsieur."
    except Exception as e:
        try:
            subprocess.run(["powershell", f"Invoke-Item '{path}'"],
                           capture_output=True, timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
            return "Fichier ouvert, Monsieur."
        except:
            return f"Erreur ouverture fichier : {e}"

def tool_list_folder(path):
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

def tool_read_file_content(path, max_lines=100):
    path = path.strip().strip('"').strip("'")
    try:
        if not os.path.exists(path):
            return f"Fichier '{path}' introuvable."
        size = os.path.getsize(path)
        if size > 500_000:
            return f"Fichier trop volumineux ({size // 1024}KB). Utilisez un éditeur, Monsieur."
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
        note = f"[{len(lines)} lignes au total, {max_lines} affichées]\n" if len(lines) > max_lines else ""
        return note + "".join(lines[:max_lines])
    except Exception as e:
        return f"Erreur lecture fichier : {e}"

def tool_scroll(direction, clicks=3):
    try:
        import pyautogui
        pyautogui.scroll(clicks if direction == "up" else -clicks)
        return f"Défilement {direction}, {clicks} crans"
    except Exception as e:
        return f"Erreur scroll : {e}"

def _show_help_popup(what_i_tried, what_i_need):
    """Bulle flottante Jarvis — tourne dans son propre thread tkinter."""
    import tkinter as tk

    root = tk.Tk()
    root.title("Jarvis")
    root.configure(bg="#0a0a1a")
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.96)
    root.resizable(False, False)
    root.overrideredirect(True)

    W, H = 440, 340
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{W}x{H}+{sw - W - 24}+{60}")

    _drag = {"x": 0, "y": 0}
    def start_drag(e): _drag["x"], _drag["y"] = e.x, e.y
    def do_drag(e): root.geometry(f"+{root.winfo_x()+e.x-_drag['x']}+{root.winfo_y()+e.y-_drag['y']}")

    # ── Header ──────────────────────────────────────────
    header = tk.Frame(root, bg="#12122e", height=42)
    header.pack(fill="x")
    header.pack_propagate(False)
    for w in (header,):
        w.bind("<ButtonPress-1>", start_drag)
        w.bind("<B1-Motion>", do_drag)

    tk.Label(header, text="⚡  JARVIS — Assistance requise",
             bg="#12122e", fg="#7eb8f7",
             font=("Segoe UI", 10, "bold")).pack(side="left", padx=14, pady=10)

    close = tk.Label(header, text="✕", bg="#12122e", fg="#445",
                     font=("Segoe UI", 13), cursor="hand2")
    close.pack(side="right", padx=14)
    close.bind("<Button-1>", lambda e: (_help_request["event"].set(), root.destroy()))

    # ── Corps ───────────────────────────────────────────
    body = tk.Frame(root, bg="#0a0a1a")
    body.pack(fill="both", expand=True, padx=16, pady=10)

    tk.Label(body, text="Ce que j'ai essayé :", bg="#0a0a1a", fg="#556",
             font=("Segoe UI", 8, "bold"), anchor="w").pack(fill="x")
    tk.Label(body, text=what_i_tried[:140] + ("…" if len(what_i_tried) > 140 else ""),
             bg="#0a0a1a", fg="#445566",
             font=("Segoe UI", 8), anchor="w", wraplength=400, justify="left").pack(fill="x", pady=(0, 8))

    tk.Label(body, text="Ce dont j'ai besoin :", bg="#0a0a1a", fg="#7eb8f7",
             font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x")
    tk.Label(body, text=what_i_need,
             bg="#0a0a1a", fg="#aac4ee",
             font=("Segoe UI", 9), anchor="w", wraplength=400, justify="left").pack(fill="x", pady=(0, 10))

    tk.Frame(root, bg="#1e1e3e", height=1).pack(fill="x", padx=16)

    tk.Label(body, text="Votre explication :", bg="#0a0a1a", fg="#c8d0ff",
             font=("Segoe UI", 10), anchor="w").pack(fill="x", pady=(8, 4))

    text_input = tk.Text(root, height=5, bg="#10102a", fg="#e8eeff",
                         font=("Segoe UI", 10), insertbackground="#7eb8f7",
                         relief="flat", padx=10, pady=8, wrap="word", bd=0)
    text_input.pack(fill="x", padx=16)
    text_input.focus_set()

    def on_submit(e=None):
        result = text_input.get("1.0", "end-1c").strip()
        if result:
            _help_request["result"] = result
            _help_request["event"].set()
            root.destroy()

    text_input.bind("<Control-Return>", on_submit)

    # ── Footer ──────────────────────────────────────────
    footer = tk.Frame(root, bg="#0a0a1a")
    footer.pack(fill="x", padx=16, pady=10)

    tk.Label(footer, text="Ctrl+Entrée pour envoyer", bg="#0a0a1a", fg="#333355",
             font=("Segoe UI", 8)).pack(side="left")

    tk.Button(footer, text="Envoyer →", command=on_submit,
              bg="#2a2a7e", fg="#c8d8ff",
              font=("Segoe UI", 10, "bold"), relief="flat",
              padx=14, pady=5, cursor="hand2", bd=0,
              activebackground="#3a3a9e", activeforeground="white").pack(side="right")

    root.mainloop()


def tool_request_human_help(what_i_tried, what_i_need):
    """Ouvre la bulle, attend la réponse de Monsieur, retourne l'explication."""
    _help_request["result"] = None
    _help_request["event"].clear()

    threading.Thread(target=_show_help_popup, args=(what_i_tried, what_i_need), daemon=True).start()
    speak_with_interrupt("Je n'y arrive pas seul, Monsieur. Une fenêtre d'aide vient de s'ouvrir.")

    _help_request["event"].wait(timeout=300)

    if _help_request["result"]:
        print(f"[Aide utilisateur] {_help_request['result'][:120]}")
        return f"EXPLICATION DE MONSIEUR : {_help_request['result']}"
    return "Aucune explication reçue."


def tool_save_learned_command(triggers, powershell_cmd, response):
    try:
        commands = load_commands()
        existing = {normalize_text(t) for cmd in commands for t in cmd.get("triggers", [])}
        new_triggers = [t for t in triggers if normalize_text(t) not in existing]
        if not new_triggers:
            return "Déjà mémorisé."
        new_cmd = {
            "id": f"learned_{int(time.time())}",
            "triggers": triggers,
            "action": {"type": "powershell", "cmd": powershell_cmd},
            "response": response
        }
        commands.append(new_cmd)
        save_commands(commands)
        print(f"[Apprentissage auto] {triggers[0]}")
        return "Mémorisé. La prochaine fois ce sera instantané."
    except Exception as e:
        return f"Erreur sauvegarde : {e}"

def execute_tool(name, args):
    if name == "request_human_help":
        return tool_request_human_help(
            args.get("what_i_tried", ""),
            args.get("what_i_need", "")
        )
    elif name == "save_learned_command":
        return tool_save_learned_command(
            args.get("triggers", []),
            args.get("powershell_cmd", ""),
            args.get("response", "Fait, Monsieur.")
        )
    elif name == "run_powershell":
        return tool_run_powershell(args.get("command", ""))
    elif name == "type_text":
        return tool_type_text(args.get("text", ""))
    elif name == "press_keys":
        return tool_press_keys(args.get("keys", ""))
    elif name == "open_url":
        return tool_open_url(args.get("url", ""))
    elif name == "mouse_click":
        return tool_mouse_click(args.get("x", 0), args.get("y", 0), args.get("button", "left"))
    elif name == "take_screenshot":
        return tool_take_screenshot()
    elif name == "scroll_page":
        return tool_scroll(args.get("direction", "down"), args.get("clicks", 3))
    elif name == "get_browser_url":
        return tool_get_browser_url()
    elif name == "read_screen":
        return tool_read_screen()
    elif name == "search_file":
        return tool_search_file(args.get("name", ""), args.get("location"))
    elif name == "open_file":
        return tool_open_file(args.get("path", ""))
    elif name == "list_folder":
        return tool_list_folder(args.get("path", ""))
    elif name == "read_file_content":
        return tool_read_file_content(args.get("path", ""), args.get("max_lines", 100))
    return f"Outil inconnu : {name}"

def _recovery_hint(tool_name, args, result):
    """Injecte un conseil de récupération quand un outil échoue."""
    r = result.lower()
    is_error = any(k in r for k in ["cannot find", "error", "introuvable", "aucun fichier",
                                     "not found", "exception", "erreur", "n'a pas pu"])
    if not is_error:
        return None

    if tool_name == "run_powershell":
        cmd = args.get("command", "").lower()

        # Start-Process échoue → chercher via Get-StartApps
        if "start-process" in cmd:
            m = re.search(r"start-process\s+['\"]?([a-z0-9_\-\.]+)['\"]?", cmd)
            name = m.group(1).rstrip(".exe") if m else "app"
            return (f"Start-Process a échoué. Étape suivante OBLIGATOIRE : "
                    f"Get-StartApps | Where-Object {{$_.Name -like '*{name}*'}}")

        # Get-StartApps vide → chercher l'exe dans LocalAppData
        if "get-startapps" in cmd:
            m = re.search(r"like\s+'?\*([a-z0-9_\-]+)\*", cmd)
            name = m.group(1) if m else "app"
            return (f"Get-StartApps n'a rien trouvé. Étape suivante OBLIGATOIRE : "
                    f"Get-ChildItem \"$env:LOCALAPPDATA\\Programs\",\"$env:LOCALAPPDATA\" "
                    f"-Recurse -Filter '*{name}*.exe' -ErrorAction SilentlyContinue "
                    f"| Select-Object -First 5 FullName")

        # Recherche filesystem échoue → demander de l'aide
        if "get-childitem" in cmd:
            return ("Toutes les recherches ont échoué. "
                    "Appelle maintenant request_human_help pour demander à Monsieur "
                    "où se trouve l'application.")

    return None


# Client Anthropic (initialisé une fois)
_anthropic_client = None
def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None and ANTHROPIC_API_KEY:
        _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _anthropic_client

def _to_claude_tools(ollama_tools):
    """Convertit les outils format Ollama → format Claude API."""
    result = []
    for t in ollama_tools:
        f = t["function"]
        result.append({
            "name": f["name"],
            "description": f["description"],
            "input_schema": f.get("parameters", {"type": "object", "properties": {}})
        })
    return result

def _to_claude_tools_cached(ollama_tools):
    """Même chose mais marque le dernier outil pour cacher toute la liste."""
    tools = _to_claude_tools(ollama_tools)
    if tools:
        tools[-1]["cache_control"] = {"type": "ephemeral"}
    return tools

def ask_claude_with_tools(question):
    """Appel Claude Haiku avec tool use — raisonnement fiable et rapide."""
    global conversation_history

    client = _get_anthropic_client()
    if not client:
        print("[Claude] Clé API manquante — vérifiez votre ANTHROPIC_API_KEY dans .env")
        return "Je ne peux pas répondre sans clé API, Monsieur. Vérifiez le fichier .env."

    claude_tools = _to_claude_tools_cached(PC_TOOLS)
    static_prompt, dynamic_prompt = get_system_prompt()
    # Bloc statique (personnalité + contexte + instructions) → mis en cache
    static_text = static_prompt + "\n\n" + AGENT_INSTRUCTIONS
    system = [{"type": "text", "text": static_text,
                "cache_control": {"type": "ephemeral"}}]
    # Bloc dynamique (mémoire + mode actif) → non caché, peut changer
    if dynamic_prompt:
        system.append({"type": "text", "text": dynamic_prompt})

    # Limiter l'historique à 30 échanges max pour éviter une croissance infinie
    if len(conversation_history) > 30:
        conversation_history[:] = conversation_history[-30:]

    # Historique : garder seulement les messages texte simples pour Claude
    history = []
    for msg in conversation_history[-10:]:
        if isinstance(msg.get("content"), str):
            history.append({"role": msg["role"], "content": msg["content"]})

    messages = history + [{"role": "user", "content": question}]

    tool_call_count = 0
    help_requested = False

    for _ in range(12):
        if stop_agent.is_set():
            return None

        if tool_call_count >= 5 and not help_requested:
            help_requested = True
            messages.append({"role": "user", "content":
                "Tu as effectué plus de 5 appels sans résoudre la tâche. "
                "Appelle request_human_help maintenant."})

        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=1024,
                system=system,
                tools=claude_tools,
                messages=messages
            )
            track_claude_usage(getattr(response, "usage", None))
        except Exception as e:
            print(f"[Claude] Erreur API : {e}")
            return "Je rencontre une difficulté technique, Monsieur."

        if response.stop_reason == "end_turn":
            final = "".join(
                b.text for b in response.content if hasattr(b, "text")
            ).strip() or "Je n'ai pas réussi à accomplir cette tâche, Monsieur."
            conversation_history.append({"role": "user", "content": question})
            conversation_history.append({"role": "assistant", "content": final})
            return final

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in response.content:
                if block.type != "tool_use":
                    continue
                print(f"[Outil] {block.name}({block.input})")
                result = execute_tool(block.name, block.input)
                print(f"[Résultat] {result[:200]}")
                tool_call_count += 1

                hint = _recovery_hint(block.name, block.input, result)
                content = result + (f"\n\nCONSEIL SYSTÈME : {hint}" if hint else "")

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": content
                })

            messages.append({"role": "user", "content": tool_results})

    final = "Je n'ai pas réussi à accomplir cette tâche, Monsieur. Pourriez-vous préciser ?"
    conversation_history.append({"role": "user", "content": question})
    conversation_history.append({"role": "assistant", "content": final})
    return final

AGENT_INSTRUCTIONS = """════════════════════════════════════════════════════════════
MODE AGENT AUTONOME — Philosophie et méthode
════════════════════════════════════════════════════════════

Tu es un agent qui agit, vérifie et apprend. Tu ne devines pas. Tu ne flattes pas.
Tu ne prétends pas avoir réussi quand tu ignores le résultat. Tu fais, tu confirmes,
ou tu dis honnêtement "je ne sais pas" / "je n'y arrive pas".

───── 1. COMPRENDRE AVANT D'AGIR ─────
L'entrée vient de la reconnaissance vocale (Whisper). Elle contient FRÉQUEMMENT
des erreurs : pluriels fantômes ("Notions Calendars" = "Notion Calendar"),
homophones ("brave"/"braves"), mots coupés, ponctuation absurde, noms propres déformés.

→ Avant d'agir, demande-toi : quelle est la VRAIE intention, compte tenu des erreurs
  possibles de transcription ?
→ Si plusieurs interprétations sont plausibles, choisis la plus probable MAIS garde
  les autres en réserve pour réessayer.
→ Si la demande est vraiment incompréhensible, dis-le franchement :
  "Pourriez-vous reformuler, Monsieur ?" ou "Je n'ai pas saisi, Monsieur."

───── 2. RAISONNER AVANT LE PREMIER OUTIL ─────
Avant d'appeler un outil, réponds mentalement à :
  a) Quelle est l'action concrète attendue ?
  b) Qu'est-ce qui pourrait rater ?
  c) Quelle est la méthode la plus fiable, pas la première qui me vient ?

───── 3. CHERCHER PLUTÔT QUE SUPPOSER ─────
Tu ne connais pas par cœur les chemins d'installation. NE DEVINE JAMAIS un chemin
ou un nom d'exe. Cherche toujours :

Pour une app :
  Get-StartApps | Where-Object {$_.Name -like '*Mot*'}

Si aucun résultat, essaie en filesystem (avec plusieurs orthographes) :
  Get-ChildItem 'C:\\Program Files','C:\\Program Files (x86)',"$env:LOCALAPPDATA\\Programs" -Recurse -Filter '*mot*.exe' -ErrorAction SilentlyContinue | Select -First 5 FullName

Essaie des variantes si le premier nom ne donne rien : "Notion Calendar",
"NotionCalendar", "notion-calendar".

───── 4. EXÉCUTER PROPREMENT ─────
Avec le chemin ou l'AppID exact trouvé — jamais approximatif.
  Start-Process 'C:\\chemin\\exact\\app.exe'
  Ou pour une app UWP : Start-Process "shell:AppsFolder\\$AppID"

───── 5. VÉRIFIER, TOUJOURS ─────
Une commande qui retourne exit 0 ne prouve RIEN. Vérifie l'effet réel :
  • App ouverte ? → Get-Process | Where-Object {$_.MainWindowTitle -ne ''} | Select Name,MainWindowTitle
  • Fichier créé ? → Test-Path 'chemin'
  • Fenêtre visible ? → take_screenshot

Si la vérification échoue ou ne confirme rien, ce n'est PAS un succès.
N'annonce JAMAIS "c'est ouvert, Monsieur" sans avoir vu la preuve.

───── 6. RÉESSAYER INTELLIGEMMENT ─────
Si une approche échoue :
  1ère tentative échoue → change de méthode, pas de paramètres aléatoires
  2ème tentative échoue → change complètement d'angle
  3ème tentative échoue → dis honnêtement que tu n'y arrives pas

Dans la MÊME conversation, ne refais pas une approche qui vient d'échouer.
Garde en tête ce qui n'a pas fonctionné.

───── 7. HONNÊTETÉ RADICALE ─────
Tu as le droit — et le devoir — de dire :
  • "Je n'ai pas compris, Monsieur."
  • "Je n'y parviens pas, Monsieur. J'ai tenté X et Y sans succès."
  • "L'application ne semble pas installée sur ce système, Monsieur."
  • "Je ne dispose pas de cette information, Monsieur."

Il est STRICTEMENT INTERDIT de :
  ✗ Inventer un résultat
  ✗ Prétendre qu'une action a réussi sans vérification
  ✗ Deviner un chemin de fichier ou un nom d'exe
  ✗ Répondre "c'est fait, Monsieur" par défaut quand tu ne sais pas

───── 8. DEMANDER DE L'AIDE SI VRAIMENT BLOQUÉ ─────
Si et SEULEMENT si tu as essayé au moins 3 approches différentes sans succès,
appelle request_human_help en précisant :
  • Ce que tu as tenté (résumé court)
  • Ce dont tu as exactement besoin (chemin, AppID, nom exact, etc.)
Monsieur répondra par écrit dans la bulle. Utilise immédiatement cette info pour terminer.
N'appelle JAMAIS cette fonction dès le premier obstacle — essaie vraiment d'abord.

───── 9. APPRENDRE DE CHAQUE SUCCÈS ─────
Après CHAQUE réussite répétable (app ouverte, action système, recherche récurrente),
appelle OBLIGATOIREMENT save_learned_command avec :
  • 3 à 5 triggers naturels que Monsieur pourrait dire (variantes incluses)
  • La commande PowerShell EXACTE qui a fonctionné (pas une approximation)
  • Une réponse courte style Jarvis ("Monsieur" obligatoire)

Cette sauvegarde transforme 8s de réflexion en 1ms de réponse la fois suivante.
C'est ton mécanisme d'amélioration continue. Ne l'oublie jamais.

N'appelle PAS save_learned_command si :
  ✗ La tâche a échoué
  ✗ La réponse n'est pas reproductible (dépend du moment, du contexte)
  ✗ Tu n'as pas vérifié le succès

═══════════════ EXEMPLES DE RAISONNEMENT ═══════════════

Exemple A — "Ouvre mon agenda"
  1. "Agenda" peut signifier plusieurs choses : Notion Calendar (installée), Google Calendar (web),
     Windows Calendar. Par défaut je privilégie l'app locale.
  2. Je cherche : Get-StartApps | Where-Object {$_.Name -like '*Calendar*' -or $_.Name -like '*Agenda*'}
  3. Je trouve "Notion Calendar" avec un AppID.
  4. Je lance : Start-Process "shell:AppsFolder\\<AppID>"
  5. Je vérifie : Get-Process | Where-Object {$_.MainWindowTitle -like '*Notion Calendar*'}
  6. Confirmation visuelle → je sauvegarde avec save_learned_command et je réponds.

Exemple B — Échec assumé
  Demande incompréhensible ou app introuvable après 3 tentatives :
  → "Je n'ai pas trouvé cette application sur votre système, Monsieur."
  → Pas de save_learned_command.

Ce framework n'est pas optionnel. C'est ta méthode de travail pour chaque tâche."""

def is_pc_command(question):
    keywords = [
        "ouvre", "ferme", "lance", "démarre", "arrête", "volume", "son",
        "screenshot", "capture", "dossier", "fichier", "application",
        "programme", "navigateur", "musique", "vidéo", "cherche", "trouve",
        "crée", "supprime", "déplace", "copie", "écris", "note",
        "clique", "tape", "écran", "fenêtre", "bureau", "barre des tâches",
        "wifi", "bluetooth", "batterie", "cpu", "ram", "mémoire", "disque",
        "processus", "tâche", "raccourci", "touche", "clavier", "souris",
        "télécharge", "installe", "paramètre", "luminosité", "résolution",
        "imprime", "connecte", "déconnecte", "verrouille", "redémarre", "éteins",
        "adresse ip", "réseau", "ping", "stockage", "espace", "explorateur",
        "mon pc", "l'ordinateur", "windows", "spotify", "chrome", "firefox",
        "discord", "steam", "teams", "word", "excel", "powerpoint", "notepad",
        "glisse", "fais défiler", "scroll", "maximise", "minimise", "plein écran",
        "github", "profil", "onglet", "site", "page", "url", "lien", "navigue", "va sur"
    ]
    return any(kw in question.lower() for kw in keywords)

def load_commands():
    global _commands_cache
    if _commands_cache is None:
        if os.path.exists(COMMANDS_FILE):
            with open(COMMANDS_FILE, 'r', encoding='utf-8') as f:
                _commands_cache = json.load(f).get("commands", [])
        else:
            _commands_cache = []
    return _commands_cache

def save_commands(commands):
    global _commands_cache
    _commands_cache = commands
    with open(COMMANDS_FILE, 'w', encoding='utf-8') as f:
        json.dump({"version": 1, "commands": commands}, f, ensure_ascii=False, indent=2)

def match_command(question):
    q = normalize_text(question)
    words = q.split()

    ACTION_VERBS = {
        "ouvre", "lance", "ferme", "va", "coupe", "mets", "montre", "affiche",
        "vide", "verrouille", "redemarre", "eteins", "arrete", "pause",
        "prends", "minimise", "reduis", "monte", "baisse", "next", "previous"
    }
    # Phrase courte (≤4 mots) ou contient un verbe d'action dans les 4 premiers mots
    is_command_like = len(words) <= 4 or any(w in ACTION_VERBS for w in words[:4])

    best = None
    best_len = 0
    for cmd in load_commands():
        for trigger in cmd.get("triggers", []):
            t = normalize_text(trigger)
            if t not in q or len(t) <= best_len:
                continue
            # Trigger multi-mots : assez spécifique, on accepte toujours
            # Trigger mono-mot : seulement si la phrase ressemble à une commande
            if len(t.split()) >= 2 or is_command_like:
                best = cmd
                best_len = len(t)
    return best

def _execute_action(action):
    atype = action.get("type", "")
    if atype == "open_url":
        tool_open_url(action["url"])
    elif atype == "powershell":
        tool_run_powershell(action["cmd"])
    elif atype == "open_app":
        tool_run_powershell(f"Start-Process '{action['app']}'")
    elif atype == "sequence":
        for step in action.get("steps", []):
            _execute_action(step)
            time.sleep(0.3)

def execute_command_entry(cmd):
    _execute_action(cmd.get("action", {}))
    return cmd.get("response", "Fait, Monsieur.")

def is_learn_command(question):
    """Détecte une demande d'apprentissage de COMMANDE (contient un verbe d'action)."""
    q = normalize_text(question)
    trigger_kw = ["mémorise", "retiens", "apprends", "souviens-toi", "enregistre",
                  "quand je dis", "quand je te dis", "quand je te demande",
                  "si je dis", "si je te dis"]
    action_kw = ["ouvre", "lance", "ferme", "demarre", "execute", "tape", "clique",
                 "va sur", "navigue", "fait", "fais", "ecris", "joue", "telecharge"]
    has_trigger = any(kw in q for kw in trigger_kw)
    has_action = any(kw in q for kw in action_kw)
    return has_trigger and has_action

def is_memory_fact(question):
    """Détecte une demande de mémorisation de FAIT PERSONNEL (sans verbe d'action concret)."""
    q = normalize_text(question)
    trigger_kw = ["mémorise que", "retiens que", "sache que", "note que", "souviens-toi que",
                  "n'oublie pas que", "je te dis que", "sache bien que"]
    return any(kw in q for kw in trigger_kw) and not is_learn_command(question)

def save_explicit_fact(question):
    """Extrait et sauvegarde directement un fait depuis 'mémorise que X'."""
    q = normalize_text(question)
    # Extraire ce qui vient après le trigger
    for trigger in ["memorise que", "retiens que", "sache que", "note que",
                    "souviens-toi que", "n'oublie pas que", "je te dis que", "sache bien que"]:
        if trigger in q:
            idx = q.index(trigger) + len(trigger)
            fact = question[idx:].strip().rstrip(".")
            if fact:
                memory = load_memory()
                # Limiter à 25 mots
                words = fact.split()
                fact = " ".join(words[:25])
                if fact not in memory["facts"]:
                    memory["facts"].append(fact)
                    memory["facts"] = list(dict.fromkeys(memory["facts"]))[-80:]
                    memory["last_updated"] = str(time.time())
                    save_memory(memory)
                    print(f"[Mémoire explicite] {fact}")
                return fact
    return None

def handle_direct_local_command(question):
    """Réponses ultra-rapides sans LLM : uniquement heure et IP locale."""
    q = normalize_text(question)

    if "heure" in q and len(q.split()) <= 5:
        now = time.localtime()
        return f"Il est {now.tm_hour} heures {now.tm_min:02d}, Monsieur."

    if "adresse ip" in q or ("ip" in q and "adresse" in q):
        output = tool_run_powershell(
            "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.IPAddress -notlike '127.*' -and $_.PrefixOrigin -ne 'WellKnown'} | "
            "Select-Object -ExpandProperty IPAddress -First 1)"
        ).strip()
        if output and not output.lower().startswith("erreur") and not output.lower().startswith("timeout"):
            return f"Votre adresse IP locale est {output}, Monsieur."
        return "Je n'ai pas pu récupérer votre adresse IP locale, Monsieur."

    return None

# Dossiers raccourcis connus
_KNOWN_FOLDERS = {
    "documents": os.path.expanduser("~/Documents"),
    "telechargements": os.path.expanduser("~/Downloads"),
    "downloads": os.path.expanduser("~/Downloads"),
    "bureau": os.path.expanduser("~/Desktop"),
    "desktop": os.path.expanduser("~/Desktop"),
    "images": os.path.expanduser("~/Pictures"),
    "photos": os.path.expanduser("~/Pictures"),
    "musique": os.path.expanduser("~/Music"),
    "videos": os.path.expanduser("~/Videos"),
}

def _smart_open(name):
    """Tente d'ouvrir intelligemment : dossier connu → chemin direct → app → site web → recherche fichier."""
    n = normalize_text(name).strip()

    # 1. Dossier connu
    if n in _KNOWN_FOLDERS:
        subprocess.Popen(["explorer", _KNOWN_FOLDERS[n]])
        return f"Dossier {name} ouvert, Monsieur."

    # 2. Chemin direct
    if os.path.exists(name):
        try:
            os.startfile(name)
            return f"Ouvert, Monsieur."
        except Exception:
            pass

    # 3. Tentative app (exe)
    try:
        result = subprocess.run(
            ["powershell", "-command", f"Start-Process '{name}' -ErrorAction Stop"],
            capture_output=True, timeout=3, creationflags=subprocess.CREATE_NO_WINDOW
        )
        if result.returncode == 0:
            return f"{name} est ouvert, Monsieur."
    except Exception:
        pass

    # 4. Ressemble à un domaine → site web
    if "." in name and " " not in name:
        url = name if name.startswith("http") else f"https://{name}"
        tool_open_url(url)
        return f"{name} est ouvert, Monsieur."

    # 5. Recherche fichier/dossier sur le disque utilisateur
    try:
        name_safe = name.replace("'", "").replace('"', "")[:60]
        ps = (f"Get-ChildItem -Path '$env:USERPROFILE' -Recurse -ErrorAction SilentlyContinue "
              f"| Where-Object {{ $_.Name -like '*{name_safe}*' }} "
              f"| Select-Object -First 1 -ExpandProperty FullName")
        result = subprocess.run(
            ["powershell", "-command", ps],
            capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW
        )
        found = result.stdout.decode('utf-8', errors='replace').strip()
        if found and os.path.exists(found):
            os.startfile(found)
            return f"J'ai trouvé et ouvert « {os.path.basename(found)} », Monsieur."
    except Exception:
        pass

    # 6. Dernier recours : site web avec .com
    tool_open_url(f"https://www.{name.replace(' ', '')}.com")
    return f"Je n'ai pas trouvé d'application ni de fichier « {name} », Monsieur — j'ai tenté le site."

def is_pause_command(question):
    pause_keywords = ["mets-toi en pause", "pause", "tais-toi", "silence", 
                     "arrête de m'écouter", "désactive-toi"]
    resume_keywords = ["reprends", "réactive-toi", "réveille-toi", 
                      "tu peux reprendre", "c'est bon reprends"]
    q = question.lower()
    if any(kw in q for kw in pause_keywords):
        return "pause"
    if any(kw in q for kw in resume_keywords):
        return "resume"
    return None

# --- Voix ---

def speak(text):
    global is_speaking
    stop_speaking.clear()
    is_speaking = True
    
    try:
        response = requests.post(
            SPEACHES_TTS_URL,
            json={
                "model": TTS_MODEL,
                "input": text,
                "voice": TTS_VOICE
            },
            timeout=REQUEST_TIMEOUT
        )
        if response.status_code == 200 and not stop_speaking.is_set():
            buffer = io.BytesIO(response.content)
            audio = AudioSegment.from_mp3(buffer)
            
            # Fondu au début (200ms)
            audio = audio.fade_in(200)
            
            samples = np.array(audio.get_array_of_samples(), dtype=np.int16)
            sd.play(samples, samplerate=audio.frame_rate)
            
            while sd.get_stream().active:
                if stop_speaking.is_set():
                    # Fondu à la fin avant de couper (150ms)
                    sd.stop()
                    remaining = audio[-300:]
                    remaining = remaining.fade_out(150)
                    fade_samples = np.array(remaining.get_array_of_samples(), dtype=np.int16)
                    sd.play(fade_samples, samplerate=audio.frame_rate)
                    sd.wait()
                    break
                time.sleep(0.05)
        elif response.status_code != 200:
            print(f"Erreur TTS HTTP {response.status_code}: {response.text[:200]}")
    except Exception as e:
        print(f"Erreur TTS: {e}")
    
    is_speaking = False

def listen_for_interrupt():
    CHUNK = 512
    sample_rate = 16000
    consecutive_speech = 0

    # Vider l'audio accumulé pendant que le stream était inactif
    if _interrupt_stream:
        available = _interrupt_stream.get_read_available()
        if available > 0:
            _interrupt_stream.read(available, exception_on_overflow=False)

    time.sleep(INTERRUPT_START_DELAY)

    while not stop_speaking.is_set():
        if _interrupt_stream is None:
            break
        chunk = np.frombuffer(_interrupt_stream.read(CHUNK, exception_on_overflow=False), dtype=np.int16)
        audio_float = torch.FloatTensor(chunk.astype(np.float32) / 32768.0)
        speech_prob = silero_model(audio_float, sample_rate).item()
        rms = float(np.sqrt(np.mean(np.square(audio_float.numpy()))))

        if speech_prob > INTERRUPT_VAD_THRESHOLD and rms > INTERRUPT_MIN_RMS:
            consecutive_speech += 1
            if consecutive_speech >= INTERRUPT_MIN_CONSECUTIVE:
                print("\n(Interrompu)")
                stop_speaking.set()
                stop_agent.set()
                sd.stop()
                while not phrase_queue.empty():
                    try:
                        phrase_queue.get_nowait()
                    except:
                        pass
                phrase_queue.put(None)
                break
        else:
            consecutive_speech = 0

def speak_with_interrupt(text):
    print(f"Jarvis : {text}")
    overlay.set_response(text)
    overlay.set_state("speaking")
    if overlay.is_muted():
        # Mode texte : pas de TTS, juste l'affichage
        overlay.set_state("idle")
        return
    interrupt_thread = threading.Thread(target=listen_for_interrupt)
    interrupt_thread.start()
    speak(text)
    stop_speaking.set()  # Signal au thread d'interruption pour qu'il s'arrête proprement
    interrupt_thread.join()
    overlay.set_state("idle")

def listen_for_wake_word_tflite(stream):
    """Detecte le wake word avec le modele local TFLite sur fenetre glissante."""
    chunk_size = 512
    score_counter = 0
    consecutive_hits = 0
    last_trigger_time = 0.0
    ring_buffer = deque(maxlen=WAKE_WORD_WINDOW_SAMPLES)
    print("\nEn attente de 'Jarvis'...")
    overlay.set_state("idle")

    while True:
        # Input texte ou token de contrôle depuis l'overlay
        typed = overlay.get_text_input_nowait()
        if typed == TOKEN_PAUSE:
            return TOKEN_PAUSE
        if typed == TOKEN_RESUME:
            return TOKEN_RESUME
        if typed:
            print(f"[overlay] Input texte: {typed}")
            flush_audio_buffer(stream)
            return typed

        # Mode mute : écoute micro suspendue, seule la saisie texte est active
        if overlay.is_muted():
            time.sleep(0.05)
            continue

        chunk = np.frombuffer(stream.read(chunk_size, exception_on_overflow=False), dtype=np.int16)
        ring_buffer.extend(chunk.tolist())
        score_counter += 1

        if len(ring_buffer) < WAKE_WORD_WINDOW_SAMPLES:
            continue
        if score_counter < WAKE_WORD_STEP_CHUNKS:
            continue

        score_counter = 0
        audio_window = np.array(ring_buffer, dtype=np.float32) / 32768.0

        # Vérification volume d'abord — si trop silencieux, pas la peine de scorer
        rms = float(np.sqrt(np.mean(np.square(audio_window))))
        if rms < 0.015:  # seuil de silence
            consecutive_hits = 0
            continue

        score = score_wake_word(audio_window)

        if score >= WAKE_WORD_THRESHOLD:
            consecutive_hits += 1
            print(f"[Wake word score: {score:.2f}] rms={rms:.4f}")
        else:
            consecutive_hits = 0

        now = time.time()
        if consecutive_hits >= WAKE_WORD_CONSECUTIVE_HITS and now - last_trigger_time > WAKE_WORD_COOLDOWN_SECONDS:
            # Vérifier qu'il y a vraiment de la parole avec le VAD
            vad_chunk = np.frombuffer(stream.read(512, exception_on_overflow=False), dtype=np.int16)
            vad_float = torch.FloatTensor(vad_chunk.astype(np.float32) / 32768.0)
            vad_prob = silero_model(vad_float, 16000).item()
            rms = float(np.sqrt(np.mean(np.square(vad_float.numpy()))))
            
            if vad_prob < 0.3 and rms < 0.01:
                # Faux positif — bruit ambiant, pas de vraie voix
                consecutive_hits = 0
                continue
            
            last_trigger_time = now
            consecutive_hits = 0
            print(f"'{WAKE_WORD}' detecte ! (score: {score:.2f})")
            flush_audio_buffer(stream)
            return ""

# --- Main ---

def main_loop():
    global is_paused, is_waiting, _interrupt_pa, _interrupt_stream
    setup_wake_word_model()

    _pa = pyaudio.PyAudio()
    audio_stream = _pa.open(format=pyaudio.paInt16, channels=1, rate=16000,
                            input=True, frames_per_buffer=256)

    _interrupt_pa = pyaudio.PyAudio()
    _interrupt_stream = _interrupt_pa.open(format=pyaudio.paInt16, channels=1, rate=16000,
                                           input=True, frames_per_buffer=512)

    try:
        _main_loop_inner(audio_stream)
    finally:
        audio_stream.stop_stream()
        audio_stream.close()
        _pa.terminate()
        _interrupt_stream.stop_stream()
        _interrupt_stream.close()
        _interrupt_pa.terminate()

def _main_loop_inner(audio_stream):
    global is_paused, is_waiting

    speak_with_interrupt("À votre service, Monsieur.")
    is_waiting = True
    update_tray_icon()
    question_count = 0

    while True:
        if is_paused:
            is_waiting = True
            update_tray_icon()
            inline_command = listen_for_wake_word_tflite(audio_stream)
            # Token RESUME depuis le bouton overlay
            if inline_command == TOKEN_RESUME:
                is_paused = False
                overlay.set_paused(False)
                update_tray_icon()
                speak_with_interrupt("De retour, Monsieur.")
                continue
            if inline_command == TOKEN_PAUSE:
                continue  # déjà en pause
            question = inline_command or transcribe_stream(audio_stream)
            if question and question not in (TOKEN_PAUSE, TOKEN_RESUME):
                cmd = is_pause_command(question)
                if cmd == "resume":
                    is_paused = False
                    overlay.set_paused(False)
                    update_tray_icon()
                    speak_with_interrupt("De retour, Monsieur.")
            continue

        is_waiting = True
        update_tray_icon()
        inline_command = listen_for_wake_word_tflite(audio_stream)

        # Token PAUSE depuis le bouton overlay pendant la veille
        if inline_command == TOKEN_PAUSE:
            is_paused = True
            overlay.set_paused(True)
            update_tray_icon()
            speak_with_interrupt("Mise en veille, Monsieur.")
            continue

        # Réinitialiser l'état après le wake word
        stop_speaking.clear()
        while not phrase_queue.empty():
            try:
                phrase_queue.get_nowait()
            except:
                pass

        is_waiting = False
        update_tray_icon()
        overlay.set_state("listening")
        timeout_start = time.time()

        while True:
            if is_paused:
                break

            # Poll overlay avant d'aller au micro (texte ou pause)
            typed = overlay.get_text_input_nowait()
            if typed == TOKEN_PAUSE:
                is_paused = True
                overlay.set_paused(True)
                update_tray_icon()
                stop_speaking.set()
                speak_with_interrupt("Mise en veille, Monsieur.")
                break
            question = (typed or inline_command) or transcribe_stream(audio_stream)
            inline_command = ""

            if question and len(question) > 2:
                print(f"Quentin : {question}")
                overlay.set_transcript(question)
                overlay.set_state("processing")
                cmd = is_pause_command(question)
                if cmd == "pause":
                    is_paused = True
                    update_tray_icon()
                    speak_with_interrupt("Mise en veille, Monsieur.")
                    break

                debut = time.time()

                # Changement de mode ("mode travail", "passe en mode détente"...)
                mode_match = match_mode_trigger(question)
                if mode_match:
                    activated = set_mode(mode_match["id"])
                    if activated:
                        overlay.set_mode(activated["name"].replace("Mode ", ""))
                        response_mode = f"{activated['name']} activé, Monsieur. {activated['description']}"
                    else:
                        response_mode = "Mode non reconnu, Monsieur."
                    overlay.set_source("direct")
                    flush_audio_buffer(audio_stream)
                    speak_with_interrupt(response_mode)
                    flush_audio_buffer(audio_stream)
                    timeout_start = time.time()
                    continue

                # Mémorisation d'un fait personnel ("mémorise que X")
                if is_memory_fact(question):
                    fact = save_explicit_fact(question)
                    if fact:
                        confirm = f"Mémorisé, Monsieur : « {fact[:60]} »."
                    else:
                        confirm = "Je n'ai pas pu identifier le fait à mémoriser, Monsieur."
                    overlay.set_source("direct")
                    flush_audio_buffer(audio_stream)
                    speak_with_interrupt(confirm)
                    flush_audio_buffer(audio_stream)
                    timeout_start = time.time()
                    continue

                # Fast path : commandes système instantanées (volume, verrou, arrêt...)
                matched_cmd = match_command(question)
                if matched_cmd:
                    duree = time.time() - debut
                    print(f"Commande '{matched_cmd['id']}' en {duree:.3f}s")
                    response = execute_command_entry(matched_cmd)
                    overlay.set_source("cache")
                    flush_audio_buffer(audio_stream)
                    speak_with_interrupt(response)
                    flush_audio_buffer(audio_stream)
                    timeout_start = time.time()
                    continue

                # Réponses ultra-rapides sans LLM (heure, IP)
                direct_response = handle_direct_local_command(question)
                if direct_response:
                    duree = time.time() - debut
                    print(f"Réponse locale en {duree:.1f}s")
                    overlay.set_source("direct")
                    flush_audio_buffer(audio_stream)
                    speak_with_interrupt(direct_response)
                    flush_audio_buffer(audio_stream)
                else:
                    # Tout le reste → Claude Haiku (raisonnement fiable)
                    overlay.set_source("ai")
                    print("(Mode Claude)")
                    stop_agent.clear()
                    stop_speaking.clear()

                    agent_result = [None]
                    def _run_agent():
                        agent_result[0] = ask_claude_with_tools(question)

                    agent_thread = threading.Thread(target=_run_agent, daemon=True)
                    interrupt_thread = threading.Thread(target=listen_for_interrupt, daemon=True)
                    agent_thread.start()
                    interrupt_thread.start()
                    agent_thread.join()
                    stop_speaking.set()  # arrête le listener d'interruption
                    interrupt_thread.join()

                    if stop_agent.is_set() or agent_result[0] is None:
                        print("(Agent interrompu)")
                        flush_audio_buffer(audio_stream)
                        timeout_start = time.time()
                        continue

                    duree = time.time() - debut
                    print(f"Réponse en {duree:.1f}s")
                    flush_audio_buffer(audio_stream)
                    speak_with_interrupt(agent_result[0])
                    flush_audio_buffer(audio_stream)

                question_count += 1
                if question_count % 5 == 0:
                    print("Mise à jour de la mémoire en arrière-plan...")
                    threading.Thread(target=update_memory, daemon=True).start()
                timeout_start = time.time()
            else:
                if time.time() - timeout_start > 20:
                    is_waiting = True
                    update_tray_icon()
                    print("(Retour en veille)")
                    break

if __name__ == "__main__":
    print("=== Jarvis démarré ===")
    # Démarrer l'overlay flottant
    overlay.start()
    # Synchroniser le badge mode avec le mode actif
    _active = get_active_mode_data()
    if _active:
        overlay.set_mode(_active["name"].replace("Mode ", ""))
    # Charger le coût mensuel en cours
    _usage_summary = get_usage_summary()
    overlay.set_cost(_usage_summary["last_cost_usd"],
                     _usage_summary["month_cost_usd"],
                     _usage_summary["month_calls"])
    # Callback : changement de mode depuis le menu overlay
    def _overlay_mode_change(mode_id):
        activated = set_mode(mode_id)
        if activated:
            overlay.set_mode(activated["name"].replace("Mode ", ""))
            speak_with_interrupt(f"{activated['name']} activé, Monsieur.")
    overlay.on_mode_change = _overlay_mode_change
    # Lancer l'icône taskbar dans un thread séparé
    tray_thread = threading.Thread(target=setup_tray, daemon=True)
    tray_thread.start()
    # PyQt6 exige que sa boucle tourne sur le thread principal :
    # on déplace main_loop dans un thread dédié.
    jarvis_thread = threading.Thread(target=main_loop, daemon=True)
    jarvis_thread.start()
    overlay.exec()  # boucle Qt — bloque jusqu'à fermeture
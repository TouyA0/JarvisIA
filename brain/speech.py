"""Proxy voix (STT + TTS) vers Speaches, pour la Console web (Phase 9).

Même conteneur Speaches que l'agent desktop (agents/desktop/audio/stt.py,
tts.py) — pas de nouvelle dépendance, juste un deuxième client vers le
même service. Contrairement au desktop, pas de VAD ni de streaming
spéculatif ici : le navigateur envoie un segment audio déjà découpé
(voir brain/server.py, /ws/voice), la latence de Whisper sur un clip
court reste raisonnable sans cette optimisation.
"""
from __future__ import annotations

import requests

from brain import config


def transcribe(audio_bytes: bytes, filename: str = "audio.webm", content_type: str = "audio/webm") -> str:
    """Transcrit un segment audio. Retourne une chaîne vide en cas d'échec
    (jamais d'exception — un segment illisible ne doit pas interrompre la
    fenêtre d'écoute)."""
    if not audio_bytes:
        return ""
    try:
        resp = requests.post(
            config.SPEACHES_STT_URL,
            files={"file": (filename, audio_bytes, content_type)},
            data={"model": config.STT_MODEL, "language": "fr"},
            timeout=config.SPEECH_REQUEST_TIMEOUT,
        )
        if resp.status_code == 200:
            return resp.json().get("text", "").strip()
        print(f"[speech] STT HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[speech] erreur STT : {e}")
    return ""


def synthesize(text: str) -> bytes | None:
    """Synthétise `text` en MP3 (même format que le desktop, lisible
    nativement par <audio> côté navigateur). None en cas d'échec."""
    if not text:
        return None
    try:
        resp = requests.post(
            config.SPEACHES_TTS_URL,
            json={"model": config.TTS_MODEL, "input": text, "voice": config.TTS_VOICE},
            timeout=config.SPEECH_REQUEST_TIMEOUT,
        )
        if resp.status_code == 200:
            return resp.content
        print(f"[speech] TTS HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[speech] erreur TTS : {e}")
    return None

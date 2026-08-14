"""Transcription vocale (Speaches / faster-whisper) avec STT spéculatif.

Dès le premier chunk de silence détecté, Whisper est lancé en arrière-plan.
L'objectif est que le résultat soit prêt avant la fin de la fenêtre de silence
(320 ms) → latence STT perçue nulle.
"""
from __future__ import annotations

import io
import threading
import time
import wave
from collections import deque
from typing import Callable, Optional

import numpy as np
import requests

from agents.desktop import config, state
from agents.desktop.audio import vad


def _do_stt(frames: list) -> str:
    """Envoie des frames int16 au STT et retourne le texte."""
    if not frames:
        return ""
    audio = np.concatenate(frames)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(audio.tobytes())
    buf.seek(0)
    try:
        resp = requests.post(
            config.SPEACHES_STT_URL,
            files={"file": ("audio.wav", buf, "audio/wav")},
            data={"model": config.STT_MODEL, "language": "fr"},
            timeout=config.REQUEST_TIMEOUT,
        )
        if resp.status_code == 200:
            return resp.json().get("text", "").strip()
        print(f"[STT] HTTP {resp.status_code}: {resp.text[:100]}")
    except Exception as e:
        print(f"[STT] erreur : {e}")
    return ""


def transcribe(stream, on_level: Optional[Callable[[float], None]] = None) -> str:
    """Enregistre avec VAD et transcrit avec STT spéculatif."""
    CHUNK = 512
    sample_rate = 16000
    silent_chunks = 0
    speaking_started = False
    speech_frames: list = []
    pre_buffer: deque = deque(maxlen=6)
    max_silent_chunks = int(0.32 * sample_rate / CHUNK)  # 10 chunks × 32ms = 320ms
    max_chunks = int(15 * sample_rate / CHUNK)

    t_start = time.time()

    # STT spéculatif : résultat et version pour éviter les résultats périmés
    _stt = {"text": None, "version": 0, "thread": None}

    def _launch_stt(frames_snapshot, version):
        def _run():
            result = _do_stt(frames_snapshot)
            if _stt["version"] == version:
                _stt["text"] = result
        t = threading.Thread(target=_run, daemon=True)
        t.start()
        _stt["thread"] = t

    for _ in range(max_chunks):
        chunk = stream.read(CHUNK)
        speech_prob = vad.prob_int16(chunk, sample_rate)
        if on_level:
            on_level(vad.rms_int16(chunk))

        if speech_prob > 0.5:
            if not speaking_started:
                speech_frames.extend(pre_buffer)
                pre_buffer.clear()
            speaking_started = True
            silent_chunks = 0
            # L'utilisateur reprend la parole → invalider le STT spéculatif en cours
            if _stt["thread"] is not None:
                _stt["version"] += 1
                _stt["text"] = None
                _stt["thread"] = None
        elif speaking_started:
            silent_chunks += 1
            # 1er chunk de silence → lancer Whisper immédiatement en arrière-plan
            if silent_chunks == 1:
                _launch_stt(list(speech_frames), _stt["version"])
            if silent_chunks >= max_silent_chunks:
                break

        if speaking_started:
            speech_frames.append(chunk)
        else:
            pre_buffer.append(chunk)

    if not speech_frames:
        print("[Transcription] aucune parole détectée.")
        return ""

    # Attendre le résultat spéculatif (quasi-instantané avec un modèle rapide)
    if _stt["thread"] is not None:
        t0 = time.time()
        _stt["thread"].join(timeout=config.REQUEST_TIMEOUT)
        waited = time.time() - t0
        if waited > 0.05:
            print(f"Whisper a pris : +{waited:.2f}s après silence")
        else:
            print("Whisper : résultat prêt avant fin du silence")
        text = _stt["text"] or ""
    else:
        # Fallback si le STT spéculatif n'a pas démarré
        t0 = time.time()
        text = _do_stt(speech_frames)
        print(f"Whisper a pris : {time.time() - t0:.2f}s")

    state.set_metric("stt_ms", (time.time() - t_start) * 1000)

    if text:
        print(f"[Transcription] '{text}'")
    else:
        print("[Transcription] texte vide.")
    return text

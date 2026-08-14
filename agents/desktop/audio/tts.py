"""Synthèse vocale (Speaches / Piper) + interruption vocale (barge-in).

speak() joue le texte et alimente en continu le niveau audio de sortie
(pour la visualisation du HUD). listen_for_interrupt() écoute le micro
pendant que Jarvis parle et coupe la synthèse si Monsieur reprend la parole.
"""
from __future__ import annotations

import io
import time
from typing import Callable, Optional

import numpy as np
import requests
import sounddevice as sd
from pydub import AudioSegment

from agents.desktop import config, state
from agents.desktop.audio import capture, vad
from agents.desktop.textutil import normalize_text

# ── Profil de sortie audio (casque vs haut-parleurs) ─────────────────────────
_output_profile_cache = {"name": None, "profile": "inconnu", "checked_at": 0.0}


def detect_output_profile() -> str:
    """Devine si la sortie audio courante est un casque ou des haut-parleurs.

    Détermine la sensibilité du barge-in : sur haut-parleurs le micro réentend
    Jarvis et il faut relever les seuils. Le périphérique peut changer en cours
    de session (on branche un casque) — on revérifie donc périodiquement.
    """
    # Surcharge explicite : Windows nomme « Haut-parleurs » beaucoup de casques
    # USB/DAC, l'heuristique sur le nom ne peut donc pas être fiable à 100%.
    # Mettre INTERRUPT_PROFILE=casque dans .env pour forcer.
    import os
    forced = os.getenv("INTERRUPT_PROFILE", "").strip().lower()
    if forced in config.INTERRUPT_PROFILES:
        return forced

    now = time.time()
    if now - _output_profile_cache["checked_at"] < config.OUTPUT_DEVICE_RECHECK_SECONDS:
        return _output_profile_cache["profile"]
    _output_profile_cache["checked_at"] = now

    try:
        name = sd.query_devices(kind="output")["name"]
    except Exception:
        return _output_profile_cache["profile"]

    if name == _output_profile_cache["name"]:
        return _output_profile_cache["profile"]

    n = normalize_text(name)
    if any(h in n for h in config.HEADSET_HINTS):
        profile = "casque"
    elif any(h in n for h in config.SPEAKER_HINTS):
        profile = "haut-parleur"
    else:
        profile = "inconnu"

    _output_profile_cache["name"] = name
    _output_profile_cache["profile"] = profile
    print(f"[Audio] Sortie « {name} » → profil interruption : {profile}")
    return profile


# ── Synthèse ──────────────────────────────────────────────────────────────────
def _envelope(samples: np.ndarray, frame_rate: int, step_ms: int = 50) -> np.ndarray:
    """Enveloppe RMS par tranche de step_ms — alimente la visu du HUD."""
    step = max(1, int(frame_rate * step_ms / 1000))
    n = len(samples) // step
    if n == 0:
        return np.zeros(1, dtype=np.float32)
    trimmed = samples[: n * step].astype(np.float32) / 32768.0
    return np.sqrt(np.mean(trimmed.reshape(n, step) ** 2, axis=1))


def speak(text: str, on_level: Optional[Callable[[float], None]] = None) -> None:
    """Synthétise et joue `text`. Respecte stop_speaking (fondu de sortie)."""
    state.stop_speaking.clear()
    state.is_speaking = True

    try:
        response = requests.post(
            config.SPEACHES_TTS_URL,
            json={"model": config.TTS_MODEL, "input": text, "voice": config.TTS_VOICE},
            timeout=config.REQUEST_TIMEOUT,
        )
        if response.status_code == 200 and not state.stop_speaking.is_set():
            buffer = io.BytesIO(response.content)
            audio = AudioSegment.from_mp3(buffer)
            audio = audio.fade_in(200)

            samples = np.array(audio.get_array_of_samples(), dtype=np.int16)
            env = _envelope(samples, audio.frame_rate)
            sd.play(samples, samplerate=audio.frame_rate)

            t0 = time.time()
            while sd.get_stream().active:
                if state.stop_speaking.is_set():
                    # Fondu à la fin avant de couper (150ms)
                    sd.stop()
                    remaining = audio[-300:].fade_out(150)
                    fade_samples = np.array(remaining.get_array_of_samples(), dtype=np.int16)
                    sd.play(fade_samples, samplerate=audio.frame_rate)
                    sd.wait()
                    break
                if on_level is not None:
                    idx = min(len(env) - 1, int((time.time() - t0) * 1000 / 50))
                    on_level(float(env[idx]))
                time.sleep(0.05)
        elif response.status_code != 200:
            print(f"Erreur TTS HTTP {response.status_code}: {response.text[:200]}")
    except Exception as e:
        print(f"Erreur TTS: {e}")

    if on_level is not None:
        on_level(0.0)
    state.is_speaking = False


# ── Interruption (barge-in) ───────────────────────────────────────────────────
def listen_for_interrupt() -> None:
    """Écoute le micro pendant que Jarvis parle ; coupe tout si Monsieur parle.

    Tourne dans un thread dédié, s'arrête quand stop_speaking est levé.
    """
    sample_rate = 16000
    consecutive_speech = 0
    cfg = config.INTERRUPT_PROFILES[detect_output_profile()]

    # Vider l'audio accumulé pendant que le flux était inactif
    capture.interrupt.flush()
    time.sleep(cfg["start_delay"])

    while not state.stop_speaking.is_set():
        if capture.interrupt.raw is None:
            break
        chunk = capture.interrupt.read(512)
        speech_prob = vad.prob_int16(chunk, sample_rate)
        rms = vad.rms_int16(chunk)

        if speech_prob > cfg["vad"] and rms > cfg["min_rms"]:
            consecutive_speech += 1
            if consecutive_speech >= cfg["min_consecutive"]:
                print("\n(Interrompu)")
                state.stop_speaking.set()
                state.stop_agent.set()
                sd.stop()
                break
        else:
            consecutive_speech = 0

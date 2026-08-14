"""Détection du mot d'éveil « Jarvis » — modèle TFLite local, fenêtre glissante.

TensorFlow n'est importé qu'au chargement du modèle (~500 Mo, +2-3 s) pour
garder le module léger à importer.
"""
from __future__ import annotations

import time
from collections import deque
from typing import Callable, Optional

import numpy as np

from agents.desktop import config
from agents.desktop.audio import vad

_interpreter = None
_input_details = None
_output_details = None


def load_model() -> bool:
    global _interpreter, _input_details, _output_details
    if not config.WAKE_WORD_MODEL_PATH.exists():
        print(f"Modèle wake word introuvable : {config.WAKE_WORD_MODEL_PATH}")
        return False
    try:
        import warnings
        warnings.filterwarnings(
            "ignore", message=r".*tf\.lite\.Interpreter is deprecated.*",
            category=UserWarning,
        )
        import tensorflow as tf
        _interpreter = tf.lite.Interpreter(model_path=str(config.WAKE_WORD_MODEL_PATH))
        _interpreter.allocate_tensors()
        _input_details = _interpreter.get_input_details()
        _output_details = _interpreter.get_output_details()
        print("Modèle wake word chargé.")
        return True
    except Exception as e:
        print(f"Erreur chargement wake word : {e}")
        _interpreter = None
        return False


def _normalize(audio: np.ndarray) -> np.ndarray:
    """Ramène la fenêtre à un niveau de référence.

    DOIT rester identique à normalize_audio() dans wakeword/entrainer.py :
    toute divergence remet le modèle hors de sa distribution d'entraînement.
    """
    rms = float(np.sqrt(np.mean(np.square(audio))))
    if rms < 1e-7:
        return audio
    return (audio * (config.WAKE_WORD_TARGET_RMS / rms)).astype(np.float32)


def _extract_features(audio: np.ndarray) -> np.ndarray:
    import librosa
    if len(audio) < config.WAKE_WORD_WINDOW_SAMPLES:
        audio = np.pad(audio, (0, config.WAKE_WORD_WINDOW_SAMPLES - len(audio)))
    else:
        audio = audio[:config.WAKE_WORD_WINDOW_SAMPLES]
    audio = _normalize(audio.astype(np.float32))
    mfcc = librosa.feature.mfcc(y=audio, sr=config.WAKE_WORD_SAMPLE_RATE, n_mfcc=40)
    features = mfcc.T.astype(np.float32)
    if features.shape != (47, 40):
        fixed = np.zeros((47, 40), dtype=np.float32)
        rows = min(47, features.shape[0])
        cols = min(40, features.shape[1])
        fixed[:rows, :cols] = features[:rows, :cols]
        features = fixed
    return np.expand_dims(features, axis=0)


def score(audio: np.ndarray) -> float:
    if _interpreter is None:
        return 0.0
    try:
        features = _extract_features(audio)
        _interpreter.set_tensor(_input_details[0]["index"], features)
        _interpreter.invoke()
        output = _interpreter.get_tensor(_output_details[0]["index"])
        return float(np.squeeze(output))
    except Exception as e:
        print(f"Erreur score wake word : {e}")
        return 0.0


def listen(stream,
           poll_text: Callable[[], Optional[str]],
           is_muted: Callable[[], bool],
           on_level: Optional[Callable[[float], None]] = None) -> str:
    """Boucle d'attente du mot d'éveil.

    Retourne :
      - ""            : wake word détecté au micro
      - un texte      : saisie clavier depuis le HUD (ou token de contrôle)

    poll_text/is_muted sont fournis par le runtime : ce module ne dépend
    d'aucune UI.
    """
    chunk_size = 512
    score_counter = 0
    consecutive_hits = 0
    last_trigger_time = 0.0
    ring_buffer: deque = deque(maxlen=config.WAKE_WORD_WINDOW_SAMPLES)
    print("\nEn attente de 'Jarvis'...")

    while True:
        typed = poll_text()
        if typed:
            if not typed.startswith("__"):   # tokens de contrôle transmis tels quels
                print(f"[HUD] Saisie texte : {typed}")
                stream.flush()
            return typed

        # Mode mute : écoute micro suspendue, seule la saisie texte est active
        if is_muted():
            time.sleep(0.05)
            continue

        chunk = stream.read(chunk_size)
        ring_buffer.extend(chunk.tolist())
        score_counter += 1

        rms_now = vad.rms_int16(chunk)
        if on_level:
            on_level(rms_now)

        if len(ring_buffer) < config.WAKE_WORD_WINDOW_SAMPLES:
            continue
        if score_counter < config.WAKE_WORD_STEP_CHUNKS:
            continue

        score_counter = 0
        audio_window = np.array(ring_buffer, dtype=np.float32) / 32768.0

        # Vérification volume d'abord — si trop silencieux, pas la peine de scorer
        rms = float(np.sqrt(np.mean(np.square(audio_window))))
        if rms < config.WAKE_WORD_MIN_RMS:
            consecutive_hits = 0
            continue

        s = score(audio_window)
        if s >= config.WAKE_WORD_THRESHOLD:
            consecutive_hits += 1
            print(f"[Wake word score: {s:.2f}] rms={rms:.4f}")
        else:
            consecutive_hits = 0

        now = time.time()
        if (consecutive_hits >= config.WAKE_WORD_CONSECUTIVE_HITS
                and now - last_trigger_time > config.WAKE_WORD_COOLDOWN_SECONDS):
            # Vérifier qu'il y a vraiment de la parole avec le VAD
            vad_chunk = stream.read(512)
            vad_prob = vad.prob_int16(vad_chunk)
            rms = vad.rms_int16(vad_chunk)

            if vad_prob < 0.3 and rms < config.WAKE_WORD_MIN_RMS * 2:
                # Faux positif — bruit ambiant, pas de vraie voix
                consecutive_hits = 0
                continue

            last_trigger_time = now
            consecutive_hits = 0
            print(f"'{config.WAKE_WORD}' détecté ! (score: {s:.2f})")
            stream.flush()
            return ""

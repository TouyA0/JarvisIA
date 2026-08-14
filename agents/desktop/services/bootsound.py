"""Son de démarrage synthétisé — montée harmonique + ping, façon mise sous
tension de réacteur. Généré en numpy, aucun fichier audio externe.
"""
from __future__ import annotations

import numpy as np


def play(blocking: bool = True) -> None:
    try:
        import sounddevice as sd

        sr = 22050
        dur = 1.1
        t = np.linspace(0, dur, int(sr * dur), endpoint=False)

        # Balayage 180 → 880 Hz (exponentiel, effet "mise sous tension")
        f0, f1 = 180.0, 880.0
        freq = f0 * (f1 / f0) ** (t / dur)
        phase = 2 * np.pi * np.cumsum(freq) / sr
        sweep = np.sin(phase) * 0.4 + np.sin(2 * phase) * 0.15

        # Hum grave qui s'installe
        hum = np.sin(2 * np.pi * 110 * t) * np.clip(t / 0.4, 0, 1) * 0.18

        # Ping cristallin à 85 % de la montée
        ping_start = int(0.85 * len(t))
        ping_t = t[: len(t) - ping_start]
        ping = np.zeros_like(t)
        ping[ping_start:] = np.sin(2 * np.pi * 1568 * ping_t) * np.exp(-ping_t * 14) * 0.5

        env = np.minimum(np.clip(t / 0.15, 0, 1), np.clip((dur - t) / 0.25, 0, 1))
        audio = (sweep + hum) * env + ping
        audio = (audio / np.max(np.abs(audio)) * 0.30 * 32767).astype(np.int16)

        sd.play(audio, samplerate=sr)
        if blocking:
            sd.wait()
    except Exception as e:
        print(f"[Boot sound] {e}")

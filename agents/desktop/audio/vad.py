"""Détection de parole (Silero VAD).

torch n'est importé qu'à l'initialisation : le module reste léger à importer
(utile pour les outils de preview UI qui n'ont pas besoin de l'audio).
"""
from __future__ import annotations

import numpy as np

_torch = None
_model = None


def init() -> None:
    """Charge Silero VAD. À appeler une fois au démarrage du runtime."""
    global _torch, _model
    if _model is not None:
        return
    import torch
    print("Chargement de Silero VAD...")
    _model, _ = torch.hub.load(
        repo_or_dir="snakers4/silero-vad", model="silero_vad",
        force_reload=False, trust_repo=True,
    )
    _torch = torch
    print("Silero VAD chargé.")


def prob_int16(chunk: np.ndarray, sample_rate: int = 16000) -> float:
    """Probabilité de parole d'un chunk int16 (512 échantillons attendus)."""
    audio_float = _torch.FloatTensor(chunk.astype(np.float32) / 32768.0)
    return _model(audio_float, sample_rate).item()


def rms_int16(chunk: np.ndarray) -> float:
    f = chunk.astype(np.float32) / 32768.0
    return float(np.sqrt(np.mean(np.square(f))))

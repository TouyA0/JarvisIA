"""États globaux partagés entre threads.

Deux événements pilotent tout le cycle parole/interruption :
  - stop_speaking : coupe la synthèse vocale en cours (barge-in)
  - stop_agent    : abandonne le tour complet de l'agent (réflexion incluse)
"""
from __future__ import annotations

import threading
import time

stop_speaking = threading.Event()
stop_agent = threading.Event()

# Indicateurs simples, mutés uniquement par le runtime (pas de course réelle :
# lus par l'UI pour affichage, jamais pour une décision critique).
is_paused = False
is_waiting = True
is_speaking = False
is_busy = False       # un tour (question → réponse) est en cours de traitement

started_at = time.time()

# ── Métriques temps réel (affichées dans le HUD) ─────────────────────────────
_metrics_lock = threading.Lock()
_metrics = {
    "stt_ms": 0,        # durée de la dernière transcription
    "llm_first_ms": 0,  # temps jusqu'au premier token du dernier tour LLM
    "turn_ms": 0,       # durée totale du dernier tour (question → fin réponse)
}


def set_metric(key: str, value: float) -> None:
    with _metrics_lock:
        _metrics[key] = int(value)


def get_metrics() -> dict:
    with _metrics_lock:
        return dict(_metrics)

"""État en mémoire du brain.

Volontairement minimal pour l'instant : juste des métriques de suivi
(temps de première réponse LLM). Les signaux d'interruption vocale
(stop_speaking, stop_agent) restent dans `agents/desktop/state.py` — ce
sont des `threading.Event` qui ne veulent rien dire une fois brain et
agent dans deux process séparés. Le jour où le brain doit pouvoir couper
une génération en cours depuis le web (bouton « stop » côté Console), ce
sera un message du protocole (`agents/protocol/`), pas un Event partagé.
"""
from __future__ import annotations

import threading

_metrics_lock = threading.Lock()
_metrics: dict[str, float] = {
    "llm_first_ms": 0,
}


def set_metric(key: str, value: float) -> None:
    with _metrics_lock:
        _metrics[key] = int(value)


def get_metrics() -> dict:
    with _metrics_lock:
        return dict(_metrics)

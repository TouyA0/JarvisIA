"""Suivi de la consommation API Claude (tokens + coût, rotation mensuelle)."""
from __future__ import annotations

import json
import threading
import time
from typing import Callable, Optional

from brain import config

_usage_lock = threading.Lock()

# Callback branché par le runtime : (dernier coût, coût du mois, nb appels)
on_update: Optional[Callable[[float, float, int], None]] = None


def _load() -> dict:
    if config.USAGE_FILE.exists():
        try:
            with open(config.USAGE_FILE, encoding="utf-8") as f:
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
        "history": [],
    }


def _save(data: dict) -> None:
    with open(config.USAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def track(usage_obj) -> float:
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

    cost = (input_t * config.HAIKU_PRICES["input"]
            + output_t * config.HAIKU_PRICES["output"]
            + cache_w * config.HAIKU_PRICES["cache_write"]
            + cache_r * config.HAIKU_PRICES["cache_read"])

    current_month = time.strftime("%Y-%m")
    with _usage_lock:
        data = _load()

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

        _save(data)

        if on_update:
            try:
                on_update(cost, data["current"]["cost_usd"], data["current"]["calls"])
            except Exception:
                pass

    return cost


def snapshot() -> dict:
    """Copie brute du fichier de suivi — pour la Console web, qui affiche
    le détail (tokens par catégorie, historique mensuel) que `summary()`
    aplatit volontairement pour le HUD."""
    return _load()


def summary() -> dict:
    data = _load()
    return {
        "month": data["current_month"],
        "month_cost_usd": data["current"]["cost_usd"],
        "month_calls": data["current"]["calls"],
        "month_tokens": data["current"]["input_tokens"] + data["current"]["output_tokens"],
        "last_cost_usd": data["last_call"]["cost_usd"],
    }

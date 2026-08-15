"""Diagnostics système RÉELS pour le HUD (fini les valeurs simulées).

Toutes les 2 s : CPU, RAM, disque, débit réseau, latence du dernier tour,
tokens/coût du mois. Toutes les 30 s : état des liaisons (Speaches, Ollama,
clé Claude).
"""
from __future__ import annotations

import threading
import time
from urllib.parse import urlparse

from agents.desktop import config, state


def _speaches_base() -> str:
    u = urlparse(config.SPEACHES_STT_URL)
    return f"{u.scheme}://{u.netloc}"


def _check_links() -> dict:
    import requests
    links = {}
    try:
        r = requests.get(_speaches_base() + "/health", timeout=1.5)
        links["speaches"] = r.status_code < 500
    except Exception:
        try:
            r = requests.get(_speaches_base(), timeout=1.5)
            links["speaches"] = True
        except Exception:
            links["speaches"] = False
    try:
        u = urlparse(config.OLLAMA_URL)
        r = requests.get(f"{u.scheme}://{u.netloc}/api/version", timeout=1.5)
        links["ollama"] = r.status_code == 200
    except Exception:
        links["ollama"] = False
    links["claude"] = bool(config.ANTHROPIC_API_KEY)
    return links


def start(push: callable) -> None:
    """Démarre le thread d'échantillonnage. `push(data: dict)` est appelé
    toutes les 2 s avec les mesures fraîches."""

    def _loop():
        import psutil
        psutil.cpu_percent(interval=None)   # amorce le compteur
        last_net = psutil.net_io_counters()
        last_t = time.time()
        links = {}
        last_links_at = 0.0

        while True:
            time.sleep(2.0)
            try:
                now = time.time()
                cpu = int(psutil.cpu_percent(interval=None))
                mem = int(psutil.virtual_memory().percent)
                try:
                    disk = int(psutil.disk_usage("C:\\").percent)
                except Exception:
                    disk = 0

                net = psutil.net_io_counters()
                dt = max(0.001, now - last_t)
                net_up = int((net.bytes_sent - last_net.bytes_sent) / dt / 1024)
                net_dn = int((net.bytes_recv - last_net.bytes_recv) / dt / 1024)
                last_net, last_t = net, now

                if now - last_links_at > 30:
                    links = _check_links()
                    last_links_at = now

                from brain.core import usage
                s = usage.summary()

                metrics = state.get_metrics()
                uptime = int(now - state.started_at)

                push({
                    "cpu": cpu, "mem": mem, "disk": disk,
                    "net_up": net_up, "net_dn": net_dn,
                    "lat_ms": metrics.get("llm_first_ms", 0) or metrics.get("stt_ms", 0),
                    "stt_ms": metrics.get("stt_ms", 0),
                    "tokens": s["month_tokens"],
                    "cost_usd": s["month_cost_usd"],
                    "calls": s["month_calls"],
                    "uptime": f"{uptime // 3600:02d}:{(uptime % 3600) // 60:02d}:{uptime % 60:02d}",
                    "links": links,
                })
            except Exception as e:
                print(f"[Diagnostics] {e}")

    threading.Thread(target=_loop, daemon=True).start()

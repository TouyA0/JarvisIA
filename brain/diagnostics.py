"""Diagnostics système à la demande — carte "diagnostics" (voir
docs/ROADMAP_DISPLAY_INTEGRATIONS.md §2.2, resté non fait jusqu'ici).

Différent de agents/desktop/services/diagnostics.py : celui-là échantillonne
en continu (toutes les 2s) pour alimenter le HUD Qt en temps réel — ici,
un seul instantané à la demande ("comment va le PC ?"), pas de thread, pas
de polling permanent qui n'aurait pas d'utilité côté brain.

Mesure la machine où tourne CE process (le brain) — dans l'immense majorité
des installations, brain et agent desktop tournent sur le même PC (voir
README.md), donc ça correspond bien au "PC" dont Monsieur parle. Si un jour
le brain tourne ailleurs (Raspberry Pi VPN, évoqué dans
ROADMAP_MULTIDEVICE.md), ce serait alors les diagnostics de CE serveur-là,
pas du poste de travail — distinction à garder en tête si ça arrive.
"""
from __future__ import annotations

from brain.core import usage


def snapshot() -> dict:
    import psutil

    cpu = int(psutil.cpu_percent(interval=0.3))
    mem = int(psutil.virtual_memory().percent)
    try:
        disk = int(psutil.disk_usage("C:\\" if _is_windows() else "/").percent)
    except Exception:
        disk = 0
    s = usage.summary()
    return {
        "cpu": cpu,
        "mem": mem,
        "disk": disk,
        "month_cost_usd": s["month_cost_usd"],
        "month_calls": s["month_calls"],
    }


def _is_windows() -> bool:
    import platform
    return platform.system() == "Windows"

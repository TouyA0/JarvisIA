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

from brain.core import convlog, usage


def snapshot() -> dict:
    import psutil

    cpu = int(psutil.cpu_percent(interval=0.3))
    mem = int(psutil.virtual_memory().percent)
    try:
        disk = int(psutil.disk_usage("C:\\" if _is_windows() else "/").percent)
    except Exception:
        disk = 0
    s = usage.summary()
    # Taux réel local (Ollama) / Claude sur la boucle à outils (F7 phase 2),
    # pas une estimation — lu depuis le journal des échanges.
    agent_stats = convlog.agent_tool_stats()
    return {
        "cpu": cpu,
        "mem": mem,
        "disk": disk,
        "month_cost_usd": s["month_cost_usd"],
        "month_calls": s["month_calls"],
        "local_calls": agent_stats["local_calls"],
        "claude_calls": agent_stats["claude_calls"],
        "local_rate": agent_stats["local_rate"],
    }


def _is_windows() -> bool:
    import platform
    return platform.system() == "Windows"

"""Journal persistant des conversations (JSONL mensuel dans data/logs/)."""
from __future__ import annotations

import json
import threading
import time

from brain import config

_lock = threading.Lock()


def log_exchange(question: str, answer: str, source: str = "") -> None:
    entry = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "question": question,
        "answer": answer,
        "source": source,
    }
    path = config.LOGS_DIR / f"conversations-{time.strftime('%Y-%m')}.jsonl"
    with _lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def agent_tool_stats(months: int = 1) -> dict:
    """Compte les tours de la boucle à outils (F7) par source, sur les
    `months` derniers fichiers mensuels — ignore la conversation pure
    (source="ollama"/"claude"), seule la boucle à outils (agenda, mails,
    météo, pilotage PC…) nous intéresse ici. Sert la carte "diagnostics"
    (voir brain/diagnostics.py) : c'est le chiffre réel qui dit si le
    sous-ensemble local (F7 phase 2) mérite d'être étendu."""
    files = sorted(config.LOGS_DIR.glob("conversations-*.jsonl"), reverse=True)[:months]
    local = claude = 0
    for path in files:
        try:
            with open(path, encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            continue
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            src = entry.get("source")
            if src == "ollama-agent":
                local += 1
            elif src == "claude-agent":
                claude += 1
    total = local + claude
    return {
        "local_calls": local,
        "claude_calls": claude,
        "local_rate": round(local / total * 100) if total else None,
    }


def recent(limit: int = 40) -> list[dict]:
    """Les `limit` derniers échanges, du plus ancien au plus récent.

    Relit les fichiers mensuels à rebours plutôt que de servir
    `history.conversation_history` : celui-ci est vidé à chaque
    redémarrage du brain et plafonné à 30 messages, alors que la Console
    web a besoin de retrouver sa conversation après un simple F5.
    """
    files = sorted(config.LOGS_DIR.glob("conversations-*.jsonl"), reverse=True)
    entries: list[dict] = []
    for path in files:
        try:
            with open(path, encoding="utf-8") as f:
                lines = f.readlines()
        except OSError:
            continue
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # ligne tronquée par un arrêt brutal — on la saute
            if len(entries) >= limit:
                return list(reversed(entries))
    return list(reversed(entries))

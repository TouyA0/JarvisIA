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

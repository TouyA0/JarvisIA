"""J.A.R.V.I.S. — point d'entrée.

Lance : python jarvis.py   (ou via start_jarvis.bat / launch_jarvis.vbs)
Le code de l'agent desktop vit dans agents/desktop/ — voir README.md pour l'architecture.
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

if __name__ == "__main__":
    print("=== J.A.R.V.I.S. — démarrage ===")
    from agents.desktop import runtime
    runtime.start()

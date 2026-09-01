"""J.A.R.V.I.S. — point d'entrée.

Lance : python jarvis.py   (ou via start_jarvis.bat / launch_jarvis.vbs)
Le code de l'agent desktop vit dans agents/desktop/ — voir README.md pour l'architecture.
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")
os.environ.setdefault("TF_ENABLE_ONEDNN_OPTS", "0")

# Sans ça, un process Windows non déclaré "DPI aware" reçoit du système une
# image bureau déjà mise à l'échelle (floue) sur tout écran configuré à
# 125%/150%/etc. — ça touche pyautogui/PIL (agents/desktop/tools/screen.py,
# take_screenshot/capture_frame) qui passent par l'API GDI brute, pas Qt
# (screen.grabWindow(0) dans ui/snip.py récupère déjà les pixels physiques,
# Qt gère sa propre awareness). Doit s'exécuter AVANT toute création de
# fenêtre — donc avant l'import de agents.desktop.runtime, qui instancie
# QApplication. Per-Monitor-V2 (le plus précis) avec repli sur l'API plus
# ancienne si shcore est indisponible (Windows 7).
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

if __name__ == "__main__":
    print("=== J.A.R.V.I.S. — démarrage ===")
    from agents.desktop import runtime
    runtime.start()

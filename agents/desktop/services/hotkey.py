"""Raccourcis clavier globaux (RegisterHotKey via ctypes, zéro dépendance).

Par défaut :
  Ctrl+Alt+J → afficher le HUD et donner le focus à la saisie
  Ctrl+Alt+V → Vision ciblée (sélection d'une zone d'écran à analyser)
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import threading
from typing import Callable

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
WM_HOTKEY = 0x0312


def start(bindings: list[tuple[int, str, Callable[[], None]]]) -> None:
    """bindings : liste de (modificateurs, lettre, callback).

    Le hotkey doit être enregistré ET écouté depuis le même thread — d'où la
    boucle de messages dédiée.
    """
    def _loop():
        user32 = ctypes.windll.user32
        callbacks: dict[int, Callable[[], None]] = {}
        for i, (mods, ch, cb) in enumerate(bindings, start=1):
            if user32.RegisterHotKey(None, i, mods, ord(ch.upper())):
                callbacks[i] = cb
                print(f"[Hotkey] Ctrl+Alt+{ch.upper()} actif.")
            else:
                print(f"[Hotkey] Ctrl+Alt+{ch.upper()} indisponible (déjà pris par une autre app).")
        if not callbacks:
            return
        msg = ctypes.wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            if msg.message == WM_HOTKEY:
                cb = callbacks.get(msg.wParam)
                if cb:
                    try:
                        cb()
                    except Exception:
                        pass

    threading.Thread(target=_loop, daemon=True).start()

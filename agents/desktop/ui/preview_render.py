"""Rendu offscreen du HUD en PNG — pour vérifier le design sans ouvrir de
fenêtre sur le bureau.

Usage : python -m agents.desktop.ui.preview_render
Sorties : build_preview/hud_<état>.png
"""
from __future__ import annotations

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
# Plateforme réelle (vraies polices) mais la fenêtre n'est JAMAIS affichée :
# _on_show est neutralisé ci-dessous, le rendu passe par widget.grab().
# Mettre QT_PREVIEW_OFFSCREEN=1 pour forcer le mode offscreen (CI, etc.).
if os.getenv("QT_PREVIEW_OFFSCREEN") == "1":
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication  # noqa: E402

from agents.desktop import config  # noqa: E402
from agents.desktop.ui.hud import JarvisOverlay, _JarvisWindow, _Signals  # noqa: E402


def main() -> None:
    out_dir = config.BUILD_PREVIEW_DIR
    out_dir.mkdir(exist_ok=True)

    app = QApplication(sys.argv)
    ov = JarvisOverlay()
    ov._app = app
    ov._sig = _Signals()
    win = _JarvisWindow(ov._sig, ov._input_queue, ov)
    ov._win = win
    win._on_show = lambda ms: None   # jamais de fenêtre visible pendant le rendu

    # Données réalistes
    win._on_set_weather("21° CIEL DÉGAGÉ")
    win._on_set_timer_chip("◷ 04:32")
    win._on_set_model_label("qwen3:14b")
    import random
    for i in range(40):
        win._on_update_diag({
            "cpu": 18 + int(14 * abs(__import__('math').sin(i / 5))) + random.randint(0, 6),
            "mem": 40 + random.randint(0, 3),
        })
    win._on_update_diag({
        "cpu": 23, "mem": 41, "disk": 67, "net_up": 12, "net_dn": 340,
        "lat_ms": 640, "tokens": 48213, "cost_usd": 0.021, "calls": 14,
        "uptime": "02:41:07",
        "links": {"speaches": True, "ollama": True, "claude": True},
    })
    from agents.desktop import APP_VERSION
    win._conv.add_system(f"J.A.R.V.I.S. MARK {APP_VERSION} — mise sous tension…")
    win._conv.add_system("Tous les systèmes sont nominaux.")
    win._on_set_transcript("Jarvis, ouvre mon agenda et dis-moi la météo.")
    win._on_set_source("ollama")
    win._on_set_response("Notion Calendar est ouvert, Monsieur. "
                         "Il fait 21 degrés à Toulouse, ciel dégagé.")
    win._on_finish_response("2.4s")
    win._on_set_transcript("Regarde ça, c'est quoi cette erreur ?  ⌖")
    win._on_set_source("ai")
    win._on_set_response("Une erreur de segmentation dans le module audio, "
                         "Monsieur. Rien que nous ne puissions corriger.")
    win._on_set_cost(0.000024, 0.0187, 14)

    # Avancer l'animation et terminer le boot du réacteur
    win._reactor._boot_t0 -= 10
    for _ in range(30):
        win._tick()

    for st in ("idle", "listening", "processing", "speaking", "error"):
        win._on_set_state(st)
        win._reactor._boot_t0 = 0   # boot terminé quel que soit l'état
        if st in ("listening", "speaking"):
            win._on_set_level(0.028)
        elif st == "processing":
            win._on_set_activity("run_powershell")
        else:
            win._on_set_level(0.0)
            win._on_set_activity("")
        for _ in range(14):
            win._tick()
        app.processEvents()
        pm = win.grab()
        path = out_dir / f"hud_{st}.png"
        pm.save(str(path))
        print(f"→ {path}")

    print("Rendu terminé.")


if __name__ == "__main__":
    main()

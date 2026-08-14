"""Icône de zone de notification — QSystemTrayIcon natif Qt.

Remplace pystray (v1) : plus de thread dédié ni de dépendance externe,
l'icône vit sur le thread Qt comme le reste de l'UI.
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QColor, QIcon
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from agents.desktop.ui.icons import reactor_pixmap
from agents.desktop.ui.theme import C_GOLD, C_GREEN, C_RED

_STATUS_COLORS = {
    "paused": QColor(C_RED),
    "waiting": QColor(C_GOLD),
    "active": QColor(C_GREEN),
}
_STATUS_TITLES = {
    "paused": "Jarvis — En pause",
    "waiting": "Jarvis — En attente",
    "active": "Jarvis — Actif",
}


def _make_icon(color: QColor) -> QIcon:
    """Arc reactor avec noyau teinté selon l'état."""
    icon = QIcon()
    for s in (16, 24, 32, 48):
        icon.addPixmap(reactor_pixmap(s, core=color))
    return icon


class Tray(QObject):
    """Doit être créé sur le thread Qt. set_status() est thread-safe."""
    _sig_status = pyqtSignal(str)

    def __init__(self, on_show, on_toggle_pause, on_quit):
        super().__init__()
        self._icons = {k: _make_icon(c) for k, c in _STATUS_COLORS.items()}
        self._tray = QSystemTrayIcon(self._icons["waiting"])
        self._tray.setToolTip(_STATUS_TITLES["waiting"])

        menu = QMenu()
        act_show = menu.addAction("Afficher Jarvis")
        act_pause = menu.addAction("Pause / Reprendre")
        menu.addSeparator()
        act_quit = menu.addAction("Quitter Jarvis")
        act_show.triggered.connect(lambda: on_show())
        act_pause.triggered.connect(lambda: on_toggle_pause())
        act_quit.triggered.connect(lambda: on_quit())
        self._menu = menu
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_activated)
        self._on_show = on_show
        self._sig_status.connect(self._apply_status)
        self._tray.show()

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:  # simple clic
            self._on_show()

    def set_status(self, status: str) -> None:
        """'paused' | 'waiting' | 'active' — appelable depuis tout thread."""
        self._sig_status.emit(status)

    def _apply_status(self, status: str) -> None:
        icon = self._icons.get(status)
        if icon:
            self._tray.setIcon(icon)
            self._tray.setToolTip(_STATUS_TITLES.get(status, "Jarvis"))

    def hide(self) -> None:
        self._tray.hide()

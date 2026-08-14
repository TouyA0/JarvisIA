"""Dialogues thématisés (confirmation destructive, demande d'aide).

Remplacent les popups tkinter de la v1 : même moteur Qt que le HUD, même
thème, et surtout plus de second toolkit graphique dans le process.

Les fonctions publiques (confirm_destructive, request_help) sont BLOQUANTES
et appelables depuis n'importe quel thread de travail : elles postent un
signal vers le thread Qt qui crée le dialogue, puis attendent le résultat
sur un threading.Event.
"""
from __future__ import annotations

import threading

from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QColor, QCursor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout,
    QWidget,
)

from agents.desktop.ui.theme import (
    C_BG, C_BG2, C_CYAN, C_GOLD, C_RED, C_TEXT, C_TEXT_DIM, FONT,
    hexa, rgba_css, with_alpha,
)

_bridge = None


class _Bridge(QObject):
    do_confirm = pyqtSignal(str, object)          # (commande, holder)
    do_help = pyqtSignal(str, str, object)        # (essayé, besoin, holder)

    def __init__(self):
        super().__init__()
        self.do_confirm.connect(self._open_confirm)
        self.do_help.connect(self._open_help)

    def _open_confirm(self, command, holder):
        dlg = _ConfirmDialog(command, holder)
        holder["dialog"] = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _open_help(self, tried, need, holder):
        dlg = _HelpDialog(tried, need, holder)
        holder["dialog"] = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()


def init() -> None:
    """À appeler une fois sur le thread Qt, après création du QApplication."""
    global _bridge
    if _bridge is None:
        _bridge = _Bridge()


# ── Base : fenêtre HUD flottante ─────────────────────────────────────────────
class _HudDialog(QWidget):
    W, H = 480, 240

    def __init__(self, accent: QColor):
        super().__init__()
        self._accent = accent
        self._drag_offset = None
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.W, self.H)
        scr = QApplication.primaryScreen().geometry()
        self.move(scr.width() - self.W - 26, 70)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        col = self._accent

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(C_BG))
        p.drawRoundedRect(self.rect(), 6, 6)

        p.setPen(QPen(with_alpha(col, 110), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 6, 6)
        p.setPen(QPen(with_alpha(col, 230), 2))
        p.drawLine(0, 1, w, 1)

        L = 16
        p.setPen(QPen(with_alpha(col, 255), 2))
        for (ox, oy, sx, sy) in [(0, 0, 1, 1), (w, 0, -1, 1), (0, h, 1, -1), (w, h, -1, -1)]:
            p.drawLine(ox, oy + sy * 2, ox, oy + sy * L)
            p.drawLine(ox + sx * 2, oy, ox + sx * L, oy)
        p.end()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = e.pos()

    def mouseMoveEvent(self, e):
        if self._drag_offset is not None:
            self.move(e.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, _):
        self._drag_offset = None

    def _btn(self, text, color, filled=False):
        b = QPushButton(text)
        b.setFont(QFont(FONT, 9, QFont.Weight.Bold))
        b.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        bg = rgba_css(QColor(color), 0.18) if filled else rgba_css(C_BG2, 0.9)
        b.setStyleSheet(
            f"QPushButton {{ background:{bg}; color:{color};"
            f" border:1px solid {color}; border-radius:3px; padding:7px 18px;"
            " letter-spacing:1px; }"
            "QPushButton:hover { background:#122a40; }"
        )
        return b


# ── Confirmation d'action destructive ────────────────────────────────────────
class _ConfirmDialog(_HudDialog):
    def __init__(self, command: str, holder: dict):
        super().__init__(QColor(C_RED))
        self._holder = holder

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(8)

        title = QLabel("⚠  CONFIRMATION REQUISE")
        title.setFont(QFont(FONT, 10, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{hexa(C_RED)}; background:transparent; letter-spacing:2px;")
        root.addWidget(title)

        sub = QLabel("Action potentiellement irréversible détectée :")
        sub.setFont(QFont(FONT, 8))
        sub.setStyleSheet(f"color:{hexa(C_TEXT)}; background:transparent;")
        root.addWidget(sub)

        cmd = QLabel(command[:400])
        cmd.setFont(QFont(FONT, 8))
        cmd.setWordWrap(True)
        cmd.setStyleSheet(
            f"color:{hexa(C_GOLD)}; background:{rgba_css(QColor(20, 8, 8), 0.85)};"
            f" border:1px solid {rgba_css(C_RED, 0.3)}; border-radius:3px; padding:8px;")
        root.addWidget(cmd, 1)

        row = QHBoxLayout()
        refuse = self._btn("REFUSER", hexa(C_RED), filled=True)
        allow = self._btn("EXÉCUTER ➤", hexa(C_CYAN))
        refuse.clicked.connect(lambda: self._respond(False))
        allow.clicked.connect(lambda: self._respond(True))
        row.addWidget(refuse)
        row.addStretch()
        row.addWidget(allow)
        root.addLayout(row)

    def _respond(self, approved: bool):
        self._holder["approved"] = approved
        self._holder["event"].set()
        self.close()

    def closeEvent(self, e):
        if not self._holder["event"].is_set():
            self._holder["approved"] = False
            self._holder["event"].set()
        e.accept()


# ── Demande d'aide de l'agent ────────────────────────────────────────────────
class _HelpDialog(_HudDialog):
    W, H = 480, 360

    def __init__(self, tried: str, need: str, holder: dict):
        super().__init__(QColor(C_CYAN))
        self._holder = holder

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(7)

        title = QLabel("⚡  ASSISTANCE REQUISE")
        title.setFont(QFont(FONT, 10, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{hexa(C_CYAN)}; background:transparent; letter-spacing:2px;")
        root.addWidget(title)

        l1 = QLabel("CE QUE J'AI ESSAYÉ")
        l1.setFont(QFont(FONT, 7, QFont.Weight.Bold))
        l1.setStyleSheet(f"color:{hexa(C_TEXT_DIM)}; background:transparent; letter-spacing:1px;")
        root.addWidget(l1)
        t1 = QLabel(tried[:220] + ("…" if len(tried) > 220 else ""))
        t1.setFont(QFont(FONT, 8))
        t1.setWordWrap(True)
        t1.setStyleSheet(f"color:{hexa(C_TEXT_DIM)}; background:transparent;")
        root.addWidget(t1)

        l2 = QLabel("CE DONT J'AI BESOIN")
        l2.setFont(QFont(FONT, 7, QFont.Weight.Bold))
        l2.setStyleSheet(f"color:{hexa(C_CYAN)}; background:transparent; letter-spacing:1px;")
        root.addWidget(l2)
        t2 = QLabel(need)
        t2.setFont(QFont(FONT, 9))
        t2.setWordWrap(True)
        t2.setStyleSheet(f"color:{hexa(C_TEXT)}; background:transparent;")
        root.addWidget(t2)

        self._input = QTextEdit()
        self._input.setFont(QFont(FONT, 9))
        self._input.setPlaceholderText("Votre explication…  (Ctrl+Entrée pour envoyer)")
        self._input.setFixedHeight(90)
        self._input.setStyleSheet(
            f"QTextEdit {{ background:{rgba_css(QColor(3, 10, 18), 0.9)};"
            f" color:{hexa(QColor(232, 246, 255))};"
            f" border:1px solid {rgba_css(C_CYAN, 0.25)}; border-radius:3px; padding:6px; }}"
            f"QTextEdit:focus {{ border-color:{rgba_css(C_CYAN, 0.6)}; }}")
        root.addWidget(self._input)

        row = QHBoxLayout()
        hint = QLabel("Ctrl+Entrée pour envoyer")
        hint.setFont(QFont(FONT, 7))
        hint.setStyleSheet(f"color:{hexa(C_TEXT_DIM)}; background:transparent;")
        send = self._btn("ENVOYER ➤", hexa(C_CYAN), filled=True)
        send.clicked.connect(self._submit)
        row.addWidget(hint)
        row.addStretch()
        row.addWidget(send)
        root.addLayout(row)

        self._input.setFocus()
        self._input.installEventFilter(self)

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent
        if obj is self._input and event.type() == QEvent.Type.KeyPress:
            if (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                    and event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                self._submit()
                return True
        return super().eventFilter(obj, event)

    def _submit(self):
        text = self._input.toPlainText().strip()
        if text:
            self._holder["result"] = text
            self._holder["event"].set()
            self.close()

    def closeEvent(self, e):
        if not self._holder["event"].is_set():
            self._holder["event"].set()
        e.accept()


# ── API pour les threads de travail ──────────────────────────────────────────
# Deux temps (open puis wait) : l'appelant peut ouvrir le dialogue, parler
# pendant qu'il est affiché, puis attendre la décision.
def open_confirm(command: str) -> dict | None:
    if _bridge is None:
        print("[Dialogs] non initialisé — refus par défaut")
        return None
    holder = {"approved": False, "event": threading.Event(), "dialog": None}
    _bridge.do_confirm.emit(command, holder)
    return holder


def wait_confirm(holder: dict | None, timeout: float = 30) -> bool:
    if holder is None:
        return False
    holder["event"].wait(timeout=timeout)
    return bool(holder["approved"])


def confirm_destructive(command: str, timeout: float = 30) -> bool:
    return wait_confirm(open_confirm(command), timeout=timeout)


def open_help(tried: str, need: str) -> dict | None:
    if _bridge is None:
        print("[Dialogs] non initialisé — pas d'aide possible")
        return None
    holder = {"result": None, "event": threading.Event(), "dialog": None}
    _bridge.do_help.emit(tried, need, holder)
    return holder


def wait_help(holder: dict | None, timeout: float = 300) -> str | None:
    if holder is None:
        return None
    holder["event"].wait(timeout=timeout)
    return holder["result"]


def request_help(tried: str, need: str, timeout: float = 300) -> str | None:
    return wait_help(open_help(tried, need), timeout=timeout)

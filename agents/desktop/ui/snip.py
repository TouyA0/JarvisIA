"""Vision ciblée — sélecteur de zone d'écran façon outil Capture, style Stark.

Flux : le bureau est photographié, puis affiché plein écran assombri ;
Monsieur trace un rectangle (bords cyan, équerres, dimensions en direct) ;
la zone est découpée et renvoyée encodée, prête pour Claude vision.
Échap annule. Le HUD est masqué pendant la photo pour ne pas polluer la zone.

Même modèle thread que dialogs.py : open_selector() est appelable depuis un
thread de travail, la fenêtre vit sur le thread Qt, le résultat revient via
un threading.Event.
"""
from __future__ import annotations

import base64
import threading

from PyQt6.QtCore import Qt, QBuffer, QIODevice, QObject, QPoint, QRect, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QGuiApplication, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QApplication, QWidget

from agents.desktop.ui.theme import C_CYAN, FONT, with_alpha

_bridge = None

# En dessous de cette surface (px logiques), la sélection est considérée comme
# un clic raté plutôt qu'une vraie zone.
_MIN_SIZE = 12
# Largeur max envoyée au modèle : au-delà on réduit (coût vision ∝ surface).
_MAX_SEND_WIDTH = 1400


class _Bridge(QObject):
    do_open = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.do_open.connect(self._open)

    def _open(self, holder: dict):
        # Masquer le HUD le temps de la photo : il ne doit pas apparaître
        # dans la capture ni gêner la sélection.
        hud_win = None
        try:
            from agents.desktop.ui.hud import overlay
            hud_win = overlay._win
        except Exception:
            pass
        hud_was_visible = bool(hud_win and hud_win.isVisible())
        if hud_was_visible:
            hud_win.hide()
            QApplication.processEvents()

        screen = QGuiApplication.primaryScreen()
        shot = screen.grabWindow(0)   # pixels physiques (DPI inclus)

        win = _SnipWindow(shot, holder, restore_hud=hud_was_visible)
        holder["window"] = win
        win.showFullScreen()
        win.raise_()
        win.activateWindow()


def init() -> None:
    """À appeler une fois sur le thread Qt, après création du QApplication."""
    global _bridge
    if _bridge is None:
        _bridge = _Bridge()


class _SnipWindow(QWidget):
    def __init__(self, screenshot: QPixmap, holder: dict, restore_hud: bool):
        super().__init__()
        self._shot = screenshot
        self._holder = holder
        self._restore_hud = restore_hud
        self._origin: QPoint | None = None
        self._current: QPoint | None = None
        self._mouse: QPoint = QPoint(-1, -1)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)
        geo = QGuiApplication.primaryScreen().geometry()
        self.setGeometry(geo)
        # Facteur px physiques / px logiques (écrans à mise à l'échelle Windows)
        self._scale = self._shot.width() / max(1, geo.width())

    # ── Rendu ────────────────────────────────────────────────────────────────
    def paintEvent(self, _):
        p = QPainter(self)
        w, h = self.width(), self.height()

        # Bureau figé + voile sombre
        p.drawPixmap(self.rect(), self._shot)
        p.fillRect(self.rect(), QColor(3, 9, 18, 150))

        sel = self._selection_rect()
        if sel is not None:
            # Zone claire : redessiner la portion originale du bureau
            src = QRect(int(sel.x() * self._scale), int(sel.y() * self._scale),
                        int(sel.width() * self._scale), int(sel.height() * self._scale))
            p.drawPixmap(sel, self._shot, src)

            # Cadre + équerres
            p.setPen(QPen(with_alpha(QColor(C_CYAN), 230), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(sel)
            p.setPen(QPen(QColor(C_CYAN), 3))
            L = min(26, max(8, min(sel.width(), sel.height()) // 4))
            for (cx, cy, sx, sy) in [
                (sel.left(), sel.top(), 1, 1), (sel.right(), sel.top(), -1, 1),
                (sel.left(), sel.bottom(), 1, -1), (sel.right(), sel.bottom(), -1, -1),
            ]:
                p.drawLine(cx, cy, cx + sx * L, cy)
                p.drawLine(cx, cy, cx, cy + sy * L)

            # Dimensions en direct
            label = f"{sel.width()} × {sel.height()}"
            p.setFont(QFont(FONT, 9, QFont.Weight.Bold))
            fm = p.fontMetrics()
            tw = fm.horizontalAdvance(label) + 16
            ty = sel.top() - 26 if sel.top() > 34 else sel.bottom() + 8
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(4, 12, 22, 220)))
            p.drawRect(sel.left(), ty, tw, 20)
            p.setPen(QPen(QColor(C_CYAN), 1))
            p.drawText(sel.left() + 8, ty + 14, label)
        elif self._mouse.x() >= 0:
            # Réticule avant sélection
            p.setPen(QPen(with_alpha(QColor(C_CYAN), 70), 1))
            p.drawLine(0, self._mouse.y(), w, self._mouse.y())
            p.drawLine(self._mouse.x(), 0, self._mouse.x(), h)

        # Bandeau d'instructions
        msg = "VISION CIBLÉE — SÉLECTIONNEZ UNE ZONE  ·  ÉCHAP POUR ANNULER"
        p.setFont(QFont(FONT, 9, QFont.Weight.Bold))
        fm = p.fontMetrics()
        bw = fm.horizontalAdvance(msg) + 40
        bx = (w - bw) // 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(4, 12, 22, 235)))
        p.drawRect(bx, 18, bw, 30)
        p.setPen(QPen(with_alpha(QColor(C_CYAN), 200), 1))
        p.drawRect(bx, 18, bw, 30)
        p.drawText(bx + 20, 38, msg)
        p.end()

    def _selection_rect(self) -> QRect | None:
        if self._origin is None or self._current is None:
            return None
        return QRect(self._origin, self._current).normalized()

    # ── Interactions ─────────────────────────────────────────────────────────
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._origin = e.pos()
            self._current = e.pos()
            self.update()

    def mouseMoveEvent(self, e):
        self._mouse = e.pos()
        if self._origin is not None:
            self._current = e.pos()
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        sel = self._selection_rect()
        if sel is None or sel.width() < _MIN_SIZE or sel.height() < _MIN_SIZE:
            # Clic raté : on repart en attente de sélection
            self._origin = None
            self._current = None
            self.update()
            return
        self._finish(sel)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self._cancel()

    # ── Résultat ─────────────────────────────────────────────────────────────
    def _finish(self, sel: QRect):
        src = QRect(int(sel.x() * self._scale), int(sel.y() * self._scale),
                    int(sel.width() * self._scale), int(sel.height() * self._scale))
        img = self._shot.copy(src).toImage()

        if img.width() > _MAX_SEND_WIDTH:
            img = img.scaledToWidth(_MAX_SEND_WIDTH,
                                    Qt.TransformationMode.SmoothTransformation)

        # PNG pour les petites zones (texte net), JPEG au-delà (poids)
        use_png = img.width() * img.height() <= 600_000
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        if use_png:
            img.save(buf, "PNG")
            media = "image/png"
        else:
            img.save(buf, "JPEG", 85)
            media = "image/jpeg"
        b64 = base64.b64encode(bytes(buf.data())).decode("ascii")

        self._holder["result"] = {
            "image_b64": b64,
            "media_type": media,
            "w": sel.width(),
            "h": sel.height(),
        }
        self._close_and_notify()

    def _cancel(self):
        self._holder["result"] = None
        self._close_and_notify()

    def _close_and_notify(self):
        self._holder["event"].set()
        if self._restore_hud:
            try:
                from agents.desktop.ui.hud import overlay
                overlay.show(0)
            except Exception:
                pass
        self.close()
        self.deleteLater()

    def closeEvent(self, e):
        if not self._holder["event"].is_set():
            self._holder["result"] = None
            self._holder["event"].set()
        e.accept()


# ── API pour les threads de travail ──────────────────────────────────────────
def open_selector() -> dict | None:
    if _bridge is None:
        print("[Snip] non initialisé")
        return None
    holder = {"result": None, "event": threading.Event(), "window": None}
    _bridge.do_open.emit(holder)
    return holder


def wait_selector(holder: dict | None, timeout: float = 90) -> dict | None:
    """Attend la sélection. Retourne {image_b64, media_type, w, h} ou None."""
    if holder is None:
        return None
    holder["event"].wait(timeout=timeout)
    return holder.get("result")

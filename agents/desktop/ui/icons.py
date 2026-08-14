"""Icônes vectorielles du HUD — tout est dessiné au QPainter, zéro image.

- IconButton : bouton carré avec pictogramme vectoriel (envoi, cible, pause,
  micro, épingle, fermeture…), états hover/pressed/actif.
- reactor_pixmap : l'arc reactor en icône (tray, barre des tâches, .ico).
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import (
    QBrush, QColor, QCursor, QIcon, QPainter, QPainterPath, QPen, QPixmap,
    QPolygonF, QRadialGradient,
)
from PyQt6.QtWidgets import QPushButton

from agents.desktop.ui.theme import C_BG2, C_CYAN, C_WHITE, with_alpha


# ── Bouton à pictogramme vectoriel ────────────────────────────────────────────
class IconButton(QPushButton):
    """Bouton 30×30 dont l'icône est dessinée à la main dans la couleur donnée.

    kinds : send, target, pause, play, mic, mic_off, pin, pin_on, close
    """

    def __init__(self, kind: str, color: QColor, tip: str = "",
                 size: int = 30, frameless: bool = False, parent=None):
        super().__init__(parent)
        self._kind = kind
        self._color = QColor(color)
        self._frameless = frameless
        self.setFixedSize(size, size)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setToolTip(tip)
        self.setStyleSheet("background: transparent; border: none;")

    def set_kind(self, kind: str) -> None:
        if kind != self._kind:
            self._kind = kind
            self.update()

    def set_color(self, color: QColor) -> None:
        self._color = QColor(color)
        self.update()

    # ── Rendu ────────────────────────────────────────────────────────────────
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = h = min(self.width(), self.height())
        col = QColor(self._color)
        hover = self.underMouse()
        pressed = self.isDown()

        if not self._frameless:
            # Fond + cadre à coin coupé (haut-droite)
            cut = 7
            path = QPainterPath()
            path.moveTo(1, 1)
            path.lineTo(w - cut, 1)
            path.lineTo(w - 1, cut)
            path.lineTo(w - 1, h - 1)
            path.lineTo(1, h - 1)
            path.closeSubpath()
            bg = QColor(C_BG2)
            bg.setAlpha(235 if pressed else 210)
            if hover:
                bg = QColor(13, 34, 52, 235)
            p.setPen(QPen(with_alpha(col, 220 if hover else 120), 1))
            p.setBrush(QBrush(bg))
            p.drawPath(path)
            if hover:
                p.setPen(QPen(with_alpha(col, 60), 3))
                p.drawPath(path)
        elif hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(with_alpha(col, 26)))
            p.drawEllipse(QPointF(w / 2, h / 2), w / 2 - 2, h / 2 - 2)

        icon_col = with_alpha(col, 255 if hover else 215)
        pen = QPen(icon_col, 1.7)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        s = w / 30.0   # facteur d'échelle (design de référence : 30 px)

        def P(x, y):
            return QPointF(x * s, y * s)

        k = self._kind
        if k == "send":
            # Avion en papier
            poly = QPolygonF([P(7, 23), P(24, 15), P(7, 7), P(11, 14.6), P(7, 23)])
            p.drawPolyline(poly)
            p.drawLine(P(11, 14.6), P(18, 15))
        elif k == "target":
            p.drawEllipse(QPointF(15 * s, 15 * s), 6.4 * s, 6.4 * s)
            for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
                p.drawLine(P(15 + dx * 8.6, 15 + dy * 8.6), P(15 + dx * 12, 15 + dy * 12))
            p.setBrush(QBrush(icon_col))
            p.drawEllipse(QPointF(15 * s, 15 * s), 1.7 * s, 1.7 * s)
        elif k == "pause":
            p.setBrush(QBrush(icon_col))
            p.drawRect(QRectF(10.4 * s, 9 * s, 3.2 * s, 12 * s))
            p.drawRect(QRectF(16.4 * s, 9 * s, 3.2 * s, 12 * s))
        elif k == "play":
            p.setBrush(QBrush(icon_col))
            p.drawPolygon(QPolygonF([P(11, 8.5), P(22.5, 15), P(11, 21.5)]))
        elif k in ("mic", "mic_off"):
            # Capsule
            p.drawRoundedRect(QRectF(12.1 * s, 6.5 * s, 5.8 * s, 10 * s), 2.9 * s, 2.9 * s)
            # Arceau
            arc = QRectF(9.5 * s, 8.5 * s, 11 * s, 11.4 * s)
            p.drawArc(arc, 200 * 16, 140 * 16)
            # Pied
            p.drawLine(P(15, 19.9), P(15, 23.4))
            p.drawLine(P(11.4, 23.4), P(18.6, 23.4))
            if k == "mic_off":
                slash = QPen(QColor(255, 77, 77, 240), 2.0)
                slash.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(slash)
                p.drawLine(P(8.5, 24), P(21.5, 6))
        elif k in ("pin", "pin_on"):
            if k == "pin_on":
                p.setBrush(QBrush(icon_col))
            p.drawEllipse(QPointF(15 * s, 12 * s), 4.6 * s, 4.6 * s)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawLine(P(15, 16.6), P(15, 23.5))
        elif k == "close":
            p.drawLine(P(9.5, 9.5), P(20.5, 20.5))
            p.drawLine(P(20.5, 9.5), P(9.5, 20.5))
        p.end()


# ── Icône application : l'arc reactor ────────────────────────────────────────
def reactor_pixmap(size: int, core: QColor | None = None,
                   badge: bool = True) -> QPixmap:
    """Arc reactor en pixmap. `badge=True` ajoute un disque sombre de fond
    (lisibilité barre des tâches / tray), `core` teinte le noyau (état)."""
    core = QColor(core) if core else QColor(C_CYAN)
    pm = QPixmap(size, size)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    c = size / 2
    u = size / 100.0   # unités relatives (design de référence : 100 px)

    if badge:
        p.setPen(QPen(with_alpha(QColor(C_CYAN), 200), max(1.0, 2.2 * u)))
        p.setBrush(QBrush(QColor(5, 13, 24)))
        p.drawEllipse(QPointF(c, c), 47 * u, 47 * u)

    # Anneau d'enceinte
    p.setPen(QPen(with_alpha(QColor(C_CYAN), 235), max(1.0, 2.4 * u)))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(QPointF(c, c), 38 * u, 38 * u)

    # 10 bobines
    coil_rect = QRectF(c - 30 * u, c - 30 * u, 60 * u, 60 * u)
    coil_pen = QPen(with_alpha(QColor(C_CYAN), 255), max(1.5, 9 * u))
    coil_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    p.setPen(coil_pen)
    for k in range(10):
        p.drawArc(coil_rect, int((k * 36 + 7) * 16), int(22 * 16))

    # Noyau
    grad = QRadialGradient(QPointF(c, c), 20 * u)
    grad.setColorAt(0, with_alpha(QColor(C_WHITE), 255))
    grad.setColorAt(0.5, with_alpha(core, 230))
    grad.setColorAt(1, with_alpha(core, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(grad))
    p.drawEllipse(QPointF(c, c), 20 * u, 20 * u)
    p.end()
    return pm


def app_icon() -> QIcon:
    """Icône multi-résolutions pour la fenêtre et la barre des tâches."""
    icon = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(reactor_pixmap(s))
    return icon


def export_ico(path) -> bool:
    """Exporte assets/jarvis.ico (pour les raccourcis Windows). Best-effort."""
    try:
        import io
        from PIL import Image
        frames = []
        for s in (16, 24, 32, 48, 64, 128, 256):
            buf = QBuffer_bytes(reactor_pixmap(s))
            frames.append(Image.open(io.BytesIO(buf)))
        frames[-1].save(str(path), format="ICO",
                        sizes=[(f.width, f.height) for f in frames],
                        append_images=frames[:-1])
        return True
    except Exception as e:
        print(f"[Icône] export .ico impossible : {e}")
        return False


def QBuffer_bytes(pm: QPixmap) -> bytes:
    from PyQt6.QtCore import QBuffer, QIODevice
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pm.save(buf, "PNG")
    return bytes(buf.data())

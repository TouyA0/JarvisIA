"""Widgets custom du HUD : arc reactor, onde audio, diagnostics, conversation."""
from __future__ import annotations

import math
import random
import time
from collections import deque

from PyQt6.QtCore import Qt, QPointF, QRectF, QTimer
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QLinearGradient, QPainter, QPen, QPolygonF,
    QRadialGradient,
)
from PyQt6.QtWidgets import (
    QLabel, QScrollArea, QVBoxLayout, QWidget, QSizePolicy,
)

from agents.desktop.ui import theme
from agents.desktop.ui.theme import (
    C_CYAN, C_GOLD, C_RED, C_TEXT, C_TEXT_DIM, C_TEXT_FAINT, C_USER, C_WHITE,
    FONT, STATE_COLORS, dim, hexa, mix, rgba_css, with_alpha,
)


def _ease_out(x: float) -> float:
    return 1 - (1 - min(max(x, 0.0), 1.0)) ** 3


# ── Cadre de panneau chanfreiné (style Stark Industries) ─────────────────────
class PanelFrame(QWidget):
    """Panneau translucide à coins coupés avec onglet de titre et équerre.

    Héberge un widget de contenu ; la couleur d'accent suit l'état de Jarvis
    (changement instantané — seuls les éléments animés interpolent).
    """
    CUT = 12          # taille du chanfrein
    TITLE_H = 22

    def __init__(self, title: str, content: QWidget, parent=None,
                 fixed_width: int | None = None):
        super().__init__(parent)
        self._title = title
        self._state = "idle"
        if fixed_width:
            self.setFixedWidth(fixed_width)
        from PyQt6.QtWidgets import QVBoxLayout
        lay = QVBoxLayout(self)
        lay.setContentsMargins(9, self.TITLE_H + 6, 9, 9)
        lay.addWidget(content)
        content.setStyleSheet(getattr(content, "styleSheet", lambda: "")() or
                              "background: transparent;")

    def set_state(self, s: str) -> None:
        if s != self._state:
            self._state = s
            self.update()

    def paintEvent(self, _):
        from PyQt6.QtGui import QPainterPath
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        col = STATE_COLORS.get(self._state, C_CYAN)
        cut = self.CUT

        # Corps chanfreiné (coins coupés en haut-droite et bas-gauche)
        path = QPainterPath()
        path.moveTo(0, 0)
        path.lineTo(w - cut, 0)
        path.lineTo(w - 1, cut)
        path.lineTo(w - 1, h - 1)
        path.lineTo(cut, h - 1)
        path.lineTo(0, h - cut)
        path.closeSubpath()

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(7, 19, 34, 150)))
        p.drawPath(path)
        p.setPen(QPen(with_alpha(col, 65), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

        # Onglet de titre (parallélogramme)
        fm_font = QFont(FONT, 7, QFont.Weight.Bold)
        p.setFont(fm_font)
        tw = p.fontMetrics().horizontalAdvance(self._title) + 26
        tab = QPainterPath()
        tab.moveTo(0, 0)
        tab.lineTo(tw, 0)
        tab.lineTo(tw - 9, self.TITLE_H)
        tab.lineTo(0, self.TITLE_H)
        tab.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(with_alpha(col, 30)))
        p.drawPath(tab)
        p.setPen(QPen(with_alpha(col, 90), 1))
        p.drawLine(0, self.TITLE_H, w - 1, self.TITLE_H)

        p.setPen(QPen(with_alpha(col, 230), 1))
        p.drawText(10, 15, self._title)

        # Équerre décorative bas-droite + tick haut-gauche
        p.setPen(QPen(with_alpha(col, 150), 2))
        p.drawLine(w - 2, h - 16, w - 2, h - 2)
        p.drawLine(w - 16, h - 2, w - 2, h - 2)
        p.setPen(QPen(with_alpha(col, 150), 2))
        p.drawLine(1, 1, 1, 12)

        p.end()


# ── Emblème du header ─────────────────────────────────────────────────────────
class EmblemCanvas(QWidget):
    """Petit réacteur hexagonal pulsant à gauche du titre."""
    S = 26

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.S, self.S)
        self._phase = 0.0
        self._col = QColor(C_CYAN)

    def tick(self, ph: float, col: QColor) -> None:
        self._phase = ph
        self._col = col
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx = cy = self.S / 2
        col = self._col
        pulse = (math.sin(self._phase * 1.1) + 1) / 2

        # Hexagone externe rotatif
        p.setPen(QPen(with_alpha(col, 190), 1.4))
        pts = []
        for k in range(6):
            a = self._phase * 0.25 + k * math.pi / 3
            pts.append(QPointF(cx + math.cos(a) * 11, cy + math.sin(a) * 11))
        for k in range(6):
            p.drawLine(pts[k], pts[(k + 1) % 6])

        # Cœur
        core = QRadialGradient(QPointF(cx, cy), 7)
        core.setColorAt(0, with_alpha(C_WHITE, int(150 + pulse * 100)))
        core.setColorAt(0.6, with_alpha(col, 190))
        core.setColorAt(1, with_alpha(col, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(core))
        p.drawEllipse(QPointF(cx, cy), 7, 7)
        p.end()


# ── Arc Reactor ───────────────────────────────────────────────────────────────
class ReactorCanvas(QWidget):
    """Réacteur central : anneaux rotatifs, graduations, barres audio radiales.

    Toute l'animation dépend de trois entrées : l'état, la phase (temps) et le
    niveau audio réel (micro quand Jarvis écoute, voix quand il parle).
    """
    SIZE = 210
    N_BARS = 48

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.SIZE, self.SIZE)
        self._state = "idle"
        self._phase = 0.0
        self._level = 0.0          # niveau lissé affiché
        self._level_raw = 0.0      # dernière mesure reçue
        self._boot_t0 = time.time()
        self._bars = [0.0] * self.N_BARS
        self._col = QColor(STATE_COLORS["idle"])

    def set_state(self, s: str) -> None:
        self._state = s

    def set_level(self, lvl: float) -> None:
        self._level_raw = min(1.0, max(0.0, lvl))

    def restart_boot(self) -> None:
        self._boot_t0 = time.time()

    def tick(self, ph: float) -> None:
        self._phase = ph
        # Transition de couleur fluide entre états
        self._col = mix(self._col, QColor(STATE_COLORS.get(self._state, C_CYAN)), 0.14)
        # Attaque rapide, retombée douce — rend la visu « vivante »
        if self._level_raw > self._level:
            self._level = self._level * 0.4 + self._level_raw * 0.6
        else:
            self._level = self._level * 0.88 + self._level_raw * 0.12
        self.update()

    # Progression du boot [0..1] sur 1.6 s
    def _boot(self) -> float:
        return _ease_out((time.time() - self._boot_t0) / 1.6)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        col = self._col
        ph = self._phase
        boot = self._boot()
        pulse = (math.sin(ph * 0.9) + 1) / 2
        cx = cy = self.SIZE / 2

        R_TICKS = 100 * boot   # anneau de graduations (le plus externe)
        R_BARS = 72 * boot     # rayon de base des barres audio (longueur max 24)
        R_ARC1, R_ARC2 = 64 * boot, 55 * boot
        R_SWEEP = 59 * boot    # rayon du balayage radar

        # ── Barres audio radiales (réagissent au niveau réel) ────────────────
        lvl = self._level
        active = self._state in ("listening", "speaking")
        for i in range(self.N_BARS):
            ang = i * 2 * math.pi / self.N_BARS - math.pi / 2
            if active:
                wob = abs(math.sin(ph * 2.0 + i * 1.7)) * 0.55 + 0.45
                length = 2 + lvl * 22 * wob
            elif self._state == "processing":
                length = 2 + abs(math.sin(ph * 2.6 + i * 0.55)) * 7
            else:
                length = 1.5 + abs(math.sin(ph * 0.4 + i * 0.4)) * 2.5
            self._bars[i] = self._bars[i] * 0.55 + length * 0.45
            length = self._bars[i]
            x1 = cx + math.cos(ang) * R_BARS
            y1 = cy + math.sin(ang) * R_BARS
            x2 = cx + math.cos(ang) * (R_BARS + length)
            y2 = cy + math.sin(ang) * (R_BARS + length)
            alpha = int(50 + min(1.0, length / 22) * 190)
            p.setPen(QPen(with_alpha(col, alpha), 2))
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # ── Anneau de graduations (60 ticks, majeur tous les 5) ──────────────
        for i in range(60):
            ang = i * math.pi / 30 - math.pi / 2
            major = i % 5 == 0
            r_in = R_TICKS - (7 if major else 3)
            alpha = 150 if major else 60
            p.setPen(QPen(with_alpha(col, int(alpha * boot)), 1.6 if major else 1))
            p.drawLine(
                QPointF(cx + math.cos(ang) * r_in, cy + math.sin(ang) * r_in),
                QPointF(cx + math.cos(ang) * R_TICKS, cy + math.sin(ang) * R_TICKS),
            )

        # Diamants cardinaux (N-E-S-O) sur l'anneau de graduations
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(with_alpha(col, int(210 * boot))))
        for k in range(4):
            a = k * math.pi / 2
            dx = cx + math.cos(a) * (R_TICKS - 4)
            dy = cy + math.sin(a) * (R_TICKS - 4)
            p.drawPolygon(QPolygonF([
                QPointF(dx, dy - 3.2), QPointF(dx + 3.2, dy),
                QPointF(dx, dy + 3.2), QPointF(dx - 3.2, dy),
            ]))

        # ── Arcs segmentés contrarotatifs ────────────────────────────────────
        def seg_arc(radius, width, speed, spans, alpha):
            rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)
            base = math.degrees(ph * speed) % 360
            pen = QPen(with_alpha(col, int(alpha * boot)), width)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            p.setPen(pen)
            for start, span in spans:
                p.drawArc(rect, int((base + start) * 16), int(span * 16))

        seg_arc(R_ARC1, 2.5, +0.55, [(0, 70), (110, 40), (180, 80), (290, 30)], 200)
        seg_arc(R_ARC2, 1.2, -0.85, [(20, 100), (150, 60), (250, 70)], 110)

        # Points orbitaux accrochés aux départs des segments de l'arc externe
        base1 = math.degrees(ph * 0.55) % 360
        p.setPen(Qt.PenStyle.NoPen)
        for start in (0, 110, 180, 290):
            a = math.radians(base1 + start)
            # drawArc compte en antihoraire avec y écran inversé
            dx = cx + math.cos(a) * R_ARC1
            dy = cy - math.sin(a) * R_ARC1
            p.setBrush(QBrush(with_alpha(col, int(230 * boot))))
            p.drawEllipse(QPointF(dx, dy), 2.6, 2.6)
            p.setBrush(QBrush(with_alpha(C_WHITE, int(120 * boot))))
            p.drawEllipse(QPointF(dx, dy), 1.1, 1.1)

        # Balayage radar : traînée dégradée entre les deux arcs
        if boot > 0.2:
            sweep_rect = QRectF(cx - R_SWEEP, cy - R_SWEEP, R_SWEEP * 2, R_SWEEP * 2)
            lead = math.degrees(-ph * 0.9) % 360
            for k in range(16):
                alpha = int(80 * (1 - k / 16) * boot)
                if alpha <= 0:
                    continue
                pen = QPen(with_alpha(col, alpha), max(1.0, 7 * boot))
                pen.setCapStyle(Qt.PenCapStyle.FlatCap)
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawArc(sweep_rect, int((lead + k * 4) * 16), int(4 * 16))

        # ── Halo ─────────────────────────────────────────────────────────────
        glow_r = 44 + pulse * 5 + lvl * 8
        for r in range(int(glow_r) + 10, int(glow_r) - 6, -3):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(with_alpha(col, int((4 + pulse * 7) * boot))))
            p.drawEllipse(QPointF(cx, cy), r, r)

        # ── Anneau de charge : se remplit avec le niveau audio (270°) ────────
        ring_r = 46 * boot
        ring_rect = QRectF(cx - ring_r, cy - ring_r, ring_r * 2, ring_r * 2)
        base_pen = QPen(with_alpha(col, int(45 * boot)), 3)
        base_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(base_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(ring_rect, -45 * 16, 270 * 16)
        if lvl > 0.02:
            fill_pen = QPen(with_alpha(C_WHITE, int(190 * boot)), 3)
            fill_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            p.setPen(fill_pen)
            p.drawArc(ring_rect, -45 * 16, int(270 * min(1.0, lvl) * 16))

        # ── Cœur arc reactor : bobines segmentées + noyau ────────────────────
        # Anneau d'enceinte des bobines
        p.setPen(QPen(with_alpha(col, int(180 * boot)), 1.4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), 41 * boot, 41 * boot)

        # 10 bobines statiques — la signature visuelle de l'arc reactor
        coil_rect = QRectF(cx - 35 * boot, cy - 35 * boot, 70 * boot, 70 * boot)
        coil_pen = QPen(with_alpha(col, int((170 + pulse * 60) * boot)),
                        max(1.0, 9 * boot))
        coil_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        p.setPen(coil_pen)
        for k in range(10):
            p.drawArc(coil_rect, int((k * 36 + 7) * 16), int(22 * 16))

        # Anneau interne
        p.setPen(QPen(with_alpha(col, int(110 * boot)), 1))
        p.drawEllipse(QPointF(cx, cy), 27 * boot, 27 * boot)

        # Triangle Mark VII en rotation lente, discret sous le noyau
        tri_ang = ph * 0.15
        pts = []
        for k in range(3):
            a = tri_ang + k * 2 * math.pi / 3 - math.pi / 2
            pts.append(QPointF(cx + math.cos(a) * 19 * boot, cy + math.sin(a) * 19 * boot))
        p.setPen(QPen(with_alpha(col, int(85 * boot)), 1.2))
        for k in range(3):
            p.drawLine(pts[k], pts[(k + 1) % 3])

        # Noyau lumineux (blanc chaud → couleur d'état), gonfle avec la voix
        core_r = 22 + lvl * 4
        core = QRadialGradient(QPointF(cx, cy), core_r)
        core.setColorAt(0, with_alpha(C_WHITE, int((200 + pulse * 55) * boot)))
        core.setColorAt(0.45, with_alpha(col, int(160 * boot)))
        core.setColorAt(1, with_alpha(col, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(core))
        p.drawEllipse(QPointF(cx, cy), core_r, core_r)

        # Éclat de lentille horizontal traversant le noyau
        if boot > 0.6:
            span = 34 + lvl * 10
            glint = QLinearGradient(cx - span, cy, cx + span, cy)
            glint.setColorAt(0, with_alpha(C_WHITE, 0))
            glint.setColorAt(0.5, with_alpha(C_WHITE, int(130 * boot)))
            glint.setColorAt(1, with_alpha(C_WHITE, 0))
            p.setPen(QPen(QBrush(glint), 1.2))
            p.drawLine(QPointF(cx - span, cy), QPointF(cx + span, cy))
            p.setPen(QPen(QBrush(glint), 0.7))
            p.drawLine(QPointF(cx - span * 0.6, cy - 2), QPointF(cx + span * 0.6, cy - 2))

        # Texte d'initialisation pendant le boot
        if boot < 1.0:
            p.setPen(QPen(with_alpha(col, int(200 * (1 - boot))), 1))
            p.setFont(QFont(FONT, 7))
            dots = "." * (int(time.time() * 4) % 4)
            p.drawText(self.rect().adjusted(0, 0, 0, -8),
                       Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
                       f"INITIALISATION{dots}")
        p.end()


# ── Onde audio horizontale ────────────────────────────────────────────────────
class WaveCanvas(QWidget):
    N = 56

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(46)
        self._state = "idle"
        self._phase = 0.0
        self._level = 0.0
        self._bars = [0.0] * self.N
        self._col = QColor(STATE_COLORS["idle"])

    def set_state(self, s): self._state = s
    def set_level(self, lvl): self._level = min(1.0, max(0.0, lvl))

    def tick(self, ph):
        self._phase = ph
        self._col = mix(self._col, QColor(STATE_COLORS.get(self._state, C_CYAN)), 0.14)
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        col = self._col
        ph, s, lvl = self._phase, self._state, self._level
        cy = h / 2
        n = self.N
        bw = max(2, (w - 8) // n - 1)
        gap = max(1, ((w - 8) - n * bw) // n)

        # Ligne médiane + graduations latérales (cadran d'oscilloscope)
        p.setPen(QPen(with_alpha(col, 40), 1))
        p.drawLine(4, int(cy), w - 4, int(cy))
        for gx in range(4, w - 4, max(20, (w - 8) // 24)):
            p.drawLine(gx, int(cy) - 2, gx, int(cy) + 2)

        for i in range(n):
            if s == "listening":
                t = abs(math.sin(ph * 1.8 + i * 0.5)) * (0.15 + lvl * 0.85) * (cy - 3)
                t *= random.uniform(0.5, 1.0)
            elif s == "speaking":
                center = n / 2
                gauss = math.exp(-((i - center) ** 2) / (2 * (n / 4.5) ** 2))
                t = abs(math.sin(ph * 2.4 + i * 0.33)) * gauss * (0.2 + lvl * 0.8) * (cy - 2)
            elif s == "processing":
                t = abs(math.sin(ph * 3.2 + i * 0.7)) * (cy - 4) * 0.55
            elif s == "error":
                t = abs(math.sin(ph * 4.2 + i * 0.5)) * (cy - 3) * random.uniform(0.4, 1.0)
            else:
                t = abs(math.sin(ph * 0.3 + i * 0.22)) * 2.5 + 1

            self._bars[i] = self._bars[i] * 0.5 + t * 0.5
            bh = max(1.5, self._bars[i])
            x = 4 + i * (bw + gap)

            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(with_alpha(col, int(120 + bh / cy * 120))))
            p.drawRect(int(x), int(cy - bh), bw, int(bh * 2))
            p.setBrush(QBrush(with_alpha(C_WHITE, int(bh / cy * 110))))
            p.drawRect(int(x), int(cy - bh), bw, 1)
        p.end()


# ── Panneau diagnostics (valeurs réelles) ────────────────────────────────────
class DiagPanel(QWidget):
    WIDTH = 190

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(self.WIDTH)
        self._state = "idle"
        self._d = {
            "cpu": 0, "mem": 0, "disk": 0, "net_up": 0, "net_dn": 0,
            "lat_ms": 0, "tokens": 0, "cost_usd": 0.0, "calls": 0,
            "uptime": "00:00:00", "links": {},
        }
        self._model = "—"
        # Historique ~2 min (échantillon toutes les 2 s) pour la sparkline
        self._hist_cpu: deque = deque(maxlen=60)
        self._hist_mem: deque = deque(maxlen=60)

    def set_state(self, s):
        self._state = s
        self.update()

    def set_model(self, m):
        self._model = m or "—"
        self.update()

    def update_data(self, data: dict):
        self._d.update(data)
        if "cpu" in data:
            self._hist_cpu.append(data["cpu"])
        if "mem" in data:
            self._hist_mem.append(data["mem"])
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        col = STATE_COLORS.get(self._state, C_CYAN)
        fn6 = QFont(FONT, 7)
        fn8 = QFont(FONT, 8)
        w, h = self.width(), self.height()
        d = self._d
        y = 6

        def section(title):
            nonlocal y
            p.setFont(fn6)
            p.setPen(QPen(with_alpha(col, 180), 1))
            p.drawText(10, y + 8, title)
            tw = p.fontMetrics().horizontalAdvance(title)
            p.setPen(QPen(with_alpha(col, 40), 1))
            p.drawLine(16 + tw, y + 5, w - 10, y + 5)
            y += 17

        def segbar(label, val, suffix="%", max_val=100, warn=70, crit=90):
            nonlocal y
            p.setFont(fn6)
            p.setPen(QPen(C_TEXT_DIM, 1))
            p.drawText(10, y + 8, label)
            vc = col if val < warn else (C_GOLD if val < crit else C_RED)
            p.setPen(QPen(vc, 1))
            txt = f"{val}{suffix}"
            p.drawText(w - 10 - p.fontMetrics().horizontalAdvance(txt), y + 8, txt)
            y += 12
            # Barre segmentée en blocs — lecture immédiate, très HUD
            bx, seg_w, gap = 10, 5, 2
            n = max(8, (w - 20) // (seg_w + gap))
            filled = round(n * min(val, max_val) / max_val)
            p.setPen(Qt.PenStyle.NoPen)
            for i in range(n):
                p.setBrush(QBrush(vc if i < filled
                                  else with_alpha(C_TEXT_FAINT, 85)))
                p.drawRect(bx + i * (seg_w + gap), y, seg_w, 4)
            y += 12

        def kv(k, v, vcol=None):
            nonlocal y
            p.setFont(fn6)
            p.setPen(QPen(C_TEXT_DIM, 1))
            p.drawText(10, y, k)
            p.setPen(QPen(vcol or C_TEXT, 1))
            p.setFont(fn8)
            txt = str(v)
            p.drawText(w - 10 - p.fontMetrics().horizontalAdvance(txt), y, txt)
            y += 14

        # ── Ressources machine ──
        section("▍RESSOURCES")
        segbar("CPU", d["cpu"])
        segbar("MEM", d["mem"])
        segbar("DISK", d["disk"])

        # Sparkline CPU (vif) + MEM (estompé) sur ~2 minutes
        if len(self._hist_cpu) >= 2:
            sx, sw_, sh_ = 10, w - 20, 26
            p.setPen(QPen(with_alpha(col, 35), 1))
            p.setBrush(QBrush(QColor(0, 0, 0, 60)))
            p.drawRect(sx, y, sw_, sh_)

            def curve(hist, color, alpha, width):
                pts = list(hist)
                if len(pts) < 2:
                    return
                step = sw_ / (len(pts) - 1)
                p.setPen(QPen(with_alpha(color, alpha), width))
                last = None
                for i, v in enumerate(pts):
                    px = sx + i * step
                    py = y + sh_ - 2 - (min(100, v) / 100) * (sh_ - 4)
                    if last:
                        p.drawLine(QPointF(last[0], last[1]), QPointF(px, py))
                    last = (px, py)

            curve(self._hist_mem, QColor(C_TEXT_DIM), 130, 1.0)
            curve(self._hist_cpu, QColor(col), 220, 1.3)
            p.setFont(fn6)
            p.setPen(QPen(with_alpha(C_TEXT_FAINT, 220), 1))
            p.drawText(sx + 4, y + 9, "CPU · 2 MIN")
            y += sh_ + 9

        # ── Session IA ──
        section("▍SESSION IA")
        lat = int(d["lat_ms"])
        lat_txt = f"{lat / 1000:.1f}s" if lat >= 1000 else f"{lat}ms"
        kv("LATENCE", lat_txt, C_GOLD if lat >= 2000 else None)
        kv("TOKENS", f"{d['tokens']:,}".replace(",", " "))
        kv("COÛT MOIS", f"{d['cost_usd'] * 0.92:.3f} €")
        kv("APPELS", d["calls"])
        p.setFont(fn6)
        p.setPen(QPen(C_TEXT_DIM, 1))
        p.drawText(10, y, "MODÈLE")
        model = self._model
        if len(model) > 17:
            model = model[:16] + "…"
        p.setPen(QPen(with_alpha(col, 220), 1))
        p.drawText(w - 10 - p.fontMetrics().horizontalAdvance(model), y, model)
        y += 18

        # ── Réseau et liaisons ──
        section("▍RÉSEAU · LIAISONS")
        kv("NET ↑ / ↓", f"{d['net_up']} / {d['net_dn']} ko/s")
        links = d.get("links", {})
        p.setFont(fn6)
        for name, label in (("speaches", "SPEACHES"), ("ollama", "OLLAMA"),
                            ("claude", "CLAUDE API")):
            ok = links.get(name)
            dot_col = theme.C_GREEN if ok else (C_RED if ok is False else C_TEXT_FAINT)
            p.setPen(QPen(dot_col, 1))
            p.drawText(10, y, "●")
            p.setPen(QPen(C_TEXT_DIM, 1))
            p.drawText(22, y, label)
            p.setPen(QPen(dot_col, 1))
            status = "ON" if ok else ("OFF" if ok is False else "--")
            p.drawText(w - 10 - p.fontMetrics().horizontalAdvance(status), y, status)
            y += 13

        # ── Uptime en pied de panneau ──
        y += 5
        p.setPen(QPen(with_alpha(col, 30), 1))
        p.drawLine(10, y, w - 10, y)
        y += 13
        p.setFont(fn6)
        p.setPen(QPen(C_TEXT_DIM, 1))
        p.drawText(10, y, "UPTIME")
        p.setPen(QPen(C_TEXT, 1))
        p.setFont(fn8)
        up = str(d["uptime"])
        p.drawText(w - 10 - p.fontMetrics().horizontalAdvance(up), y, up)

        p.end()


# ── Panneau conversation ──────────────────────────────────────────────────────
class ConvPanel(QScrollArea):
    """Journal des échanges en bulles : Monsieur en or, Jarvis en cyan.

    La bulle Jarvis courante est mise à jour en direct pendant le streaming,
    avec un curseur ▌ clignotant, puis figée avec le temps de réponse.
    """
    MAX_ENTRIES = 14

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(self.Shape.NoFrame)
        self.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { background: transparent; width: 5px; }"
            f"QScrollBar::handle:vertical {{ background: {rgba_css(C_CYAN, 0.30)};"
            " border-radius: 2px; min-height: 20px; }"
            "QScrollBar::add-line, QScrollBar::sub-line { height: 0; }"
            "QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }"
        )
        self._holder = QWidget()
        self._holder.setStyleSheet("background: transparent;")
        self._vbox = QVBoxLayout(self._holder)
        self._vbox.setContentsMargins(2, 2, 6, 2)
        self._vbox.setSpacing(7)
        self._vbox.addStretch()
        self.setWidget(self._holder)
        self._current_jarvis: QLabel | None = None
        # Contenu de la bulle en cours de streaming (pour re-rendu du curseur)
        self._cur = {"text": "", "badge": "", "tag": "", "time": ""}
        self._cursor_on = False

    # ── Fabrique de bulles ───────────────────────────────────────────────────
    def _make_label(self, html: str, accent: QColor | None = None,
                    fill: bool = True) -> QLabel:
        lbl = QLabel(html)
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.TextFormat.RichText)
        lbl.setFont(QFont(FONT, 8))
        if accent is not None:
            lbl.setStyleSheet(
                f"background: {rgba_css(accent, 0.05) if fill else 'transparent'};"
                f" border-left: 2px solid {rgba_css(accent, 0.55)};"
                " padding: 5px 7px 5px 8px;")
        else:
            lbl.setStyleSheet("background: transparent; padding: 1px 2px;")
        lbl.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        return lbl

    def _append(self, lbl: QLabel) -> None:
        self._vbox.insertWidget(self._vbox.count() - 1, lbl)
        while self._vbox.count() - 1 > self.MAX_ENTRIES:
            item = self._vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        QTimer.singleShot(30, self._scroll_bottom)

    def _scroll_bottom(self) -> None:
        sb = self.verticalScrollBar()
        sb.setValue(sb.maximum())

    @staticmethod
    def _esc(text: str) -> str:
        return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    @staticmethod
    def _now() -> str:
        return time.strftime("%H:%M")

    # ── Messages ─────────────────────────────────────────────────────────────
    def add_user(self, text: str) -> None:
        html = (f'<span style="color:{dim(C_USER)}; letter-spacing:1px;">◤ VOUS</span>'
                f' <span style="color:{hexa(C_TEXT_FAINT)};">· {self._now()}</span><br>'
                f'<span style="color:{hexa(C_USER)};">{self._esc(text)}</span>')
        self._append(self._make_label(html, accent=QColor(C_USER)))
        self._current_jarvis = None
        self._cur = {"text": "", "badge": "", "tag": "", "time": ""}

    def _jarvis_html(self) -> str:
        c = self._cur
        badge_html = ""
        if c["badge"] in theme.SOURCE_BADGES:
            sym, col = theme.SOURCE_BADGES[c["badge"]]
            badge_html = f'  <span style="color:{hexa(col)};">{sym}</span>'
        tag_html = (f'  <span style="color:{hexa(C_TEXT_FAINT)};">· {c["tag"]}</span>'
                    if c["tag"] else "")
        cursor = ('<span style="color:{0};">▌</span>'.format(hexa(theme.C_CYAN_HI))
                  if self._cursor_on else "")
        return (f'<span style="color:{dim(C_CYAN)}; letter-spacing:1px;">◢ JARVIS</span>'
                f' <span style="color:{hexa(C_TEXT_FAINT)};">· {c["time"]}</span>'
                f'{badge_html}{tag_html}<br>'
                f'<span style="color:{hexa(theme.C_CYAN_HI)};">'
                f'{self._esc(c["text"])}{cursor}</span>')

    def set_jarvis(self, text: str, badge: str = "") -> None:
        """Crée ou met à jour la bulle Jarvis courante (streaming)."""
        if self._current_jarvis is None:
            self._cur = {"text": text, "badge": badge, "tag": "",
                         "time": self._now()}
            self._cursor_on = True
            self._current_jarvis = self._make_label(
                self._jarvis_html(), accent=QColor(C_CYAN))
            self._append(self._current_jarvis)
        else:
            self._cur["text"] = text
            self._cur["badge"] = badge or self._cur["badge"]
            self._current_jarvis.setText(self._jarvis_html())
            QTimer.singleShot(30, self._scroll_bottom)

    def set_cursor_visible(self, on: bool) -> None:
        """Clignotement du curseur de streaming (piloté par le tick du HUD)."""
        if self._current_jarvis is not None and on != self._cursor_on:
            self._cursor_on = on
            self._current_jarvis.setText(self._jarvis_html())

    def finish_stream(self, tag: str = "") -> None:
        """Fige la bulle courante : curseur retiré, temps de réponse affiché."""
        if self._current_jarvis is not None:
            self._cursor_on = False
            if tag:
                self._cur["tag"] = tag
            self._current_jarvis.setText(self._jarvis_html())

    def add_system(self, text: str) -> None:
        body = "<br>".join(self._esc(line) for line in text.split("\n"))
        html = f'<span style="color:{hexa(C_TEXT_DIM)};">▸ {body}</span>'
        self._append(self._make_label(html, accent=None))


# ── Chevrons de statut animés ─────────────────────────────────────────────────
class StatusChevrons(QWidget):
    """Trois chevrons qui défilent de part et d'autre du statut central."""

    def __init__(self, mirrored: bool = False, parent=None):
        super().__init__(parent)
        self.setFixedSize(34, 16)
        self._mirrored = mirrored
        self._phase = 0.0
        self._col = QColor(STATE_COLORS["idle"])
        self._active = False

    def tick(self, ph: float, col: QColor, active: bool) -> None:
        self._phase = ph
        self._col = col
        self._active = active
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        h = self.height()
        cy = h / 2
        for i in range(3):
            if self._active:
                wave = (math.sin(self._phase * 2.6 - i * 0.9) + 1) / 2
                alpha = int(50 + wave * 190)
            else:
                alpha = 45
            pen = QPen(with_alpha(self._col, alpha), 1.8)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            x = 5 + i * 10
            if self._mirrored:
                x = self.width() - x
                p.drawLine(QPointF(x, cy - 5), QPointF(x - 5, cy))
                p.drawLine(QPointF(x - 5, cy), QPointF(x, cy + 5))
            else:
                p.drawLine(QPointF(x, cy - 5), QPointF(x + 5, cy))
                p.drawLine(QPointF(x + 5, cy), QPointF(x, cy + 5))
        p.end()

"""HUD principal J.A.R.V.I.S. — fenêtre flottante cinématique.

Architecture identique à la v1 : la façade JarvisOverlay expose des méthodes
thread-safe (signaux Qt) appelées depuis les threads de travail ; la fenêtre
vit sur le thread Qt principal.

Lancement autonome pour prévisualiser : python -m agents.desktop.ui.hud
"""
from __future__ import annotations

import json
import math
import os
import queue
import sys
import threading
import time

from PyQt6.QtCore import (
    Qt, QEasingCurve, QObject, QPoint, QPropertyAnimation, QTimer, pyqtSignal,
)
from PyQt6.QtGui import (
    QBrush, QColor, QCursor, QFont, QLinearGradient, QPainter, QPainterPath,
    QPen, QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QLineEdit, QMenu, QPushButton,
    QVBoxLayout, QWidget,
)

from agents.desktop import APP_VERSION, config
from agents.desktop.ui import theme
from agents.desktop.ui.theme import (
    C_BG, C_BG2, C_CYAN, C_GOLD, C_GRID, C_HEX, C_RED, C_TEXT, C_TEXT_DIM,
    C_TEXT_FAINT, C_WHITE, FONT, SOURCE_BADGES, STATE_COLORS, STATE_LABELS,
    hexa, mix, rgba_css, with_alpha,
)
from agents.desktop.ui.icons import IconButton, app_icon, reactor_pixmap
from agents.desktop.ui.widgets import (
    ConvPanel, DiagPanel, EmblemCanvas, PanelFrame, ReactorCanvas,
    StatusChevrons, WaveCanvas,
)

TOKEN_PAUSE = "__PAUSE__"
TOKEN_RESUME = "__RESUME__"
TOKEN_SNIP = "__SNIP__"      # déclenche la Vision ciblée (sélection de zone)


def _load_modes() -> list:
    try:
        with open(config.MODES_FILE, encoding="utf-8") as f:
            return json.load(f).get("modes", [])
    except Exception:
        return []


# ── Signaux inter-threads ─────────────────────────────────────────────────────
class _Signals(QObject):
    do_set_state = pyqtSignal(str)
    do_set_mode = pyqtSignal(str)
    do_set_transcript = pyqtSignal(str)
    do_set_response = pyqtSignal(str)
    do_set_source = pyqtSignal(str)
    do_set_cost = pyqtSignal(float, float, int)
    do_set_paused = pyqtSignal(bool)
    do_show = pyqtSignal(int)
    do_update_diag = pyqtSignal(dict)
    do_set_model_label = pyqtSignal(str)
    do_set_level = pyqtSignal(float)
    do_set_activity = pyqtSignal(str)
    do_set_weather = pyqtSignal(str)
    do_add_system_msg = pyqtSignal(str)
    do_focus_input = pyqtSignal()
    do_finish_response = pyqtSignal(str)
    do_set_timer_chip = pyqtSignal(str)


# ── Fenêtre principale ────────────────────────────────────────────────────────
class _JarvisWindow(QWidget):
    W = 960
    H = 560
    HIDE_IDLE_MS = 6_000
    HIDE_TRAY_MS = 15_000
    PEEK_PX = 16          # bande visible quand la fenêtre est repliée au bord

    def __init__(self, signals: _Signals, input_queue: queue.Queue, overlay_ref):
        super().__init__()
        self._sig = signals
        self._input_queue = input_queue
        self._overlay_ref = overlay_ref
        self._state = "idle"
        self._mode_name = "Normal"
        self._pinned = False
        self._mouse_inside = False
        self._muted = False
        self._paused = False
        self._edge_hidden = False
        self._anim_phase = 0.0
        self._last_cost = 0.0
        self._month_cost = 0.0
        self._month_calls = 0
        self._cur_source = None
        self._drag_offset = None
        self._activity = ""
        self._weather = ""
        self._bg_cache: QPixmap | None = None
        self._col_cur = QColor(STATE_COLORS["idle"])   # couleur de chrome lissée
        self._setup_window()
        self._build_ui()
        self._connect_signals()
        self._start_timers()

    # ── Fenêtre ──────────────────────────────────────────────────────────────
    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.W, self.H)
        # Silhouette octogonale (coins coupés) — signature Stark
        cut = 14
        pth = QPainterPath()
        pth.moveTo(cut, 0)
        pth.lineTo(self.W - cut, 0)
        pth.lineTo(self.W, cut)
        pth.lineTo(self.W, self.H - cut)
        pth.lineTo(self.W - cut, self.H)
        pth.lineTo(cut, self.H)
        pth.lineTo(0, self.H - cut)
        pth.lineTo(0, cut)
        pth.closeSubpath()
        self._win_path = pth
        self._win_cut = cut
        scr = QApplication.primaryScreen().geometry()
        self._screen_w = scr.width()
        self._screen_h = scr.height()
        self._normal_x = scr.width() - self.W - 22
        self._normal_y = scr.height() // 2 - self.H // 2
        self.move(self._normal_x, self._normal_y)
        self.hide()
        self._slide = QPropertyAnimation(self, b"pos")
        self._slide.setDuration(320)
        self._slide.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._check_and_hide)

    # Fond statique (dégradé + hexagones + grille) rendu une seule fois
    def _render_background(self) -> QPixmap:
        pm = QPixmap(self.W, self.H)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        grad = QLinearGradient(0, 0, 0, self.H)
        grad.setColorAt(0, QColor(C_BG2))
        grad.setColorAt(0.5, QColor(C_BG))
        grad.setColorAt(1, QColor(4, 11, 20))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawPath(self._win_path)
        p.setClipPath(self._win_path)

        # Grille fine
        p.setPen(QPen(C_GRID, 1))
        for x in range(0, self.W, 44):
            p.drawLine(x, 0, x, self.H)
        for y in range(0, self.H, 44):
            p.drawLine(0, y, self.W, y)

        # Motif hexagonal discret
        p.setPen(QPen(C_HEX, 1))
        r = 26
        dx = r * 3
        dy = r * math.sin(math.pi / 3)
        for row in range(int(self.H / dy) + 2):
            for col in range(int(self.W / dx) + 2):
                cx = col * dx + (r * 1.5 if row % 2 else 0)
                cy = row * dy
                pts = []
                for k in range(6):
                    a = math.pi / 3 * k
                    pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
                for k in range(6):
                    x1, y1 = pts[k]
                    x2, y2 = pts[(k + 1) % 6]
                    p.drawLine(int(x1), int(y1), int(x2), int(y2))

        # Grands cercles décoratifs derrière le réacteur (profondeur HUD)
        from PyQt6.QtCore import QRectF
        deco_cx, deco_cy = self.W * 0.442, 168
        for radius, alpha in ((150, 13), (196, 9)):
            p.setPen(QPen(with_alpha(QColor(C_CYAN), alpha), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(deco_cx - radius, deco_cy - radius,
                                 radius * 2, radius * 2))
        # Graduations sur le cercle intermédiaire
        p.setPen(QPen(with_alpha(QColor(C_CYAN), 22), 1))
        for i in range(48):
            a = i * math.pi / 24
            x1 = deco_cx + math.cos(a) * 170
            y1 = deco_cy + math.sin(a) * 170
            x2 = deco_cx + math.cos(a) * 176
            y2 = deco_cy + math.sin(a) * 176
            p.drawLine(int(x1), int(y1), int(x2), int(y2))

        # Vignettage : assombrit doucement les bords pour recentrer l'œil
        from PyQt6.QtGui import QRadialGradient
        vig = QRadialGradient(self.W / 2, self.H * 0.45, self.W * 0.65)
        vig.setColorAt(0.0, QColor(0, 0, 0, 0))
        vig.setColorAt(0.72, QColor(0, 0, 0, 0))
        vig.setColorAt(1.0, QColor(0, 0, 0, 115))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(vig))
        p.drawPath(self._win_path)

        p.end()
        return pm

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        col = self._col_cur

        if self._bg_cache is None:
            self._bg_cache = self._render_background()
        p.drawPixmap(0, 0, self._bg_cache)

        # Ligne de balayage lente descendante (effet hologramme)
        scan_y = int((self._anim_phase * 9) % (h + 140)) - 70
        scan = QLinearGradient(0, scan_y, 0, scan_y + 70)
        scan.setColorAt(0, with_alpha(col, 0))
        scan.setColorAt(0.85, with_alpha(col, 14))
        scan.setColorAt(1, with_alpha(col, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(scan))
        p.drawRect(1, scan_y, w - 2, 70)

        # ── Bordure octogonale et accents de chanfrein ───────────────────────
        cut = self._win_cut
        p.setPen(QPen(with_alpha(col, 90), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(self._win_path)

        # Ligne top lumineuse avec dégradé (entre les deux chanfreins)
        top_grad = QLinearGradient(cut, 0, w - cut, 0)
        top_grad.setColorAt(0, with_alpha(col, 40))
        top_grad.setColorAt(0.5, with_alpha(col, 230))
        top_grad.setColorAt(1, with_alpha(col, 40))
        p.setPen(QPen(QBrush(top_grad), 2))
        p.drawLine(cut, 1, w - cut, 1)

        # Chanfreins soulignés + courtes extensions sur les arêtes adjacentes
        p.setPen(QPen(with_alpha(col, 255), 2))
        L = 20
        # haut-gauche
        p.drawLine(0, cut, cut, 0)
        p.drawLine(cut, 1, cut + L, 1)
        p.drawLine(1, cut, 1, cut + L)
        # haut-droite
        p.drawLine(w - cut, 0, w, cut)
        p.drawLine(w - cut - L, 1, w - cut, 1)
        p.drawLine(w - 2, cut, w - 2, cut + L)
        # bas-gauche
        p.drawLine(0, h - cut, cut, h)
        p.drawLine(cut, h - 2, cut + L, h - 2)
        p.drawLine(1, h - cut - L, 1, h - cut)
        # bas-droite
        p.drawLine(w - cut, h, w, h - cut)
        p.drawLine(w - cut - L, h - 2, w - cut, h - 2)
        p.drawLine(w - 2, h - cut - L, w - 2, h - cut)

        # Séparateurs horizontaux
        p.setPen(QPen(with_alpha(col, 35), 1))
        p.drawLine(0, 44, w, 44)
        p.drawLine(0, h - 76, w, h - 76)
        p.drawLine(0, h - 30, w, h - 30)

        # Bande « peek » quand replié au bord de l'écran
        if self._edge_hidden:
            strip = QLinearGradient(0, 0, self.PEEK_PX, 0)
            strip.setColorAt(0, with_alpha(col, 190))
            strip.setColorAt(1, with_alpha(col, 20))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(strip))
            p.drawRect(0, 0, self.PEEK_PX, h)
            p.setPen(QPen(QColor(C_BG), 1))
            p.setFont(QFont(FONT, 8, QFont.Weight.Bold))
            p.save()
            p.translate(11, h // 2 - 40)
            p.rotate(90)
            p.drawText(0, 0, "J.A.R.V.I.S.")
            p.restore()
            # Mini-réacteur en haut de la languette
            p.drawPixmap(2, 20, reactor_pixmap(12, core=col, badge=False))

        p.end()

    # ── Construction UI ──────────────────────────────────────────────────────
    def _label(self, text, size=8, color=None, bold=False, spacing=0):
        lbl = QLabel(text)
        lbl.setFont(QFont(FONT, size, QFont.Weight.Bold if bold else QFont.Weight.Normal))
        style = f"color:{color or hexa(C_TEXT_DIM)}; background:transparent;"
        if spacing:
            style += f" letter-spacing:{spacing}px;"
        lbl.setStyleSheet(style)
        return lbl

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ══ HEADER ════════════════════════════════════════════════════════════
        hdr = QHBoxLayout()
        hdr.setContentsMargins(14, 0, 10, 0)
        hdr.setSpacing(10)

        self._emblem = EmblemCanvas()
        hdr.addWidget(self._emblem)

        title = QLabel("J.A.R.V.I.S.")
        title.setFont(QFont(FONT, 15, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{hexa(C_CYAN)}; background:transparent; letter-spacing:4px;")
        hdr.addWidget(title)

        self._dot = QLabel("●")
        self._dot.setFont(QFont(FONT, 10))
        self._dot.setStyleSheet(f"color:{hexa(C_CYAN)}; background:transparent;")
        hdr.addWidget(self._dot)

        ver = self._label(f"MARK {APP_VERSION} · STARK OS", 7, hexa(C_TEXT_FAINT), spacing=2)
        hdr.addWidget(ver)

        hdr.addStretch()

        # Chip minuteur (compte à rebours du prochain échéancier)
        self._timer_lbl = QLabel("")
        self._timer_lbl.setFont(QFont(FONT, 8, QFont.Weight.Bold))
        self._timer_lbl.setStyleSheet(
            f"color:{hexa(C_GOLD)}; background:{rgba_css(C_BG2, 0.85)};"
            f" border:1px solid {rgba_css(C_GOLD, 0.4)}; border-radius:3px;"
            " padding:2px 8px; letter-spacing:1px;")
        self._timer_lbl.hide()
        hdr.addWidget(self._timer_lbl)

        # Chip météo
        self._weather_lbl = QLabel("")
        self._weather_lbl.setFont(QFont(FONT, 8))
        self._weather_lbl.setStyleSheet(
            f"color:{hexa(C_TEXT_DIM)}; background:{rgba_css(C_BG2, 0.85)};"
            f" border:1px solid {rgba_css(C_CYAN, 0.2)}; border-radius:3px;"
            " padding:2px 8px; letter-spacing:1px;")
        self._weather_lbl.hide()
        hdr.addWidget(self._weather_lbl)

        self._mode_btn = QPushButton("MODE NORMAL ▾")
        self._mode_btn.setFont(QFont(FONT, 8))
        self._mode_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._mode_btn.setStyleSheet(
            f"QPushButton {{ background:{rgba_css(C_BG2, 0.9)}; color:{hexa(C_TEXT_DIM)};"
            f" border:1px solid {rgba_css(C_CYAN, 0.25)}; border-radius:3px;"
            " padding:4px 12px; letter-spacing:1px; }"
            f"QPushButton:hover {{ color:{hexa(C_CYAN)}; border-color:{rgba_css(C_CYAN, 0.6)}; }}"
        )
        self._mode_btn.clicked.connect(self._show_mode_menu)
        hdr.addWidget(self._mode_btn)

        self._pin_btn = IconButton("pin", C_TEXT_DIM,
                                   "Épingler (ne jamais replier)",
                                   size=28, frameless=True)
        self._pin_btn.clicked.connect(self._toggle_pin)
        hdr.addWidget(self._pin_btn)

        close_btn = IconButton("close", C_RED, "Quitter Jarvis",
                               size=28, frameless=True)
        close_btn.clicked.connect(self._on_close)
        hdr.addWidget(close_btn)

        hdr_w = QWidget()
        hdr_w.setFixedHeight(44)
        hdr_w.setLayout(hdr)
        hdr_w.setStyleSheet("background:transparent;")
        root.addWidget(hdr_w)

        # ══ CORPS : diag | réacteur | conversation ════════════════════════════
        body = QHBoxLayout()
        body.setContentsMargins(8, 8, 10, 4)
        body.setSpacing(10)

        # ── Panneau gauche : diagnostics réels ──
        self._diag = DiagPanel()
        self._diag_frame = PanelFrame("◢ SYS.DIAGNOSTICS", self._diag, fixed_width=208)
        body.addWidget(self._diag_frame)

        # ── Panneau central : réacteur + statut + onde ──
        center = QVBoxLayout()
        center.setSpacing(2)

        reactor_row = QHBoxLayout()
        reactor_row.addStretch()
        self._reactor = ReactorCanvas()
        reactor_row.addWidget(self._reactor)
        reactor_row.addStretch()
        center.addLayout(reactor_row)

        # Ruban de statut : chevrons animés de part et d'autre
        status_row = QHBoxLayout()
        status_row.setSpacing(10)
        status_row.addStretch()
        self._chev_l = StatusChevrons(mirrored=True)
        status_row.addWidget(self._chev_l)
        self._status_main = QLabel("EN VEILLE")
        self._status_main.setFont(QFont(FONT, 13, QFont.Weight.Bold))
        self._status_main.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._status_main.setStyleSheet(
            f"color:{hexa(C_TEXT_DIM)}; background:transparent; letter-spacing:4px;")
        status_row.addWidget(self._status_main)
        self._chev_r = StatusChevrons(mirrored=False)
        status_row.addWidget(self._chev_r)
        status_row.addStretch()
        center.addLayout(status_row)

        self._status_sub = QLabel("// STANDBY")
        self._status_sub.setFont(QFont(FONT, 8))
        self._status_sub.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._status_sub.setStyleSheet(
            f"color:{hexa(C_TEXT_FAINT)}; background:transparent; letter-spacing:2px;")
        center.addWidget(self._status_sub)

        self._activity_lbl = QLabel("")
        self._activity_lbl.setFont(QFont(FONT, 8))
        self._activity_lbl.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._activity_lbl.setStyleSheet(
            f"color:{hexa(C_GOLD)}; background:transparent; letter-spacing:1px;")
        center.addWidget(self._activity_lbl)

        center.addStretch()
        self._wave = WaveCanvas()
        self._wave_frame = PanelFrame("◢ SPECTRE AUDIO", self._wave)
        center.addWidget(self._wave_frame)
        body.addLayout(center, 1)

        # ── Panneau droit : conversation ──
        self._conv = ConvPanel()
        self._conv_frame = PanelFrame("◢ TRANSMISSIONS", self._conv, fixed_width=316)
        body.addWidget(self._conv_frame)

        self._frames = (self._diag_frame, self._wave_frame, self._conv_frame)

        body_w = QWidget()
        body_w.setLayout(body)
        body_w.setStyleSheet("background:transparent;")
        root.addWidget(body_w, 1)

        # ══ BARRE DE SAISIE ═══════════════════════════════════════════════════
        ctrl_w = QWidget()
        ctrl_w.setFixedHeight(46)
        ctrl_w.setStyleSheet("background:transparent;")
        ctrl = QHBoxLayout(ctrl_w)
        ctrl.setContentsMargins(16, 6, 10, 6)
        ctrl.setSpacing(7)

        prompt = self._label("▸", 11, hexa(C_CYAN))
        ctrl.addWidget(prompt)

        self._entry = QLineEdit()
        self._entry.setFont(QFont(FONT, 9))
        self._entry.setPlaceholderText("Commander J.A.R.V.I.S. …")
        self._entry.setStyleSheet(
            f"QLineEdit {{ background:{rgba_css(QColor(3, 10, 18), 0.9)}; color:{hexa(theme.C_CYAN_HI)};"
            f" border:1px solid {rgba_css(C_CYAN, 0.2)}; border-radius:3px; padding:6px 10px; }}"
            f"QLineEdit:focus {{ border-color:{rgba_css(C_CYAN, 0.55)}; }}"
        )
        self._entry.returnPressed.connect(self._on_send)
        ctrl.addWidget(self._entry, 1)

        self._send_btn = IconButton("send", C_CYAN, "Envoyer")
        self._snip_btn = IconButton("target", C_GOLD,
                                    "Vision ciblée — capturer une zone (Ctrl+Alt+V)")
        self._pause_btn = IconButton("pause", C_TEXT_DIM, "Pause / Reprendre")
        self._mute_btn = IconButton("mic", C_CYAN, "Couper le micro (mode texte)")
        self._send_btn.clicked.connect(self._on_send)
        self._snip_btn.clicked.connect(lambda: self._input_queue.put(TOKEN_SNIP))
        self._pause_btn.clicked.connect(self._toggle_pause)
        self._mute_btn.clicked.connect(self._toggle_mute)
        ctrl.addWidget(self._send_btn)
        ctrl.addWidget(self._snip_btn)
        ctrl.addWidget(self._pause_btn)
        ctrl.addWidget(self._mute_btn)
        root.addWidget(ctrl_w)

        # ══ STATUS BAR ════════════════════════════════════════════════════════
        sbar_w = QWidget()
        sbar_w.setFixedHeight(30)
        sbar_w.setStyleSheet("background:transparent;")
        sbar = QHBoxLayout(sbar_w)
        sbar.setContentsMargins(16, 0, 16, 0)
        sbar.setSpacing(16)

        self._link_lbl = self._label("◈ LIAISON ACTIVE", 7, hexa(theme.C_GREEN))
        self._mic_lbl = self._label("MIC ON", 7)
        self._cost_lbl = self._label("", 7)
        self._badge_lbl = self._label("", 7)
        sbar.addWidget(self._link_lbl)
        sbar.addWidget(self._mic_lbl)
        sbar.addWidget(self._badge_lbl)
        sbar.addWidget(self._cost_lbl)
        sbar.addStretch()
        self._clock_lbl = self._label("", 8, hexa(C_TEXT_DIM))
        sbar.addWidget(self._clock_lbl)
        root.addWidget(sbar_w)

        ct = QTimer(self)
        ct.setInterval(1000)
        ct.timeout.connect(self._tick_clock)
        ct.start()
        self._tick_clock()

    def _tick_clock(self):
        days = ["LUN", "MAR", "MER", "JEU", "VEN", "SAM", "DIM"]
        now = time.localtime()
        self._clock_lbl.setText(
            f"{days[now.tm_wday]} {now.tm_mday:02d}.{now.tm_mon:02d}.{now.tm_year}"
            f"  ·  {time.strftime('%H:%M:%S')}_")

    # ── Animation ─────────────────────────────────────────────────────────────
    def _start_timers(self):
        t = QTimer(self)
        t.setInterval(28)
        t.timeout.connect(self._tick)
        t.start()

    def _tick(self):
        self._anim_phase += 0.14
        ph = self._anim_phase
        self._col_cur = mix(self._col_cur,
                            QColor(STATE_COLORS.get(self._state, C_CYAN)), 0.12)
        self._reactor.tick(ph)
        self._wave.tick(ph)
        self._emblem.tick(ph, self._col_cur)
        active = self._state not in ("idle",) and not self._paused
        self._chev_l.tick(ph, self._col_cur, active)
        self._chev_r.tick(ph, self._col_cur, active)

        # Curseur de streaming clignotant dans la conversation
        if self._state in ("processing", "speaking"):
            self._conv.set_cursor_visible(int(ph * 2.2) % 2 == 0)

        col = self._col_cur
        alpha = int(90 + ((math.sin(ph * 1.1) + 1) / 2) * 165)
        self._dot.setStyleSheet(
            f"color:rgba({col.red()},{col.green()},{col.blue()},{alpha});"
            " background:transparent;")
        self.update()

    # ── Drag (n'importe où sur le fond) ───────────────────────────────────────
    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = e.pos()

    def mouseMoveEvent(self, e):
        if self._drag_offset is not None:
            np_ = e.globalPosition().toPoint() - self._drag_offset
            self._normal_x = np_.x()
            self._normal_y = np_.y()
            self.move(np_)
            self._edge_hidden = False

    def mouseReleaseEvent(self, _):
        self._drag_offset = None

    # ── Repli au bord / survol ────────────────────────────────────────────────
    def enterEvent(self, _):
        self._mouse_inside = True
        self._hide_timer.stop()
        if self._edge_hidden:
            self._expand()

    def leaveEvent(self, _):
        self._mouse_inside = False
        if not self._pinned and self._state == "idle":
            self._schedule_hide(self.HIDE_IDLE_MS)

    def _schedule_hide(self, ms):
        self._hide_timer.stop()
        self._hide_timer.start(ms)

    def _check_and_hide(self):
        if not self._pinned and not self._mouse_inside:
            self._collapse()

    def _collapse(self):
        if self._edge_hidden:
            return
        self._edge_hidden = True
        self._animate_to(QPoint(self._screen_w - self.PEEK_PX, self.y()))

    def _expand(self):
        self._edge_hidden = False
        self._animate_to(QPoint(self._normal_x, self._normal_y))

    def _animate_to(self, target):
        self._slide.stop()
        self._slide.setStartValue(self.pos())
        self._slide.setEndValue(target)
        self._slide.start()

    def _on_show(self, ms):
        if not self.isVisible():
            self.show()
            self._reactor.restart_boot()
        if self._edge_hidden:
            self._expand()
        self._hide_timer.stop()
        if not self._pinned and ms > 0:
            self._schedule_hide(ms)

    def _on_close(self):
        ref = self._overlay_ref
        if ref and getattr(ref, "on_quit", None):
            try:
                ref.on_quit()
            except Exception:
                pass
        QApplication.quit()
        os._exit(0)

    def _toggle_pin(self):
        self._pinned = not self._pinned
        if self._pinned:
            self._hide_timer.stop()
            self._pin_btn.set_kind("pin_on")
            self._pin_btn.set_color(C_CYAN)
        else:
            self._pin_btn.set_kind("pin")
            self._pin_btn.set_color(C_TEXT_DIM)
            if self._state == "idle":
                self._schedule_hide(self.HIDE_IDLE_MS)

    def _toggle_pause(self):
        self._paused = not self._paused
        self._sync_pause()
        self._input_queue.put(TOKEN_PAUSE if self._paused else TOKEN_RESUME)

    def _on_set_paused(self, val):
        self._paused = val
        self._sync_pause()

    def _sync_pause(self):
        if self._paused:
            self._pause_btn.set_kind("play")
            self._pause_btn.set_color(C_GOLD)
            self._status_main.setText("EN PAUSE")
            self._status_main.setStyleSheet(
                f"color:{hexa(C_GOLD)}; background:transparent; letter-spacing:4px;")
            self._status_sub.setText("// PAUSED")
        else:
            self._pause_btn.set_kind("pause")
            self._pause_btn.set_color(C_TEXT_DIM)
            self._on_set_state(self._state)

    def _toggle_mute(self):
        self._muted = not self._muted
        if self._muted:
            self._mute_btn.set_kind("mic_off")
            self._mute_btn.set_color(C_RED)
            self._mic_lbl.setStyleSheet(f"color:{hexa(C_RED)}; background:transparent;")
            self._mic_lbl.setText("MIC OFF — MODE TEXTE")
        else:
            self._mute_btn.set_kind("mic")
            self._mute_btn.set_color(C_CYAN)
            self._mic_lbl.setStyleSheet(f"color:{hexa(C_TEXT_DIM)}; background:transparent;")
            self._mic_lbl.setText("MIC ON")

    def _show_mode_menu(self):
        modes = _load_modes()
        if not modes:
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background:{hexa(QColor(4, 11, 20))}; color:{hexa(theme.C_CYAN_HI)};"
            f" border:1px solid {rgba_css(C_CYAN, 0.25)};"
            f" font-family:{FONT}; font-size:9pt; padding:4px; }}"
            "QMenu::item { padding:7px 22px; letter-spacing:1px; }"
            f"QMenu::item:selected {{ background:#0a2035; color:{hexa(C_CYAN)}; }}"
        )
        for mode in modes:
            mid = mode["id"]
            mname = mode["name"].replace("Mode ", "")
            active = mname.lower() == self._mode_name.lower()
            action = menu.addAction(f"{'▸ ' if active else '  '}{mode['name'].upper()}")
            action.setData((mid, mname))
        pos = self._mode_btn.mapToGlobal(self._mode_btn.rect().bottomLeft())
        chosen = menu.exec(pos)
        if chosen:
            mid, mname = chosen.data()
            self._on_set_mode(mname)
            cb = self._overlay_ref.on_mode_change if self._overlay_ref else None
            if cb:
                threading.Thread(target=cb, args=(mid,), daemon=True).start()

    def _on_send(self):
        text = self._entry.text().strip()
        if not text:
            return
        self._entry.clear()
        self._input_queue.put(text)
        self._hide_timer.stop()
        self._on_show(0)

    # ── Slots ────────────────────────────────────────────────────────────────
    def _connect_signals(self):
        s = self._sig
        s.do_set_state.connect(self._on_set_state)
        s.do_set_mode.connect(self._on_set_mode)
        s.do_set_transcript.connect(self._on_set_transcript)
        s.do_set_response.connect(self._on_set_response)
        s.do_set_source.connect(self._on_set_source)
        s.do_set_cost.connect(self._on_set_cost)
        s.do_set_paused.connect(self._on_set_paused)
        s.do_show.connect(self._on_show)
        s.do_update_diag.connect(self._on_update_diag)
        s.do_set_model_label.connect(self._on_set_model_label)
        s.do_set_level.connect(self._on_set_level)
        s.do_set_activity.connect(self._on_set_activity)
        s.do_set_weather.connect(self._on_set_weather)
        s.do_add_system_msg.connect(self._on_add_system_msg)
        s.do_focus_input.connect(self._on_focus_input)
        s.do_finish_response.connect(self._on_finish_response)
        s.do_set_timer_chip.connect(self._on_set_timer_chip)

    def _on_set_state(self, s):
        self._state = s
        self._reactor.set_state(s)
        self._wave.set_state(s)
        self._diag.set_state(s)
        for f in self._frames:
            f.set_state(s)
        col = STATE_COLORS.get(s, C_CYAN)
        labels = STATE_LABELS.get(s, ("", ""))
        if not self._paused:
            self._status_main.setText(labels[0])
            self._status_main.setStyleSheet(
                f"color:{hexa(col)}; background:transparent; letter-spacing:4px;")
            self._status_sub.setText(f"// {labels[1]}")
        if s in ("listening", "processing", "speaking"):
            self._on_show(0)
            self._hide_timer.stop()
        elif s == "idle":
            self._conv.set_cursor_visible(False)
            if not self._pinned:
                self._schedule_hide(self.HIDE_IDLE_MS)
        self.update()

    def _on_set_mode(self, name):
        self._mode_name = name or "Normal"
        self._mode_btn.setText(f"MODE {self._mode_name.upper()} ▾")

    def _on_set_transcript(self, text):
        if text:
            self._conv.add_user(text)

    def _on_set_response(self, text):
        if text:
            self._conv.set_jarvis(text, self._cur_source or "")

    def _on_set_source(self, source):
        self._cur_source = source
        badge = SOURCE_BADGES.get(source)
        if badge:
            sym, col = badge
            self._badge_lbl.setText(sym)
            self._badge_lbl.setStyleSheet(f"color:{hexa(col)}; background:transparent;")
        else:
            self._badge_lbl.setText("")

    def _on_set_cost(self, last_usd, month_usd, calls):
        self._last_cost = last_usd
        self._month_cost = month_usd
        self._month_calls = calls
        EUR = 0.92

        def fmt(usd):
            e = usd * EUR
            if e < 0.01:
                return f"{e * 100:.4f}c€"
            if e < 1:
                return f"{e * 100:.2f}c€"
            return f"{e:.3f}€"

        parts = []
        if last_usd > 0:
            parts.append(f"DERNIER {fmt(last_usd)}")
        if month_usd > 0:
            parts.append(f"MOIS {fmt(month_usd)}")
        self._cost_lbl.setText("  ·  ".join(parts))

    def _on_update_diag(self, data):
        self._diag.update_data(data)

    def _on_set_model_label(self, name):
        self._diag.set_model(name)

    def _on_set_level(self, lvl):
        # lvl est un RMS brut : ~0.005 pour la parole au micro, ~0.1-0.3 pour la
        # voix TTS. La racine carrée compresse cette dynamique pour que les deux
        # sources animent la visu de façon comparable.
        vis = min(1.0, math.sqrt(max(0.0, lvl) * 30))
        self._reactor.set_level(vis)
        self._wave.set_level(vis)

    def _on_set_activity(self, text):
        self._activity = text
        self._activity_lbl.setText(f"⚙ {text}" if text else "")

    def _on_set_weather(self, text):
        self._weather = text
        self._weather_lbl.setText(text)
        self._weather_lbl.setVisible(bool(text))

    def _on_finish_response(self, tag):
        self._conv.finish_stream(tag)

    def _on_set_timer_chip(self, text):
        self._timer_lbl.setText(text)
        self._timer_lbl.setVisible(bool(text))

    def _on_add_system_msg(self, text):
        self._conv.add_system(text)

    def _on_focus_input(self):
        self._on_show(0)
        self.raise_()
        self.activateWindow()
        self._entry.setFocus()


# ── Façade publique (thread-safe) ─────────────────────────────────────────────
class JarvisOverlay:
    HIDE_AFTER_IDLE = _JarvisWindow.HIDE_IDLE_MS
    HIDE_AFTER_TRAY = _JarvisWindow.HIDE_TRAY_MS

    def __init__(self):
        self._app = None
        self._win = None
        self._sig = None
        self._input_queue = queue.Queue()
        self.on_mode_change = None   # callback(mode_id) branché par le runtime
        self.on_quit = None          # callback() branché par le runtime

    def start(self):
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setWindowIcon(app_icon())   # barre des tâches + fenêtres
        self._sig = _Signals()
        self._win = _JarvisWindow(self._sig, self._input_queue, self)

    def exec(self):
        if self._app:
            self._app.exec()

    # — Méthodes thread-safe (émettent des signaux Qt) —
    def show(self, duration_ms=None):
        if self._sig:
            self._sig.do_show.emit(
                duration_ms if duration_ms is not None else self.HIDE_AFTER_IDLE)

    def set_state(self, state):
        if self._sig:
            self._sig.do_set_state.emit(state)

    def set_mode(self, name):
        if self._sig:
            self._sig.do_set_mode.emit(name or "Normal")

    def set_transcript(self, text):
        if self._sig:
            self._sig.do_set_transcript.emit(text or "")

    def set_response(self, text):
        if self._sig:
            self._sig.do_set_response.emit(text or "")

    def set_source(self, source):
        if self._sig:
            self._sig.do_set_source.emit(source or "")

    def set_cost(self, last_usd, month_usd, calls):
        if self._sig:
            self._sig.do_set_cost.emit(last_usd, month_usd, calls)

    def set_paused(self, paused):
        if self._sig:
            self._sig.do_set_paused.emit(paused)

    def update_diagnostics(self, data: dict):
        if self._sig:
            self._sig.do_update_diag.emit(data)

    def set_model_label(self, name):
        """Affiche quel cerveau a répondu au dernier tour (ex: 'qwen3:14b')."""
        if self._sig:
            self._sig.do_set_model_label.emit(name or "—")

    def set_level(self, rms: float):
        """Niveau audio temps réel (RMS brut micro ou sortie voix)."""
        if self._sig:
            self._sig.do_set_level.emit(float(rms))

    def set_activity(self, text: str):
        """Activité agent en cours (nom d'outil), '' pour effacer."""
        if self._sig:
            self._sig.do_set_activity.emit(text or "")

    def set_weather(self, text: str):
        if self._sig:
            self._sig.do_set_weather.emit(text or "")

    def add_system_message(self, text: str):
        if self._sig:
            self._sig.do_add_system_msg.emit(text or "")

    def finish_response(self, tag: str = ""):
        """Fige la bulle Jarvis courante (curseur retiré, temps de réponse)."""
        if self._sig:
            self._sig.do_finish_response.emit(tag or "")

    def set_timer_chip(self, text: str):
        """Compte à rebours du prochain minuteur dans le header ('' = masqué)."""
        if self._sig:
            self._sig.do_set_timer_chip.emit(text or "")

    def focus_input(self):
        if self._sig:
            self._sig.do_focus_input.emit()

    def is_muted(self):
        return self._win._muted if self._win else False

    def get_text_input_nowait(self):
        try:
            return self._input_queue.get_nowait()
        except queue.Empty:
            return None

    def push_input(self, text: str):
        """Injecte un texte ou un token de contrôle comme si Monsieur l'avait
        saisi (utilisé par le tray et les hotkeys globaux)."""
        self._input_queue.put(text)


overlay = JarvisOverlay()


# ── Preview autonome ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    ov = JarvisOverlay()
    ov._app = app
    ov._sig = _Signals()
    ov._win = _JarvisWindow(ov._sig, ov._input_queue, ov)
    ov._win.show()

    states = ["idle", "listening", "processing", "speaking", "error"]
    idx = [0]

    def demo():
        s = states[idx[0] % len(states)]
        ov.set_state(s)
        ov.set_level(0.03 if s in ("listening", "speaking") else 0.0)
        if s == "listening":
            ov.set_transcript("Jarvis, ouvre mon agenda et dis-moi la météo.")
        elif s == "processing":
            ov.set_source("ai")
            ov.set_activity("run_powershell")
        elif s == "speaking":
            ov.set_source("ollama")
            ov.set_activity("")
            ov.set_response("Notion Calendar est ouvert, Monsieur. Il fait 21 degrés à Toulouse, ciel dégagé.")
            ov.set_cost(0.000024, 0.0187, 14)
        elif s == "idle":
            ov.set_source("cache")
        idx[0] += 1

    ov.set_weather("21° CIEL DÉGAGÉ")
    ov.set_model_label("qwen3:14b")
    ov.update_diagnostics({
        "cpu": 23, "mem": 41, "disk": 67, "net_up": 12, "net_dn": 340,
        "lat_ms": 640, "tokens": 48213, "cost_usd": 0.021, "calls": 14,
        "uptime": "02:41:07",
        "links": {"speaches": True, "ollama": True, "claude": True},
    })
    t = QTimer()
    t.setInterval(3000)
    t.timeout.connect(demo)
    t.start()
    demo()
    sys.exit(app.exec())

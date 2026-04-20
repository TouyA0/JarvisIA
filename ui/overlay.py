"""
Floating overlay Jarvis — HUD style (PyQt6)
- Alt + drag pour déplacer
- Edge-hide : glisse sur le bord droit, réapparaît au survol
- Pin pour garder visible en permanence
- Sélecteur de mode cliquable
- Mute coupe écoute ET réponse audio (mode textuel pur)
"""
from __future__ import annotations
import sys
import math
import random
import queue
import threading
import json
import pathlib
import time

from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit, QPushButton,
    QHBoxLayout, QVBoxLayout, QMenu,
)
from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve,
    QPoint, QPointF, QObject, pyqtSignal,
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QPainterPath, QFont, QCursor,
)

_ROOT      = pathlib.Path(__file__).parent.parent
MODES_FILE = _ROOT / "brain" / "modes" / "modes.json"

# ── Palette ───────────────────────────────────────────────────────────────────
_BG    = "#0a0e1a"
_BG2   = "#141a2a"
_BG3   = "#1a2535"
_CYAN  = "#4dd0e1"
_DIM   = "#7a8899"
_TEXT  = "#e0e6ed"
_WARN  = "#ff9800"
_RED   = "#e53935"

STATE_COLORS = {
    "idle":       "#1f4468",
    "listening":  "#4dd0e1",
    "processing": "#ff9800",
    "speaking":   "#66bb6a",
    "error":      "#e53935",
}
STATE_LABELS = {
    "idle":       "En veille…",
    "listening":  "À votre écoute, Monsieur.",
    "processing": "Un instant…",
    "speaking":   "Jarvis parle.",
    "error":      "Erreur.",
}
SOURCE_BADGES = {
    "cache":  ("●", "#4dd0e1"),
    "direct": ("◆", "#ab9ff2"),
    "ai":     ("⚡", "#ff9800"),
}

USD_TO_EUR = 0.92
PEEK_PX    = 8       # px visibles au bord droit en mode edge-hidden
ANIM_MS    = 30      # intervalle animation (ms)
SLIDE_MS   = 250     # durée animation glissement

TOKEN_PAUSE  = "__PAUSE__"
TOKEN_RESUME = "__RESUME__"


def _fmt_money(usd: float | None) -> str:
    if usd is None:
        return "—"
    eur = usd * USD_TO_EUR
    if eur < 0.01:
        return f"{eur * 100:.2f}c€"
    if eur < 1:
        return f"{eur * 100:.1f}c€"
    return f"{eur:.2f}€"


def _load_modes() -> list:
    try:
        with open(MODES_FILE, encoding="utf-8") as f:
            return json.load(f).get("modes", [])
    except Exception:
        return []


# ── Thread-safe signal bridge ─────────────────────────────────────────────────
class _Signals(QObject):
    do_set_state      = pyqtSignal(str)
    do_set_mode       = pyqtSignal(str)
    do_set_transcript = pyqtSignal(str)
    do_set_response   = pyqtSignal(str)
    do_set_source     = pyqtSignal(str)
    do_set_cost       = pyqtSignal(float, float, int)
    do_set_paused     = pyqtSignal(bool)
    do_show           = pyqtSignal(int)


# ── Animation canvas (custom QPainter) ───────────────────────────────────────
class _AnimCanvas(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(62)
        self._state      = "idle"
        self._phase      = 0.0
        self._wave_amps  = [0.0] * 24

    def set_state(self, s: str) -> None:
        self._state = s

    def tick(self, phase: float) -> None:
        self._phase = phase
        self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(0, 0, 0, 0))

        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        col = QColor(STATE_COLORS.get(self._state, _CYAN))
        ph  = self._phase
        s   = self._state

        if s == "idle":
            pulse  = (math.sin(ph * 0.6) + 1) / 2
            r_out  = 10 + pulse * 5
            r_in   = 5  + pulse * 2
            p.setPen(QPen(col, 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(cx, cy), r_out, r_out)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(col))
            p.drawEllipse(QPointF(cx, cy), r_in, r_in)

        elif s == "listening":
            n, bw, gap = 24, 6, 3
            sx = cx - (n * (bw + gap) - gap) / 2
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(col))
            for i in range(n):
                target = abs(math.sin(ph * 1.2 + i * 0.45)) * random.uniform(0.3, 1.0) * 22
                self._wave_amps[i] = self._wave_amps[i] * 0.6 + target * 0.4
                bh = max(2.0, self._wave_amps[i])
                x  = sx + i * (bw + gap)
                p.drawRect(int(x), int(cy - bh), bw, int(bh * 2))

        elif s == "processing":
            for i in range(8):
                angle = ph * 2 + i * math.pi / 4
                x = cx + math.cos(angle) * 16
                y = cy + math.sin(angle) * 16
                r = 2 + (i + 1) / 8 * 2
                c = QColor(col)
                c.setAlpha(int(50 + (i + 1) / 8 * 205))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(c))
                p.drawEllipse(QPointF(x, y), r, r)

        elif s == "speaking":
            pen = QPen(col, 2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath()
            for i in range(50):
                x   = cx - 140 + i * (280 / 49)
                amp = (math.sin(ph * 1.5 + i * 0.35)
                       * math.sin(ph * 0.6 + i * 0.12) * 18)
                if i == 0:
                    path.moveTo(x, cy + amp)
                else:
                    path.lineTo(x, cy + amp)
            p.drawPath(path)

        elif s == "error":
            blink = (math.sin(ph * 4) + 1) / 2
            r = 10 + blink * 4
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(col))
            p.drawEllipse(QPointF(cx, cy), r, r)

        p.end()


# ── Main HUD window ───────────────────────────────────────────────────────────
class _JarvisWindow(QWidget):

    W = 360
    H = 265

    HIDE_IDLE_MS = 3_000
    HIDE_TRAY_MS = 15_000

    def __init__(
        self,
        signals: _Signals,
        input_queue: queue.Queue,
        overlay_ref: "JarvisOverlay",
    ) -> None:
        super().__init__()
        self._sig          = signals
        self._input_queue  = input_queue
        self._overlay_ref  = overlay_ref

        self._state        = "idle"
        self._mode_name    = "Normal"
        self._pinned       = False
        self._mouse_inside = False
        self._muted        = False
        self._paused       = False
        self._edge_hidden  = False
        self._anim_phase   = 0.0
        self._last_cost    = 0.0
        self._month_cost   = 0.0
        self._month_calls  = 0
        self._cur_source: str | None = None
        self._drag_offset: QPoint | None = None

        self._setup_window()
        self._build_ui()
        self._connect_signals()
        self._start_timers()

    # ── Window setup ──────────────────────────────────────────────────────────

    def _setup_window(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.W, self.H)

        scr = QApplication.primaryScreen().geometry()
        self._screen_w = scr.width()
        self._normal_x = scr.width() - self.W - 40
        self._normal_y = int(scr.height() * 0.38)
        self.move(self._normal_x, self._normal_y)
        self.hide()

        self._slide = QPropertyAnimation(self, b"pos")
        self._slide.setDuration(SLIDE_MS)
        self._slide.setEasingCurve(QEasingCurve.Type.InOutCubic)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._check_and_hide)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg = QColor(_BG)
        bg.setAlpha(235)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(bg))
        p.drawRoundedRect(self.rect(), 12, 12)
        p.setPen(QPen(QColor(77, 208, 225, 35), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 12, 12)
        p.end()

    # ── UI builder ────────────────────────────────────────────────────────────

    def _ibtn(self, text: str, color: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setFont(QFont("Consolas", 10))
        btn.setFixedWidth(28)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setStyleSheet(self._ibtn_css(color))
        return btn

    @staticmethod
    def _ibtn_css(color: str) -> str:
        return (
            f"QPushButton {{ background:{_BG2}; color:{color}; border:none;"
            f" border-radius:4px; padding:4px 2px; }}"
            f"QPushButton:hover {{ background:{_BG3}; }}"
        )

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 9)
        layout.setSpacing(3)

        fn = QFont("Consolas", 9)

        # ── Title bar ─────────────────────────────────────────────────────────
        bar = QHBoxLayout()
        bar.setSpacing(4)

        title = QLabel("J.A.R.V.I.S.")
        title.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        title.setStyleSheet(f"color:{_CYAN}; background:transparent;")
        bar.addWidget(title)
        bar.addStretch()

        self._mode_btn = QPushButton("NORMAL ▾")
        self._mode_btn.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        self._mode_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._mode_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{_DIM}; border:none; padding:2px 4px; }}"
            f"QPushButton:hover {{ background:{_BG3}; border-radius:3px; }}"
        )
        self._mode_btn.clicked.connect(self._show_mode_menu)
        bar.addWidget(self._mode_btn)

        self._pin_btn = QPushButton("⊙")
        self._pin_btn.setFont(QFont("Consolas", 13))
        self._pin_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._pin_btn.setStyleSheet(
            f"QPushButton {{ background:transparent; color:{_DIM}; border:none; padding:2px 4px; }}"
            f"QPushButton:hover {{ background:{_BG3}; border-radius:3px; }}"
        )
        self._pin_btn.clicked.connect(self._toggle_pin)
        bar.addWidget(self._pin_btn)

        layout.addLayout(bar)

        # ── Animation canvas ──────────────────────────────────────────────────
        self._canvas = _AnimCanvas(self)
        self._canvas.setStyleSheet("background:transparent;")
        layout.addWidget(self._canvas)

        # ── Status ────────────────────────────────────────────────────────────
        self._status_lbl = QLabel(STATE_LABELS["idle"])
        self._status_lbl.setFont(QFont("Consolas", 10))
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_lbl.setStyleSheet(f"color:{_CYAN}; background:transparent;")
        layout.addWidget(self._status_lbl)

        # ── User transcript ───────────────────────────────────────────────────
        self._user_lbl = QLabel("")
        self._user_lbl.setFont(fn)
        self._user_lbl.setWordWrap(True)
        self._user_lbl.setStyleSheet(f"color:{_DIM}; background:transparent;")
        layout.addWidget(self._user_lbl)

        # ── Response + source badge ───────────────────────────────────────────
        resp = QHBoxLayout()
        resp.setSpacing(4)
        resp.setContentsMargins(0, 2, 0, 2)

        self._source_lbl = QLabel("")
        self._source_lbl.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        self._source_lbl.setFixedWidth(18)
        self._source_lbl.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self._source_lbl.setStyleSheet(f"color:{_DIM}; background:transparent;")
        resp.addWidget(self._source_lbl)

        self._resp_lbl = QLabel("")
        self._resp_lbl.setFont(fn)
        self._resp_lbl.setWordWrap(True)
        self._resp_lbl.setStyleSheet(f"color:{_TEXT}; background:transparent;")
        resp.addWidget(self._resp_lbl, 1)
        layout.addLayout(resp)

        layout.addStretch()

        # ── Cost footer ───────────────────────────────────────────────────────
        self._cost_lbl = QLabel("")
        self._cost_lbl.setFont(QFont("Consolas", 8))
        self._cost_lbl.setStyleSheet(f"color:{_DIM}; background:transparent;")
        layout.addWidget(self._cost_lbl)

        # ── Bottom bar ────────────────────────────────────────────────────────
        bottom = QHBoxLayout()
        bottom.setSpacing(4)
        bottom.setContentsMargins(0, 4, 0, 0)

        self._entry = QLineEdit()
        self._entry.setFont(fn)
        self._entry.setPlaceholderText("Écrire à Jarvis…")
        self._entry.setStyleSheet(
            f"QLineEdit {{ background:{_BG2}; color:{_TEXT}; border:none;"
            f" border-radius:4px; padding:4px 6px; }}"
        )
        self._entry.returnPressed.connect(self._on_send)
        bottom.addWidget(self._entry, 1)

        self._send_btn  = self._ibtn("▶", _CYAN)
        self._pause_btn = self._ibtn("⏸", _DIM)
        self._mute_btn  = self._ibtn("♪", _CYAN)
        self._send_btn.clicked.connect(self._on_send)
        self._pause_btn.clicked.connect(self._toggle_pause)
        self._mute_btn.clicked.connect(self._toggle_mute)
        bottom.addWidget(self._send_btn)
        bottom.addWidget(self._pause_btn)
        bottom.addWidget(self._mute_btn)

        layout.addLayout(bottom)

    # ── Signal connections ────────────────────────────────────────────────────

    def _connect_signals(self) -> None:
        s = self._sig
        s.do_set_state.connect(self._on_set_state)
        s.do_set_mode.connect(self._on_set_mode)
        s.do_set_transcript.connect(self._on_set_transcript)
        s.do_set_response.connect(self._on_set_response)
        s.do_set_source.connect(self._on_set_source)
        s.do_set_cost.connect(self._on_set_cost)
        s.do_set_paused.connect(self._on_set_paused)
        s.do_show.connect(self._on_show)

    # ── Timers ────────────────────────────────────────────────────────────────

    def _start_timers(self) -> None:
        t = QTimer(self)
        t.setInterval(ANIM_MS)
        t.timeout.connect(self._tick)
        t.start()

    def _tick(self) -> None:
        self._anim_phase += 0.18
        self._canvas.tick(self._anim_phase)

    # ── Drag (Alt + left-click) ───────────────────────────────────────────────

    def mousePressEvent(self, e) -> None:
        if (e.modifiers() & Qt.KeyboardModifier.AltModifier
                and e.button() == Qt.MouseButton.LeftButton):
            self._drag_offset = e.pos()

    def mouseMoveEvent(self, e) -> None:
        if self._drag_offset is not None:
            new_pos = e.globalPosition().toPoint() - self._drag_offset
            self._normal_x = new_pos.x()
            self._normal_y = new_pos.y()
            self.move(new_pos)
            self._edge_hidden = False

    def mouseReleaseEvent(self, _e) -> None:
        self._drag_offset = None

    # ── Hover / edge-hide ─────────────────────────────────────────────────────

    def enterEvent(self, _e) -> None:
        self._mouse_inside = True
        self._hide_timer.stop()
        if self._edge_hidden:
            self._expand_from_edge()

    def leaveEvent(self, _e) -> None:
        self._mouse_inside = False
        if not self._pinned and self._state == "idle":
            self._schedule_hide(self.HIDE_IDLE_MS)

    def _schedule_hide(self, ms: int) -> None:
        self._hide_timer.stop()
        self._hide_timer.start(ms)

    def _check_and_hide(self) -> None:
        if not self._pinned and not self._mouse_inside:
            self._collapse_to_edge()

    def _collapse_to_edge(self) -> None:
        if self._edge_hidden:
            return
        self._edge_hidden = True
        target = QPoint(self._screen_w - PEEK_PX, self.y())
        self._slide.stop()
        self._slide.setStartValue(self.pos())
        self._slide.setEndValue(target)
        self._slide.start()

    def _expand_from_edge(self) -> None:
        self._edge_hidden = False
        target = QPoint(self._normal_x, self._normal_y)
        self._slide.stop()
        self._slide.setStartValue(self.pos())
        self._slide.setEndValue(target)
        self._slide.start()

    # ── Visibility ────────────────────────────────────────────────────────────

    def _on_show(self, duration_ms: int) -> None:
        if not self.isVisible():
            self.show()
        if self._edge_hidden:
            self._expand_from_edge()
        self._hide_timer.stop()
        if not self._pinned and duration_ms > 0:
            self._schedule_hide(duration_ms)

    # ── Pin ───────────────────────────────────────────────────────────────────

    def _toggle_pin(self) -> None:
        self._pinned = not self._pinned
        if self._pinned:
            self._hide_timer.stop()
            self._pin_btn.setText("⊕")
            self._pin_btn.setStyleSheet(
                self._pin_btn.styleSheet().replace(_DIM, _CYAN)
            )
        else:
            self._pin_btn.setText("⊙")
            self._pin_btn.setStyleSheet(
                self._pin_btn.styleSheet().replace(_CYAN, _DIM)
            )
            if self._state == "idle":
                self._schedule_hide(self.HIDE_IDLE_MS)

    # ── Pause ─────────────────────────────────────────────────────────────────

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        self._sync_pause_btn()
        self._input_queue.put(TOKEN_PAUSE if self._paused else TOKEN_RESUME)

    def _on_set_paused(self, val: bool) -> None:
        self._paused = val
        self._sync_pause_btn()

    def _sync_pause_btn(self) -> None:
        if self._paused:
            self._pause_btn.setText("▶")
            self._pause_btn.setStyleSheet(self._ibtn_css(_WARN))
            self._status_lbl.setText("En pause.")
            self._status_lbl.setStyleSheet(f"color:{_RED}; background:transparent;")
        else:
            self._pause_btn.setText("⏸")
            self._pause_btn.setStyleSheet(self._ibtn_css(_DIM))

    # ── Mute (écoute + audio) ─────────────────────────────────────────────────

    def _toggle_mute(self) -> None:
        self._muted = not self._muted
        if self._muted:
            self._mute_btn.setText("∅")
            self._mute_btn.setStyleSheet(self._ibtn_css(_RED))
        else:
            self._mute_btn.setText("♪")
            self._mute_btn.setStyleSheet(self._ibtn_css(_CYAN))

    # ── Mode selector ─────────────────────────────────────────────────────────

    def _show_mode_menu(self) -> None:
        modes = _load_modes()
        if not modes:
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            f"QMenu {{ background:{_BG2}; color:{_TEXT}; border:1px solid {_BG3};"
            f" font-family:Consolas; font-size:9pt; }}"
            f"QMenu::item:selected {{ background:#1f3a5c; }}"
        )
        for mode in modes:
            mid   = mode["id"]
            mname = mode["name"].replace("Mode ", "")
            active = mname.lower() == self._mode_name.lower()
            action = menu.addAction(f"{'▶ ' if active else '   '}{mode['name']}")
            action.setData((mid, mname))

        pos    = self._mode_btn.mapToGlobal(self._mode_btn.rect().bottomLeft())
        chosen = menu.exec(pos)
        if chosen:
            mid, mname = chosen.data()
            self._on_set_mode(mname)
            cb = self._overlay_ref.on_mode_change
            if cb:
                threading.Thread(target=cb, args=(mid,), daemon=True).start()

    # ── Text input ────────────────────────────────────────────────────────────

    def _on_send(self) -> None:
        text = self._entry.text().strip()
        if not text:
            return
        self._entry.clear()
        self._input_queue.put(text)
        self._hide_timer.stop()
        self._on_show(0)

    # ── Signal handlers (Qt main thread) ─────────────────────────────────────

    def _on_set_state(self, state: str) -> None:
        self._state = state
        self._canvas.set_state(state)
        color = STATE_COLORS.get(state, _CYAN)
        if not self._paused:
            self._status_lbl.setText(STATE_LABELS.get(state, ""))
            self._status_lbl.setStyleSheet(
                f"color:{color}; background:transparent;"
            )
        if state in ("listening", "processing", "speaking"):
            self._on_show(0)
            self._hide_timer.stop()
        elif state == "idle" and not self._pinned:
            self._schedule_hide(self.HIDE_IDLE_MS)

    def _on_set_mode(self, name: str) -> None:
        self._mode_name = name or "Normal"
        self._mode_btn.setText(f"{self._mode_name.upper()} ▾")

    def _on_set_transcript(self, text: str) -> None:
        self._user_lbl.setText(f"> {text}" if text else "")

    def _on_set_response(self, text: str) -> None:
        self._resp_lbl.setText(text or "")
        self._refresh_footer()

    def _on_set_source(self, source: str) -> None:
        self._cur_source = source
        badge = SOURCE_BADGES.get(source)
        if badge:
            sym, col = badge
            self._source_lbl.setText(sym)
            self._source_lbl.setStyleSheet(
                f"color:{col}; background:transparent;"
            )
        else:
            self._source_lbl.setText("")
        self._refresh_footer()

    def _on_set_cost(self, last_usd: float, month_usd: float, calls: int) -> None:
        self._last_cost   = last_usd
        self._month_cost  = month_usd
        self._month_calls = calls
        self._refresh_footer()

    def _refresh_footer(self) -> None:
        src = self._cur_source
        if src == "ai":
            prefix, col = f"⚡ IA · {_fmt_money(self._last_cost)}", _WARN
        elif src == "cache":
            prefix, col = "● cache · 0ms", _CYAN
        elif src == "direct":
            prefix, col = "◆ local · 0ms", "#ab9ff2"
        else:
            prefix, col = "", _DIM
        month = (
            f"   Mois : {_fmt_money(self._month_cost)} · {self._month_calls} appels"
            if self._month_calls > 0 else ""
        )
        text = (prefix + month) if prefix else month.strip()
        self._cost_lbl.setText(text)
        self._cost_lbl.setStyleSheet(
            f"color:{col if prefix else _DIM}; background:transparent;"
        )


# ── Public API (unchanged pour jarvis.py) ─────────────────────────────────────
class JarvisOverlay:
    """
    Façade thread-safe exposée à jarvis.py.
    Même API qu'avant ; PyQt6 tourne sur le thread principal via exec().
    """

    HIDE_AFTER_IDLE = _JarvisWindow.HIDE_IDLE_MS
    HIDE_AFTER_TRAY = _JarvisWindow.HIDE_TRAY_MS

    def __init__(self) -> None:
        self._app: QApplication | None = None
        self._win: _JarvisWindow | None = None
        self._sig: _Signals | None = None
        self._input_queue: queue.Queue = queue.Queue()
        self.on_mode_change = None  # callable(mode_id) — défini par jarvis.py

    def start(self) -> None:
        """Crée QApplication + fenêtre. Appeler depuis le thread principal."""
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._sig = _Signals()
        self._win = _JarvisWindow(self._sig, self._input_queue, self)

    def exec(self) -> None:
        """Lance la boucle Qt. Bloque jusqu'à la fermeture. Thread principal."""
        if self._app:
            self._app.exec()

    # ── Thread-safe setters ───────────────────────────────────────────────────

    def show(self, duration_ms: int | None = None) -> None:
        if self._sig:
            self._sig.do_show.emit(
                duration_ms if duration_ms is not None else self.HIDE_AFTER_IDLE
            )

    def set_state(self, state: str) -> None:
        if self._sig:
            self._sig.do_set_state.emit(state)

    def set_mode(self, name: str) -> None:
        if self._sig:
            self._sig.do_set_mode.emit(name or "Normal")

    def set_transcript(self, text: str) -> None:
        if self._sig:
            self._sig.do_set_transcript.emit(text or "")

    def set_response(self, text: str) -> None:
        if self._sig:
            self._sig.do_set_response.emit(text or "")

    def set_source(self, source: str) -> None:
        if self._sig:
            self._sig.do_set_source.emit(source or "")

    def set_cost(self, last_usd: float, month_usd: float, calls: int) -> None:
        if self._sig:
            self._sig.do_set_cost.emit(last_usd, month_usd, calls)

    def set_paused(self, paused: bool) -> None:
        if self._sig:
            self._sig.do_set_paused.emit(paused)

    def is_muted(self) -> bool:
        return self._win._muted if self._win else False

    def get_text_input_nowait(self):
        try:
            return self._input_queue.get_nowait()
        except queue.Empty:
            return None


overlay = JarvisOverlay()

"""
J.A.R.V.I.S. — HUD Overlay PyQt6
Fidèle au design Claude Design : panneau gauche + panneau droit diagnostics
"""
from __future__ import annotations
import sys, math, random, queue, threading, json, pathlib, time, os
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit,
    QPushButton, QHBoxLayout, QVBoxLayout, QMenu, QFrame,
)
from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve,
    QPoint, QPointF, QObject, pyqtSignal, QRectF,
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush,
    QFont, QCursor, QLinearGradient, QRadialGradient,
    QPainterPath,
)

_ROOT      = pathlib.Path(__file__).parent.parent
MODES_FILE = _ROOT / "brain" / "modes" / "modes.json"

# ── Palette ───────────────────────────────────────────────────────────────────
C_BG        = QColor(8,   14,  26)
C_BG2       = QColor(12,  20,  36)
C_GRID      = QColor(0,   180, 220, 12)
C_CYAN      = QColor(0,   210, 240)
C_CYAN_DIM  = QColor(0,   140, 170, 140)
C_GOLD      = QColor(255, 185, 30)
C_RED       = QColor(220, 60,  60)
C_GREEN     = QColor(40,  210, 100)
C_WHITE     = QColor(255, 255, 255)
C_DIM       = QColor(60,  100, 130)
C_DIM2      = QColor(40,  70,  95)
C_TEXT      = QColor(160, 210, 230)

STATE_COLORS = {
    "idle":       C_CYAN_DIM,
    "listening":  C_CYAN,
    "processing": C_GOLD,
    "speaking":   C_GREEN,
    "error":      C_RED,
}
STATE_LABELS = {
    "idle":       ("EN VEILLE",      "STANDBY"),
    "listening":  ("ÉCOUTE ACTIVE",  "LISTENING"),
    "processing": ("TRAITEMENT",     "PROCESSING"),
    "speaking":   ("TRANSMISSION",   "SPEAKING"),
    "error":      ("ERREUR SYSTÈME", "FAULT"),
}
SOURCE_BADGES = {
    "cache":  ("◉ CACHE", QColor(0, 210, 240)),
    "direct": ("◆ LOCAL", QColor(160, 120, 255)),
    "ai":     ("⚡ AI",   QColor(255, 185, 30)),
}

TOKEN_PAUSE  = "__PAUSE__"
TOKEN_RESUME = "__RESUME__"

def _hex(c: QColor) -> str:
    return f"#{c.red():02x}{c.green():02x}{c.blue():02x}"

def _load_modes():
    try:
        with open(MODES_FILE, encoding="utf-8") as f:
            return json.load(f).get("modes", [])
    except Exception:
        return []


# ── Signals ───────────────────────────────────────────────────────────────────
class _Signals(QObject):
    do_set_state      = pyqtSignal(str)
    do_set_mode       = pyqtSignal(str)
    do_set_transcript = pyqtSignal(str)
    do_set_response   = pyqtSignal(str)
    do_set_source     = pyqtSignal(str)
    do_set_cost       = pyqtSignal(float, float, int)
    do_set_paused     = pyqtSignal(bool)
    do_show           = pyqtSignal(int)
    do_update_diag    = pyqtSignal(int, int, int, int, str, str)


# ── Arc Reactor canvas ────────────────────────────────────────────────────────
class _ReactorCanvas(QWidget):
    W = 90

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.W, self.W)
        self._state = "idle"
        self._phase = 0.0

    def set_state(self, s): self._state = s
    def tick(self, ph): self._phase = ph; self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(0, 0, 0, 0))

        col   = STATE_COLORS.get(self._state, C_CYAN)
        ph    = self._phase
        pulse = (math.sin(ph * 0.8) + 1) / 2
        cx, cy = self.W // 2, self.W // 2
        R = 36

        # Glow
        for r in range(R + 8, R - 4, -3):
            gc = QColor(col); gc.setAlpha(int(3 + pulse * 8))
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(gc))
            p.drawEllipse(QPointF(cx, cy), r, r)

        # Outer ring
        rc = QColor(col); rc.setAlpha(int(100 + pulse * 130))
        p.setPen(QPen(rc, 1.5)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), R, R)

        # Dashed outer ring
        dc = QColor(col); dc.setAlpha(50)
        pen = QPen(dc, 1)
        pen.setStyle(Qt.PenStyle.DotLine)
        p.setPen(pen)
        p.drawEllipse(QPointF(cx, cy), R + 5, R + 5)

        # 8 blades
        for i in range(8):
            ang = ph * 0.5 + i * math.pi / 4
            x1 = cx + math.cos(ang) * 12; y1 = cy + math.sin(ang) * 12
            x2 = cx + math.cos(ang) * 28; y2 = cy + math.sin(ang) * 28
            bc = QColor(col); bc.setAlpha(int(100 + pulse * 140))
            p.setPen(QPen(bc, 1.8))
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # Inner ring
        ic = QColor(col); ic.setAlpha(160)
        p.setPen(QPen(ic, 1.2)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), 11, 11)

        # Core
        core = QRadialGradient(QPointF(cx, cy), 10)
        cc = QColor(col); cc.setAlpha(int(180 + pulse * 75))
        core.setColorAt(0, cc)
        core.setColorAt(0.5, QColor(col.red(), col.green(), col.blue(), 60))
        core.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(core))
        p.drawEllipse(QPointF(cx, cy), 10, 10)

        p.end()


# ── Waveform canvas ───────────────────────────────────────────────────────────
class _WaveCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(90)
        self._state = "idle"
        self._phase = 0.0
        self._bars  = [0.0] * 40

    def set_state(self, s): self._state = s
    def tick(self, ph): self._phase = ph; self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(0, 0, 0, 0))

        w, h  = self.width(), self.height()
        col   = STATE_COLORS.get(self._state, C_CYAN)
        ph    = self._phase
        s     = self._state
        cy    = h // 2
        n     = 40
        bw    = max(2, (w - 10) // n - 1)
        gap   = max(1, ((w - 10) - n * bw) // n)

        for i in range(n):
            if s == "listening":
                t = abs(math.sin(ph*1.6+i*0.48)) * random.uniform(0.15, 1.0) * (cy - 6)
            elif s == "speaking":
                # Onde en forme de losange / gaussienne
                center = n / 2
                gauss = math.exp(-((i - center)**2) / (2 * (n/5)**2))
                t = abs(math.sin(ph*2.2 + i*0.3)) * gauss * (cy - 4)
            elif s == "processing":
                t = abs(math.sin(ph*3.0 + i*0.7)) * (cy - 8) * 0.6
            elif s == "idle":
                t = abs(math.sin(ph*0.25 + i*0.2)) * 4 + 2
            else:  # error
                t = abs(math.sin(ph*4.0 + i*0.5)) * (cy - 6) * random.uniform(0.5, 1.0)

            self._bars[i] = self._bars[i] * 0.5 + t * 0.5
            bh = max(2.0, self._bars[i])
            x  = 5 + i * (bw + gap)

            bc = QColor(col); bc.setAlpha(int(140 + bh / (cy) * 100))
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QBrush(bc))
            p.drawRect(int(x), int(cy - bh), bw, int(bh * 2))

            # Tip
            tc = QColor(C_WHITE); tc.setAlpha(int(bh / cy * 120))
            p.setBrush(QBrush(tc))
            p.drawRect(int(x), int(cy - bh), bw, 2)

        p.end()


# ── Diagnostics panel ─────────────────────────────────────────────────────────
class _DiagPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(180)
        self._cpu    = 0
        self._mem    = 0
        self._lat    = 0
        self._tokens = 0
        self._model  = "haiku-4.5"
        self._uptime = "00:00:00"
        self._start  = time.time()
        self._state  = "idle"

        # Timer uptime
        t = QTimer(self)
        t.setInterval(1000)
        t.timeout.connect(self._tick_uptime)
        t.start()

    def update_diag(self, cpu, mem, lat, tokens, model, uptime=""):
        self._cpu    = cpu
        self._mem    = mem
        self._lat    = lat
        self._tokens = tokens
        self._model  = model
        if uptime: self._uptime = uptime
        self.update()

    def set_state(self, s):
        self._state = s
        self.update()

    def _tick_uptime(self):
        elapsed = int(time.time() - self._start)
        h = elapsed // 3600
        m = (elapsed % 3600) // 60
        s = elapsed % 60
        self._uptime = f"{h:02d}:{m:02d}:{s:02d}"
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(0, 0, 0, 0))

        col  = STATE_COLORS.get(self._state, C_CYAN)
        fn7  = QFont("Consolas", 7)
        fn8  = QFont("Consolas", 8)
        fn8b = QFont("Consolas", 8, QFont.Weight.Bold)
        w, h = self.width(), self.height()

        # Séparateur vertical gauche
        lc = QColor(col); lc.setAlpha(40)
        p.setPen(QPen(lc, 1))
        p.drawLine(0, 0, 0, h)

        y = 8
        # Titre
        dot_col = QColor(col); dot_col.setAlpha(200)
        p.setPen(QPen(dot_col, 1))
        p.setFont(fn7)
        p.drawText(12, y + 10, "● SYS.DIAGNOSTICS")
        y += 20

        def draw_bar(label, val, max_val=100, warn=70, crit=90):
            nonlocal y
            p.setFont(fn7)
            lc2 = QColor(C_DIM)
            p.setPen(QPen(lc2, 1))
            p.drawText(12, y + 8, label)

            # Valeur
            vc = QColor(col) if val < warn else (QColor(C_GOLD) if val < crit else QColor(C_RED))
            p.setPen(QPen(vc, 1))
            p.setFont(fn7)
            suffix = "ms" if label == "LAT" else "%"
            p.drawText(w - 40, y + 8, f"{val}{suffix}")

            # Barre
            bx, bw2, bh2 = 12, w - 52, 3
            y += 12
            bg = QColor(C_DIM2)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(bg))
            p.drawRect(bx, y, bw2, bh2)
            fill_w = int(bw2 * min(val, max_val) / max_val)
            fc = QColor(col) if val < warn else (QColor(C_GOLD) if val < crit else QColor(C_RED))
            p.setBrush(QBrush(fc))
            p.drawRect(bx, y, fill_w, bh2)
            y += 10

        draw_bar("CPU", self._cpu)
        draw_bar("MEM", self._mem)
        draw_bar("LAT", self._lat, max_val=500, warn=100, crit=300)

        y += 4
        sep_col = QColor(col); sep_col.setAlpha(25)
        p.setPen(QPen(sep_col, 1))
        p.drawLine(12, y, w - 8, y)
        y += 8

        def draw_kv(k, v):
            nonlocal y
            p.setFont(fn7)
            p.setPen(QPen(QColor(C_DIM), 1))
            p.drawText(12, y, k)
            p.setPen(QPen(QColor(C_TEXT), 1))
            p.setFont(fn8)
            p.drawText(w - 8 - p.fontMetrics().horizontalAdvance(str(v)), y, str(v))
            y += 14

        draw_kv("TOKENS", f"{self._tokens:,}".replace(",", " "))
        draw_kv("MODEL",  self._model)
        draw_kv("UPTIME", self._uptime)

        p.end()


# ── Main HUD window ───────────────────────────────────────────────────────────
class _JarvisWindow(QWidget):
    W = 820
    H = 460
    HIDE_IDLE_MS = 5_000
    HIDE_TRAY_MS = 15_000

    def __init__(self, signals, input_queue, overlay_ref):
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
        self._cur_source   = None
        self._drag_offset  = None
        self._lvl          = 0.0
        self._tokens_total = 0
        self._setup_window()
        self._build_ui()
        self._connect_signals()
        self._start_timers()

    def _setup_window(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.W, self.H)
        scr = QApplication.primaryScreen().geometry()
        self._screen_w = scr.width()
        self._screen_h = scr.height()
        self._normal_x = scr.width() - self.W - 20
        self._normal_y = scr.height() // 2 - self.H // 2
        self.move(self._normal_x, self._normal_y)
        self.hide()
        self._slide = QPropertyAnimation(self, b"pos")
        self._slide.setDuration(300)
        self._slide.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._check_and_hide)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        col  = STATE_COLORS.get(self._state, C_CYAN)

        # Fond
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(C_BG))
        p.drawRoundedRect(self.rect(), 4, 4)

        # Grille de fond
        gc = QColor(C_GRID)
        p.setPen(QPen(gc, 1))
        for x in range(0, w, 40):
            p.drawLine(x, 0, x, h)
        for y in range(0, h, 40):
            p.drawLine(0, y, w, y)

        # Bordure principale
        bc = QColor(col); bc.setAlpha(80)
        p.setPen(QPen(bc, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 4, 4)

        # Ligne top lumineuse
        tc = QColor(col); tc.setAlpha(220)
        p.setPen(QPen(tc, 2))
        p.drawLine(0, 0, w, 0)

        # Coins HUD
        cc = QColor(col); cc.setAlpha(255)
        p.setPen(QPen(cc, 2))
        L = 20
        for (ox, oy, sx, sy) in [(0,0,1,1),(w,0,-1,1),(0,h,1,-1),(w,h,-1,-1)]:
            p.drawLine(ox, oy+sy*1, ox, oy+sy*L)
            p.drawLine(ox+sx*1, oy, ox+sx*L, oy)

        # Séparateur header
        sc = QColor(col); sc.setAlpha(35)
        p.setPen(QPen(sc, 1))
        p.drawLine(0, 38, w, 38)

        # Séparateur footer
        p.drawLine(0, h - 58, w, h - 58)

        # Séparateur barre du bas
        p.drawLine(0, h - 30, w, h - 30)

        p.end()

    def _label(self, text, font_size=8, color=None, bold=False):
        lbl = QLabel(text)
        w = QFont.Weight.Bold if bold else QFont.Weight.Normal
        lbl.setFont(QFont("Consolas", font_size, w))
        col = color or _hex(C_DIM)
        lbl.setStyleSheet(f"color:{col}; background:transparent;")
        return lbl

    def _sep(self, vertical=False):
        f = QFrame()
        f.setFrameShape(QFrame.Shape.VLine if vertical else QFrame.Shape.HLine)
        f.setStyleSheet("color:#0a2030;")
        return f

    def _ctrl_btn(self, text, color="#00d2f0", tip="", size=28):
        btn = QPushButton(text)
        btn.setFont(QFont("Consolas", 11))
        btn.setFixedSize(size, size)
        btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        btn.setToolTip(tip)
        self._style_ctrl(btn, color)
        return btn

    @staticmethod
    def _style_ctrl(btn, color):
        btn.setStyleSheet(
            f"QPushButton {{ background:#060e1c; color:{color};"
            f" border:1px solid {color}40; border-radius:3px; }}"
            f"QPushButton:hover {{ background:#0d1e30; border-color:{color}99; }}"
            f"QPushButton:pressed {{ background:#162840; }}"
        )

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        fn7 = QFont("Consolas", 7)
        fn8 = QFont("Consolas", 8)
        fn9 = QFont("Consolas", 9)

        # ══ HEADER ═══════════════════════════════════════════════════════════
        hdr = QHBoxLayout()
        hdr.setContentsMargins(12, 0, 8, 0)
        hdr.setSpacing(8)

        title = QLabel("J.A.R.V.I.S.")
        title.setFont(QFont("Consolas", 14, QFont.Weight.Bold))
        title.setStyleSheet("color:#00d2f0; background:transparent; letter-spacing:3px;")
        hdr.addWidget(title)

        self._dot = QLabel("●")
        self._dot.setFont(QFont("Consolas", 10))
        self._dot.setStyleSheet("color:#00d2f080; background:transparent;")
        hdr.addWidget(self._dot)

        hdr.addStretch()

        # Mode
        self._mode_btn = QPushButton("MODE  NORMAL ▾")
        self._mode_btn.setFont(QFont("Consolas", 8))
        self._mode_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._mode_btn.setStyleSheet(
            "QPushButton { background:#060e1c; color:#405570;"
            " border:1px solid #00d2f030; border-radius:3px; padding:3px 10px; letter-spacing:1px; }"
            "QPushButton:hover { color:#00d2f0; border-color:#00d2f080; }"
        )
        self._mode_btn.clicked.connect(self._show_mode_menu)
        hdr.addWidget(self._mode_btn)

        self._pin_btn = QPushButton("⊙")
        self._pin_btn.setFont(QFont("Consolas", 12))
        self._pin_btn.setFixedSize(28, 28)
        self._pin_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._pin_btn.setToolTip("Épingler")
        self._pin_btn.setStyleSheet(
            "QPushButton { background:transparent; color:#405570; border:none; }"
            "QPushButton:hover { color:#00d2f0; }"
        )
        self._pin_btn.clicked.connect(self._toggle_pin)
        hdr.addWidget(self._pin_btn)

        self._close_btn = QPushButton("✕")
        self._close_btn.setFont(QFont("Consolas", 11))
        self._close_btn.setFixedSize(28, 28)
        self._close_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._close_btn.setToolTip("Fermer Jarvis")
        self._close_btn.setStyleSheet(
            "QPushButton { background:transparent; color:#405570; border:none; }"
            "QPushButton:hover { color:#dc2828; }"
        )
        self._close_btn.clicked.connect(self._on_close)
        hdr.addWidget(self._close_btn)

        hdr_w = QWidget(); hdr_w.setFixedHeight(38)
        hdr_w.setLayout(hdr)
        hdr_w.setStyleSheet("background:transparent;")
        root.addWidget(hdr_w)

        # ══ CORPS PRINCIPAL ═══════════════════════════════════════════════════
        body = QHBoxLayout()
        body.setContentsMargins(12, 8, 8, 0)
        body.setSpacing(0)

        # ── Panneau gauche ────────────────────────────────────────────────────
        left = QVBoxLayout()
        left.setSpacing(4)

        # Arc reactor + waveform
        viz = QHBoxLayout(); viz.setSpacing(12)
        self._reactor = _ReactorCanvas()
        viz.addWidget(self._reactor)
        self._wave = _WaveCanvas()
        viz.addWidget(self._wave, 1)
        left.addLayout(viz)

        # Statut + LVL
        stat_row = QHBoxLayout()
        self._status_main = QLabel("EN VEILLE")
        self._status_main.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        self._status_main.setStyleSheet("color:#00607080; background:transparent; letter-spacing:2px;")
        stat_row.addWidget(self._status_main)

        self._status_sub = QLabel("// STANDBY")
        self._status_sub.setFont(QFont("Consolas", 9))
        self._status_sub.setStyleSheet("color:#30455580; background:transparent;")
        stat_row.addWidget(self._status_sub)

        stat_row.addStretch()

        lvl_lbl = self._label("LVL", 7)
        stat_row.addWidget(lvl_lbl)
        self._lvl_val = QLabel("0.00")
        self._lvl_val.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self._lvl_val.setStyleSheet("color:#00607080; background:transparent;")
        stat_row.addWidget(self._lvl_val)

        left.addLayout(stat_row)

        # Transcript
        self._user_lbl = QLabel("")
        self._user_lbl.setFont(fn8)
        self._user_lbl.setWordWrap(True)
        self._user_lbl.setMaximumHeight(28)
        self._user_lbl.setStyleSheet("color:#405570; background:transparent;")
        left.addWidget(self._user_lbl)

        # Réponse + badge
        resp_row = QHBoxLayout(); resp_row.setSpacing(6)
        self._badge_btn = QPushButton("")
        self._badge_btn.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
        self._badge_btn.setFixedHeight(18)
        self._badge_btn.setStyleSheet(
            "QPushButton { background:#060e1c; color:#00d2f0;"
            " border:1px solid #00d2f050; border-radius:2px; padding:0 5px; }"
        )
        self._badge_btn.hide()
        resp_row.addWidget(self._badge_btn)

        self._resp_lbl = QLabel("")
        self._resp_lbl.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self._resp_lbl.setWordWrap(True)
        self._resp_lbl.setMaximumHeight(52)
        self._resp_lbl.setStyleSheet("color:#b4e6ff; background:transparent;")
        resp_row.addWidget(self._resp_lbl, 1)
        left.addLayout(resp_row)

        # Coût
        self._cost_lbl = QLabel("")
        self._cost_lbl.setFont(QFont("Consolas", 7))
        self._cost_lbl.setStyleSheet("color:#253545; background:transparent; letter-spacing:1px;")
        left.addWidget(self._cost_lbl)

        left.addStretch()
        body.addLayout(left, 1)

        # ── Panneau droit diagnostics ─────────────────────────────────────────
        self._diag = _DiagPanel()
        body.addWidget(self._diag)

        body_w = QWidget()
        body_w.setLayout(body)
        body_w.setStyleSheet("background:transparent;")
        root.addWidget(body_w, 1)

        # ══ BARRE DE CONTRÔLE ══════════════════════════════════════════════════
        ctrl_w = QWidget(); ctrl_w.setFixedHeight(58)
        ctrl_w.setStyleSheet("background:transparent;")
        ctrl = QHBoxLayout(ctrl_w)
        ctrl.setContentsMargins(12, 6, 8, 4)
        ctrl.setSpacing(6)

        self._entry = QLineEdit()
        self._entry.setFont(fn9)
        self._entry.setPlaceholderText("> Écrire à Jarvts…")
        self._entry.setStyleSheet(
            "QLineEdit { background:#040b16; color:#b4e6ff;"
            " border:1px solid #00d2f025; border-radius:3px; padding:5px 8px; }"
            "QLineEdit:focus { border-color:#00d2f060; }"
        )
        self._entry.returnPressed.connect(self._on_send)
        ctrl.addWidget(self._entry, 1)

        self._send_btn  = self._ctrl_btn("→",  "#00d2f0", "Envoyer")
        self._pause_btn = self._ctrl_btn("||", "#405570", "Pause / Reprendre")
        self._mute_btn  = self._ctrl_btn("◄",  "#00d2f0", "Mute")
        self._send_btn.clicked.connect(self._on_send)
        self._pause_btn.clicked.connect(self._toggle_pause)
        self._mute_btn.clicked.connect(self._toggle_mute)
        ctrl.addWidget(self._send_btn)
        ctrl.addWidget(self._pause_btn)
        ctrl.addWidget(self._mute_btn)
        root.addWidget(ctrl_w)

        # ══ STATUS BAR ════════════════════════════════════════════════════════
        sbar_w = QWidget(); sbar_w.setFixedHeight(30)
        sbar_w.setStyleSheet("background:transparent;")
        sbar = QHBoxLayout(sbar_w)
        sbar.setContentsMargins(12, 0, 12, 0)
        sbar.setSpacing(16)

        self._link_lbl  = self._label("◈ LINK", 7, "#00d2f060")
        self._enc_lbl   = self._label("ENC AES-256", 7, "#304050")
        self._mic_lbl   = self._label("MIC ON", 7, "#304050")
        sbar.addWidget(self._link_lbl)
        sbar.addWidget(self._enc_lbl)
        sbar.addWidget(self._mic_lbl)
        sbar.addStretch()

        self._clock_lbl = self._label("00:00:00", 8, "#304050")
        sbar.addWidget(self._clock_lbl)

        # Timer horloge
        ct = QTimer(self)
        ct.setInterval(1000)
        ct.timeout.connect(self._tick_clock)
        ct.start()
        self._tick_clock()

        root.addWidget(sbar_w)

    def _tick_clock(self):
        self._clock_lbl.setText(time.strftime("%H:%M:%S_"))

    # ── Timers animation ──────────────────────────────────────────────────────
    def _start_timers(self):
        t = QTimer(self)
        t.setInterval(25)
        t.timeout.connect(self._tick)
        t.start()

        # Simuler CPU/MEM pour la démo
        diag_t = QTimer(self)
        diag_t.setInterval(2000)
        diag_t.timeout.connect(self._fake_diag)
        diag_t.start()

    def _tick(self):
        self._anim_phase += 0.15
        ph = self._anim_phase
        self._reactor.tick(ph)
        self._wave.tick(ph)

        col   = STATE_COLORS.get(self._state, C_CYAN)
        alpha = int(80 + ((math.sin(ph * 1.1) + 1) / 2) * 170)
        self._dot.setStyleSheet(
            f"color:rgba({col.red()},{col.green()},{col.blue()},{alpha});"
            " background:transparent;"
        )

        # LVL aléatoire
        if self._state != "idle":
            self._lvl = min(1.0, self._lvl * 0.95 + random.uniform(0, 0.1))
        else:
            self._lvl = max(0.0, self._lvl * 0.98)
        self._lvl_val.setText(f"{self._lvl:.2f}" if self._state != "idle" else "0.02")

        self.update()

    def _fake_diag(self):
        import psutil
        try:
            cpu = int(psutil.cpu_percent())
            mem = int(psutil.virtual_memory().percent)
        except Exception:
            cpu = random.randint(5, 30)
            mem = random.randint(30, 60)
        lat = random.randint(8, 30) if self._state == "idle" else random.randint(50, 200)
        self._diag.update_diag(cpu, mem, lat, self._tokens_total, "haiku-4.5")
        self._diag.set_state(self._state)

    # ── Drag ──────────────────────────────────────────────────────────────────
    def mousePressEvent(self, e):
        if (e.modifiers() & Qt.KeyboardModifier.AltModifier
                and e.button() == Qt.MouseButton.LeftButton):
            self._drag_offset = e.pos()

    def mouseMoveEvent(self, e):
        if self._drag_offset is not None:
            np_ = e.globalPosition().toPoint() - self._drag_offset
            self._normal_x = np_.x(); self._normal_y = np_.y()
            self.move(np_); self._edge_hidden = False

    def mouseReleaseEvent(self, _): self._drag_offset = None

    # ── Hover / edge-hide ─────────────────────────────────────────────────────
    def enterEvent(self, _):
        self._mouse_inside = True
        self._hide_timer.stop()
        if self._edge_hidden: self._expand()

    def leaveEvent(self, _):
        self._mouse_inside = False
        if not self._pinned and self._state == "idle":
            self._schedule_hide(self.HIDE_IDLE_MS)

    def _schedule_hide(self, ms):
        self._hide_timer.stop(); self._hide_timer.start(ms)

    def _check_and_hide(self):
        if not self._pinned and not self._mouse_inside: self._collapse()

    def _collapse(self):
        if self._edge_hidden: return
        self._edge_hidden = True
        self._animate_to(QPoint(self._screen_w - 12, self.y()))

    def _expand(self):
        self._edge_hidden = False
        self._animate_to(QPoint(self._normal_x, self._normal_y))

    def _animate_to(self, target):
        self._slide.stop()
        self._slide.setStartValue(self.pos())
        self._slide.setEndValue(target)
        self._slide.start()

    def _on_show(self, ms):
        if not self.isVisible(): self.show()
        if self._edge_hidden: self._expand()
        self._hide_timer.stop()
        if not self._pinned and ms > 0: self._schedule_hide(ms)

    def _on_close(self):
        ref = self._overlay_ref
        if ref and getattr(ref, '_tray_icon', None):
            try: ref._tray_icon.stop()
            except Exception: pass
        QApplication.quit()
        os._exit(0)

    def _toggle_pin(self):
        self._pinned = not self._pinned
        if self._pinned:
            self._hide_timer.stop()
            self._pin_btn.setText("⊕")
            self._pin_btn.setStyleSheet(
                "QPushButton { background:transparent; color:#00d2f0; border:none; }"
            )
        else:
            self._pin_btn.setText("⊙")
            self._pin_btn.setStyleSheet(
                "QPushButton { background:transparent; color:#405570; border:none; }"
                "QPushButton:hover { color:#00d2f0; }"
            )
            if self._state == "idle": self._schedule_hide(self.HIDE_IDLE_MS)

    def _toggle_pause(self):
        self._paused = not self._paused
        self._sync_pause()
        self._input_queue.put(TOKEN_PAUSE if self._paused else TOKEN_RESUME)

    def _on_set_paused(self, val):
        self._paused = val; self._sync_pause()

    def _sync_pause(self):
        if self._paused:
            self._pause_btn.setText("▶")
            self._style_ctrl(self._pause_btn, "#ff9800")
            self._status_main.setText("EN PAUSE")
            self._status_main.setStyleSheet("color:#ff9800; background:transparent; letter-spacing:2px;")
            self._status_sub.setText("// PAUSED")
        else:
            self._pause_btn.setText("||")
            self._style_ctrl(self._pause_btn, "#405570")

    def _toggle_mute(self):
        self._muted = not self._muted
        if self._muted:
            self._mute_btn.setText("∅")
            self._style_ctrl(self._mute_btn, "#dc2828")
            self._mic_lbl.setStyleSheet("color:#dc2828; background:transparent;")
            self._mic_lbl.setText("MIC OFF")
        else:
            self._mute_btn.setText("◄")
            self._style_ctrl(self._mute_btn, "#00d2f0")
            self._mic_lbl.setStyleSheet("color:#304050; background:transparent;")
            self._mic_lbl.setText("MIC ON")

    def _show_mode_menu(self):
        modes = _load_modes()
        if not modes: return
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background:#040b16; color:#b4e6ff; border:1px solid #00d2f025;"
            " font-family:Consolas; font-size:9pt; padding:4px; }"
            "QMenu::item { padding:7px 20px; letter-spacing:1px; }"
            "QMenu::item:selected { background:#0a1e35; color:#00d2f0; }"
        )
        for mode in modes:
            mid   = mode["id"]
            mname = mode["name"].replace("Mode ", "")
            active = mname.lower() == self._mode_name.lower()
            action = menu.addAction(f"{'> ' if active else '  '}{mode['name'].upper()}")
            action.setData((mid, mname))
        pos = self._mode_btn.mapToGlobal(self._mode_btn.rect().bottomLeft())
        chosen = menu.exec(pos)
        if chosen:
            mid, mname = chosen.data()
            self._on_set_mode(mname)
            cb = self._overlay_ref.on_mode_change if self._overlay_ref else None
            if cb: threading.Thread(target=cb, args=(mid,), daemon=True).start()

    def _on_send(self):
        text = self._entry.text().strip()
        if not text: return
        self._entry.clear()
        self._input_queue.put(text)
        self._hide_timer.stop(); self._on_show(0)

    # ── Signal handlers ───────────────────────────────────────────────────────
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

    def _on_set_state(self, state):
        self._state = state
        self._reactor.set_state(state)
        self._wave.set_state(state)
        self._diag.set_state(state)
        col    = STATE_COLORS.get(state, C_CYAN)
        hexcol = _hex(col)
        labels = STATE_LABELS.get(state, ("", ""))
        if not self._paused:
            self._status_main.setText(labels[0])
            self._status_main.setStyleSheet(
                f"color:{hexcol}80; background:transparent; letter-spacing:2px;"
            )
            self._status_sub.setText(f"// {labels[1]}")
            self._status_sub.setStyleSheet(
                f"color:{hexcol}50; background:transparent;"
            )
            self._lvl_val.setStyleSheet(f"color:{hexcol}80; background:transparent;")
        if state in ("listening", "processing", "speaking"):
            self._on_show(0); self._hide_timer.stop()
        elif state == "idle" and not self._pinned:
            self._schedule_hide(self.HIDE_IDLE_MS)
        self.update()

    def _on_set_mode(self, name):
        self._mode_name = name or "Normal"
        self._mode_btn.setText(f"MODE  {self._mode_name.upper()} ▾")

    def _on_set_transcript(self, text):
        self._user_lbl.setText(f"> VOUS  {text}" if text else "")

    def _on_set_response(self, text):
        self._resp_lbl.setText(text or "")

    def _on_set_source(self, source):
        self._cur_source = source
        badge = SOURCE_BADGES.get(source)
        if badge:
            sym, col = badge
            self._badge_btn.setText(sym)
            self._badge_btn.setStyleSheet(
                f"QPushButton {{ background:#060e1c; color:{_hex(col)};"
                f" border:1px solid {_hex(col)}60; border-radius:2px; padding:0 5px; }}"
            )
            self._badge_btn.show()
        else:
            self._badge_btn.hide()
        self._refresh_cost()

    def _on_set_cost(self, last_usd, month_usd, calls):
        self._last_cost   = last_usd
        self._month_cost  = month_usd
        self._month_calls = calls
        self._tokens_total = self._tokens_total  # keep
        self._refresh_cost()

    def _refresh_cost(self):
        EUR = 0.92
        last_e  = self._last_cost  * EUR
        month_e = self._month_cost * EUR

        def fmt(e):
            if e < 0.01: return f"{e*100:.4f}c €"
            if e < 1:    return f"{e*100:.3f}c €"
            return f"{e:.4f} €"

        parts = []
        if self._last_cost > 0:  parts.append(f"COÛT {fmt(last_e)}")
        if self._month_cost > 0: parts.append(f"SESSION {fmt(month_e)}")
        if self._month_calls > 0: parts.append(f"APPELS {self._month_calls}")
        self._cost_lbl.setText("  ·  ".join(parts))

    def _on_update_diag(self, cpu, mem, lat, tokens, model, uptime):
        self._tokens_total = tokens
        self._diag.update_diag(cpu, mem, lat, tokens, model, uptime)


# ── Public API ────────────────────────────────────────────────────────────────
class JarvisOverlay:
    HIDE_AFTER_IDLE = _JarvisWindow.HIDE_IDLE_MS
    HIDE_AFTER_TRAY = _JarvisWindow.HIDE_TRAY_MS

    def __init__(self):
        self._app          = None
        self._win          = None
        self._sig          = None
        self._input_queue  = queue.Queue()
        self._tray_icon    = None
        self.on_mode_change = None

    def start(self):
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._sig = _Signals()
        self._win = _JarvisWindow(self._sig, self._input_queue, self)

    def exec(self):
        if self._app: self._app.exec()

    def show(self, duration_ms=None):
        if self._sig:
            self._sig.do_show.emit(
                duration_ms if duration_ms is not None else self.HIDE_AFTER_IDLE
            )

    def set_state(self, state):
        if self._sig: self._sig.do_set_state.emit(state)

    def set_mode(self, name):
        if self._sig: self._sig.do_set_mode.emit(name or "Normal")

    def set_transcript(self, text):
        if self._sig: self._sig.do_set_transcript.emit(text or "")

    def set_response(self, text):
        if self._sig: self._sig.do_set_response.emit(text or "")

    def set_source(self, source):
        if self._sig: self._sig.do_set_source.emit(source or "")

    def set_cost(self, last_usd, month_usd, calls):
        if self._sig: self._sig.do_set_cost.emit(last_usd, month_usd, calls)

    def set_paused(self, paused):
        if self._sig: self._sig.do_set_paused.emit(paused)

    def update_diagnostics(self, cpu=0, mem=0, lat=0, tokens=0, model="haiku-4.5", uptime=""):
        if self._sig:
            self._sig.do_update_diag.emit(cpu, mem, lat, tokens, model, uptime)

    def is_muted(self):
        return self._win._muted if self._win else False

    def get_text_input_nowait(self):
        try: return self._input_queue.get_nowait()
        except queue.Empty: return None


overlay = JarvisOverlay()


# ── Preview standalone ────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        import psutil
    except ImportError:
        pass

    app = QApplication(sys.argv)
    sig = _Signals()
    iq  = queue.Queue()
    win = _JarvisWindow(sig, iq, None)
    win.show()

    states = ["idle", "listening", "processing", "speaking", "error", "idle"]
    idx = [0]

    def next_state():
        s = states[idx[0] % len(states)]
        sig.do_set_state.emit(s)
        if s == "listening":
            sig.do_set_transcript.emit("Jarvis, tu m'entends ?")
        elif s == "processing":
            sig.do_set_source.emit("ai")
            sig.do_set_transcript.emit("Analyse les derniers logs serveur.")
            sig.do_set_response.emit("Compilation du rapport en cours…")
        elif s == "speaking":
            sig.do_set_source.emit("direct")
            sig.do_set_transcript.emit("Quelle est la météo à Paris ?")
            sig.do_set_response.emit("Ciel dégagé, 14°C. Un bon temp…")
            sig.do_set_cost.emit(0.000024, 0.0187, 14)
        elif s == "error":
            sig.do_set_source.emit("")
            sig.do_set_transcript.emit("Lance une recherche.")
            sig.do_set_response.emit("Liaison satellite interrompue. Nouvelle tentative dans 3s.")
        elif s == "idle":
            sig.do_set_source.emit("cache")
            sig.do_set_response.emit("Systèmes nominaux. En attente d'instructions.")
        idx[0] += 1

    t = QTimer(); t.setInterval(2500); t.timeout.connect(next_state); t.start()
    next_state()
    sys.exit(app.exec())
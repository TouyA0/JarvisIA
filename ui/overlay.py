"""
Floating overlay Jarvis — HUD style
- Alt + drag pour déplacer
- Auto-hide 3s après retour en veille (15s depuis le tray)
- Pin pour garder visible en permanence
- Sélecteur de mode cliquable (badge en haut à droite)
- Pause / Mute TTS / Send
"""
import tkinter as tk
import threading
import queue
import math
import random
import json
import pathlib

_ROOT = pathlib.Path(__file__).parent.parent
MODES_FILE = _ROOT / "brain" / "modes" / "modes.json"

# Palette HUD
BG        = "#0a0e1a"
BG_INPUT  = "#141a2a"
BG_HOVER  = "#1a2535"
FG_TITLE  = "#4dd0e1"
FG_DIM    = "#7a8899"
FG_TEXT   = "#e0e6ed"
FG_WARN   = "#ff9800"
FG_PAUSE  = "#e53935"

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

# Tokens spéciaux dans la queue pour contrôler Jarvis depuis l'overlay
TOKEN_PAUSE  = "__PAUSE__"
TOKEN_RESUME = "__RESUME__"


def _fmt_money(usd):
    if usd is None:
        return "—"
    eur = usd * USD_TO_EUR
    if eur < 0.01:
        return f"{eur * 100:.2f}c€"
    if eur < 1:
        return f"{eur * 100:.1f}c€"
    return f"{eur:.2f}€"

def _load_modes():
    try:
        with open(MODES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f).get("modes", [])
    except Exception:
        return []


class JarvisOverlay:

    HIDE_AFTER_IDLE  = 3_000   # ms après retour en veille
    HIDE_AFTER_TRAY  = 15_000  # ms après clic sur le tray

    def __init__(self):
        self.root = None
        self._ready = threading.Event()

        # État Jarvis
        self.state          = "idle"
        self.mode_name      = "Normal"
        self._paused        = False
        self._mute_tts      = False
        self._pinned        = False
        self._mouse_inside  = False

        # Animation
        self._anim_phase  = 0.0
        self._wave_amps   = [0.0] * 30

        # Auto-hide
        self._hide_timer_id = None

        # Coût
        self._last_cost_usd  = 0.0
        self._month_cost_usd = 0.0
        self._month_calls    = 0
        self._current_source = None

        # File d'entrée (texte + tokens de contrôle)
        self._input_queue = queue.Queue()

        # Callbacks définis par jarvis.py
        self.on_mode_change = None   # callable(mode_id)

        self._started    = False
        self._start_lock = threading.Lock()

    # ------------------------------------------------------------------ lifecycle

    def start(self):
        with self._start_lock:
            if self._started:
                return
            self._started = True
        t = threading.Thread(target=self._run, daemon=True)
        t.start()
        self._ready.wait(timeout=4.0)

    def _run(self):
        try:
            self.root = tk.Tk()
            self._build_window()
            self._build_ui()
            self._animate()
            self._ready.set()
            self.root.mainloop()
        except Exception as e:
            print(f"[overlay] Erreur: {e}")
            self._ready.set()

    def _build_window(self):
        r = self.root
        r.title("Jarvis")
        r.overrideredirect(True)
        r.attributes("-topmost", True)
        r.attributes("-alpha", 0.92)
        r.configure(bg=BG)

        sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
        r.geometry(f"360x265+{sw - 400}+{int(sh * 0.38)}")

        # Départ caché — s'affiche au premier événement
        r.withdraw()

        # Suivi survol pour annuler l'auto-hide
        r.bind("<Enter>", self._on_enter)
        r.bind("<Leave>", self._on_leave)

    def _build_ui(self):
        r = self.root

        # ── Barre de titre ──────────────────────────────────────────────
        bar = tk.Frame(r, bg=BG)
        bar.pack(fill="x", padx=2, pady=(5, 0))

        self.title_lbl = tk.Label(bar, text="J.A.R.V.I.S.",
                                   fg=FG_TITLE, bg=BG,
                                   font=("Consolas", 11, "bold"))
        self.title_lbl.pack(side="left", padx=8)

        # Bouton Pin
        self.pin_btn = tk.Label(bar, text="⊙", fg=FG_DIM, bg=BG,
                                 font=("Consolas", 13), cursor="hand2")
        self.pin_btn.pack(side="right", padx=(0, 8))
        self.pin_btn.bind("<Button-1>", self._toggle_pin)

        # Badge mode cliquable
        self.mode_btn = tk.Label(bar,
                                  text=f"{self.mode_name.upper()} ▾",
                                  fg=FG_DIM, bg=BG,
                                  font=("Consolas", 8, "bold"),
                                  cursor="hand2")
        self.mode_btn.pack(side="right", padx=(0, 6))
        self.mode_btn.bind("<Button-1>", self._show_mode_menu)

        # Alt + drag sur toute la barre
        for w in (bar, self.title_lbl):
            w.bind("<Alt-ButtonPress-1>", self._drag_start)
            w.bind("<Alt-B1-Motion>",     self._drag_move)

        # ── Canvas animation ─────────────────────────────────────────────
        self.canvas = tk.Canvas(r, bg=BG, height=62,
                                 highlightthickness=0, bd=0)
        self.canvas.pack(fill="x", padx=12, pady=(6, 2))

        # ── Label état ───────────────────────────────────────────────────
        self.status_lbl = tk.Label(r, text=STATE_LABELS["idle"],
                                    fg=FG_TITLE, bg=BG,
                                    font=("Consolas", 10))
        self.status_lbl.pack(pady=(2, 4))

        # ── Transcription utilisateur ─────────────────────────────────────
        self.user_lbl = tk.Label(r, text="", fg=FG_DIM, bg=BG,
                                  font=("Consolas", 8),
                                  wraplength=336, justify="left", anchor="w")
        self.user_lbl.pack(fill="x", padx=12)

        # ── Réponse Jarvis + badge source ─────────────────────────────────
        resp_frame = tk.Frame(r, bg=BG)
        resp_frame.pack(fill="x", padx=12, pady=(2, 2))

        self.source_lbl = tk.Label(resp_frame, text="", fg=FG_DIM, bg=BG,
                                    font=("Consolas", 11, "bold"),
                                    width=2, anchor="n")
        self.source_lbl.pack(side="left", padx=(0, 4), anchor="n")

        self.jarvis_lbl = tk.Label(resp_frame, text="", fg=FG_TEXT, bg=BG,
                                    font=("Consolas", 9), wraplength=310,
                                    justify="left", anchor="w")
        self.jarvis_lbl.pack(side="left", fill="x", expand=True)

        # ── Footer coût ───────────────────────────────────────────────────
        self.cost_lbl = tk.Label(r, text="", fg=FG_DIM, bg=BG,
                                  font=("Consolas", 8), anchor="w")
        self.cost_lbl.pack(fill="x", padx=12, pady=(0, 2))

        # ── Barre du bas ──────────────────────────────────────────────────
        bottom = tk.Frame(r, bg=BG)
        bottom.pack(side="bottom", fill="x", padx=10, pady=8)

        # Champ texte
        self.entry = tk.Entry(bottom, bg=BG_INPUT, fg=FG_TEXT,
                               insertbackground=FG_TITLE, relief="flat",
                               font=("Consolas", 10))
        self.entry.pack(side="left", fill="x", expand=True, ipady=5)
        self.entry.bind("<Return>", self._on_send)

        # Envoyer ▶
        self.send_btn = tk.Button(bottom, text="▶", width=2, relief="flat",
                                   bg=BG_INPUT, fg=FG_TITLE,
                                   activebackground=BG_HOVER,
                                   font=("Consolas", 10, "bold"),
                                   cursor="hand2", command=self._on_send)
        self.send_btn.pack(side="left", padx=(4, 0))

        # Pause ⏸
        self.pause_btn = tk.Button(bottom, text="⏸", width=2, relief="flat",
                                    bg=BG_INPUT, fg=FG_DIM,
                                    activebackground=BG_HOVER,
                                    font=("Consolas", 10),
                                    cursor="hand2", command=self._toggle_pause)
        self.pause_btn.pack(side="left", padx=(4, 0))

        # Mute TTS ♪
        self.mute_btn = tk.Button(bottom, text="♪", width=2, relief="flat",
                                   bg=BG_INPUT, fg=FG_TITLE,
                                   activebackground=BG_HOVER,
                                   font=("Consolas", 10),
                                   cursor="hand2", command=self._toggle_mute)
        self.mute_btn.pack(side="left", padx=(4, 0))

    # ------------------------------------------------------------------ drag (Alt seulement)

    def _drag_start(self, e):
        self._drag_dx = e.x_root - self.root.winfo_x()
        self._drag_dy = e.y_root - self.root.winfo_y()

    def _drag_move(self, e):
        self.root.geometry(
            f"+{e.x_root - self._drag_dx}+{e.y_root - self._drag_dy}")

    # ------------------------------------------------------------------ survol

    def _on_enter(self, e):
        self._mouse_inside = True
        self._cancel_hide()

    def _on_leave(self, e):
        self._mouse_inside = False
        if not self._pinned and self.state == "idle":
            self._schedule_hide(self.HIDE_AFTER_IDLE)

    # ------------------------------------------------------------------ auto-hide

    def show(self, duration_ms=None):
        """Thread-safe. Affiche l'overlay pour duration_ms ms (défaut = HIDE_AFTER_IDLE)."""
        d = duration_ms
        self._ui_call(lambda: self._show_internal(d))

    def _show_internal(self, duration_ms=None):
        self.root.deiconify()
        self.root.lift()
        if not self._pinned:
            self._schedule_hide(
                duration_ms if duration_ms is not None else self.HIDE_AFTER_IDLE)

    def _schedule_hide(self, delay_ms):
        self._cancel_hide()
        self._hide_timer_id = self.root.after(delay_ms, self._check_and_hide)

    def _cancel_hide(self):
        if self._hide_timer_id is not None:
            try:
                self.root.after_cancel(self._hide_timer_id)
            except Exception:
                pass
            self._hide_timer_id = None

    def _check_and_hide(self):
        self._hide_timer_id = None
        if not self._pinned and not self._mouse_inside:
            self.root.withdraw()

    # ------------------------------------------------------------------ pin

    def _toggle_pin(self, e=None):
        self._pinned = not self._pinned
        if self._pinned:
            self._cancel_hide()
            self.pin_btn.config(text="⊕", fg=FG_TITLE)
        else:
            self.pin_btn.config(text="⊙", fg=FG_DIM)
            if self.state == "idle":
                self._schedule_hide(self.HIDE_AFTER_IDLE)

    # ------------------------------------------------------------------ pause

    def _toggle_pause(self):
        if self._paused:
            # Reprendre
            self._paused = False
            self.pause_btn.config(text="⏸", fg=FG_DIM)
            self._input_queue.put(TOKEN_RESUME)
        else:
            # Mettre en pause
            self._paused = True
            self.pause_btn.config(text="▶", fg=FG_WARN)
            self.status_lbl.config(text="En pause.", fg=FG_PAUSE)
            self._input_queue.put(TOKEN_PAUSE)

    def set_paused(self, paused: bool):
        """Synchronise le bouton depuis jarvis.py (ex : pause vocale)."""
        self._paused = paused
        self._ui_call(lambda: self._sync_pause_btn())

    def _sync_pause_btn(self):
        if self._paused:
            self.pause_btn.config(text="▶", fg=FG_WARN)
            self.status_lbl.config(text="En pause.", fg=FG_PAUSE)
        else:
            self.pause_btn.config(text="⏸", fg=FG_DIM)

    # ------------------------------------------------------------------ mute TTS

    def _toggle_mute(self):
        self._mute_tts = not self._mute_tts
        self.mute_btn.config(
            text="♪" if not self._mute_tts else "∅",
            fg=FG_TITLE if not self._mute_tts else FG_PAUSE)

    def is_muted(self):
        return self._mute_tts

    # ------------------------------------------------------------------ sélecteur de mode

    def _show_mode_menu(self, event):
        modes = _load_modes()
        if not modes:
            return
        menu = tk.Menu(self.root, tearoff=0,
                       bg=BG_INPUT, fg=FG_TEXT,
                       activebackground="#1f3a5c", activeforeground=FG_TEXT,
                       relief="flat", font=("Consolas", 9),
                       bd=0)
        for mode in modes:
            mode_id   = mode["id"]
            mode_name = mode["name"].replace("Mode ", "")
            def _cb(mid=mode_id, mname=mode_name):
                self.set_mode(mname)
                if self.on_mode_change:
                    threading.Thread(
                        target=self.on_mode_change, args=(mid,),
                        daemon=True).start()
            active = (mode_name.lower() == self.mode_name.lower())
            label = f"{'▶ ' if active else '   '}{mode['name']}"
            menu.add_command(label=label, command=_cb)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    # ------------------------------------------------------------------ input texte

    def _on_send(self, event=None):
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, tk.END)
        self._input_queue.put(text)
        # Garder l'overlay visible pendant le traitement
        self._cancel_hide()
        self._show_internal()

    # ------------------------------------------------------------------ animation

    def _animate(self):
        if not self.root:
            return
        self._anim_phase += 0.18
        self.canvas.delete("all")
        w  = self.canvas.winfo_width() or 336
        h  = 62
        cx, cy = w / 2, h / 2
        color = STATE_COLORS.get(self.state, FG_TITLE)
        s = self.state

        if s == "idle":
            pulse    = (math.sin(self._anim_phase * 0.6) + 1) / 2
            r_outer  = 10 + pulse * 5
            r_inner  = 5  + pulse * 2
            self.canvas.create_oval(cx - r_outer, cy - r_outer,
                                     cx + r_outer, cy + r_outer,
                                     outline=color, width=1)
            self.canvas.create_oval(cx - r_inner, cy - r_inner,
                                     cx + r_inner, cy + r_inner,
                                     fill=color, outline="")

        elif s == "listening":
            n, bw, gap = 24, 6, 3
            start_x = cx - (n * (bw + gap) - gap) / 2
            for i in range(n):
                target = (abs(math.sin(self._anim_phase * 1.2 + i * 0.45))
                          * random.uniform(0.3, 1.0) * 22)
                self._wave_amps[i] = self._wave_amps[i] * 0.6 + target * 0.4
                bh = max(2, self._wave_amps[i])
                x = start_x + i * (bw + gap)
                self.canvas.create_rectangle(x, cy - bh, x + bw, cy + bh,
                                              fill=color, outline="")

        elif s == "processing":
            for i in range(8):
                angle = self._anim_phase * 2 + i * math.pi / 4
                x = cx + math.cos(angle) * 16
                y = cy + math.sin(angle) * 16
                r = 2 + (i + 1) / 8 * 2
                self.canvas.create_oval(x - r, y - r, x + r, y + r,
                                         fill=color, outline="")

        elif s == "speaking":
            pts = []
            for i in range(50):
                x   = cx - 140 + i * (280 / 49)
                amp = (math.sin(self._anim_phase * 1.5 + i * 0.35)
                       * math.sin(self._anim_phase * 0.6 + i * 0.12) * 18)
                pts.extend([x, cy + amp])
            self.canvas.create_line(pts, fill=color, width=2, smooth=True)

        elif s == "error":
            blink = (math.sin(self._anim_phase * 4) + 1) / 2
            r = 10 + blink * 4
            self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r,
                                     fill=color, outline="")

        self.root.after(30, self._animate)

    # ------------------------------------------------------------------ API publique (thread-safe)

    def _ui_call(self, fn):
        if not self.root:
            return
        try:
            self.root.after(0, fn)
        except Exception:
            pass

    def set_state(self, state):
        if state not in STATE_COLORS:
            return
        self.state = state
        color = STATE_COLORS[state]
        label = STATE_LABELS.get(state, "")
        self._ui_call(lambda: self.status_lbl.config(text=label, fg=color))

        if state in ("listening", "processing", "speaking"):
            self.show()
        elif state == "idle" and not self._pinned:
            self._ui_call(lambda: self._schedule_hide(self.HIDE_AFTER_IDLE))

    def set_mode(self, mode_name):
        self.mode_name = mode_name or "Normal"
        n = self.mode_name.upper()
        self._ui_call(lambda: self.mode_btn.config(text=f"{n} ▾"))

    def set_transcript(self, text):
        display = f"> {text}" if text else ""
        self._ui_call(lambda: self.user_lbl.config(text=display))

    def set_response(self, text):
        self._ui_call(lambda: self.jarvis_lbl.config(text=text or ""))
        self._refresh_footer()

    def set_source(self, source):
        self._current_source = source
        badge = SOURCE_BADGES.get(source)
        if badge:
            sym, col = badge
            self._ui_call(lambda: self.source_lbl.config(text=sym, fg=col))
        else:
            self._ui_call(lambda: self.source_lbl.config(text=""))
        self._refresh_footer()

    def set_cost(self, last_usd, month_usd, month_calls):
        self._last_cost_usd  = last_usd
        self._month_cost_usd = month_usd
        self._month_calls    = month_calls
        self._refresh_footer()

    def _refresh_footer(self):
        src = self._current_source
        if src == "ai":
            prefix, color = f"⚡ IA · {_fmt_money(self._last_cost_usd)}", FG_WARN
        elif src == "cache":
            prefix, color = "● cache · 0ms", "#4dd0e1"
        elif src == "direct":
            prefix, color = "◆ local · 0ms", "#ab9ff2"
        else:
            prefix, color = "", FG_DIM

        month = (f"   Mois : {_fmt_money(self._month_cost_usd)}"
                 f" · {self._month_calls} appels"
                 if self._month_calls > 0 else "")
        text = (prefix + month) if prefix else month.strip()
        self._ui_call(lambda: self.cost_lbl.config(
            text=text, fg=color if prefix else FG_DIM))

    def get_text_input_nowait(self):
        """Retourne le prochain token de la queue (texte ou TOKEN_PAUSE/TOKEN_RESUME), ou None."""
        try:
            return self._input_queue.get_nowait()
        except queue.Empty:
            return None


overlay = JarvisOverlay()

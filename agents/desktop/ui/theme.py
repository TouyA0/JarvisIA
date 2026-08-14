"""Thème visuel du HUD — palette Iron Man (cyan froid / or / navy profond)."""
from __future__ import annotations

from PyQt6.QtGui import QColor

# ── Palette ───────────────────────────────────────────────────────────────────
C_BG        = QColor(3,   9,   18)     # fond principal
C_BG2       = QColor(6,   15,  28)     # fond panneaux
C_PANEL     = QColor(8,   22,  38, 130)
C_GRID      = QColor(0,   190, 230, 10)
C_HEX       = QColor(0,   190, 230, 7)

C_CYAN      = QColor(0,   229, 255)    # accent principal
C_CYAN_HI   = QColor(140, 246, 255)    # surbrillance
C_CYAN_DIM  = QColor(0,   140, 175, 150)
C_GOLD      = QColor(255, 194, 61)
C_RED       = QColor(255, 77,  77)
C_GREEN     = QColor(57,  229, 140)
C_VIOLET    = QColor(168, 130, 255)
C_WHITE     = QColor(240, 252, 255)

C_TEXT      = QColor(159, 216, 232)    # texte courant
C_TEXT_DIM  = QColor(70,  110, 135)    # texte secondaire
C_TEXT_FAINT= QColor(38,  62,  82)     # texte discret
C_USER      = QColor(255, 210, 125)    # messages de Monsieur

FONT = "Consolas"

STATE_COLORS = {
    "idle":       C_CYAN_DIM,
    "listening":  C_CYAN,
    "processing": C_GOLD,
    "speaking":   C_GREEN,
    "error":      C_RED,
}
STATE_LABELS = {
    "idle":       ("EN VEILLE",     "STANDBY"),
    "listening":  ("ÉCOUTE ACTIVE", "LISTENING"),
    "processing": ("TRAITEMENT",    "PROCESSING"),
    "speaking":   ("TRANSMISSION",  "SPEAKING"),
    "error":      ("ERREUR",        "FAULT"),
}
SOURCE_BADGES = {
    "cache":  ("◉ CACHE",  C_CYAN),
    "direct": ("◆ LOCAL",  C_VIOLET),
    "ollama": ("⌂ OLLAMA", C_GREEN),
    "ai":     ("⚡ CLAUDE", C_GOLD),
}


def hexa(c: QColor) -> str:
    """QColor → #rrggbb (rich text Qt : pas d'alpha supporté)."""
    return f"#{c.red():02x}{c.green():02x}{c.blue():02x}"


def rgba_css(c: QColor, alpha: float) -> str:
    """QColor → rgba(r,g,b,a) pour les stylesheets Qt (alpha 0.0-1.0)."""
    return f"rgba({c.red()},{c.green()},{c.blue()},{alpha:.2f})"


def dim(c: QColor, factor: int = 160) -> str:
    """Variante assombrie en #rrggbb — pour simuler l'alpha en rich text."""
    return hexa(QColor(c).darker(factor))


def with_alpha(c: QColor, alpha: int) -> QColor:
    out = QColor(c)
    out.setAlpha(alpha)
    return out


def mix(a: QColor, b: QColor, t: float) -> QColor:
    """Interpolation linéaire a→b (t dans [0,1]) — transitions d'état fluides."""
    t = min(1.0, max(0.0, t))
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
        round(a.alpha() + (b.alpha() - a.alpha()) * t),
    )

"""Jetons de session à courte durée pour la Console web (P4).

Le mot de passe (CONSOLE_PASSWORD) n'est plus jamais utilisé comme jeton
d'API : il ne sert qu'une fois, à l'échange contre un jeton de session via
POST /api/session (voir brain/server.py). Seul ce jeton voyage ensuite —
en en-tête Authorization pour l'API REST, en paramètre de requête pour le
handshake WebSocket (aucun en-tête custom possible depuis un navigateur à
ce stade). Contrairement au mot de passe, il est borné dans le temps,
révocable, et sans valeur au-delà de cette Console — sa présence en clair
dans les logs d'accès uvicorn (inhérente à l'URL du WebSocket) n'expose
donc plus le secret permanent.
"""
from __future__ import annotations

import hmac
import secrets
import time

_TTL_S = 12 * 3600  # 12h : une session d'usage, pas un secret à durée de vie du serveur
_tokens: dict[str, float] = {}  # token -> expiration (epoch)

_MAX_ATTEMPTS = 5
_WINDOW_S = 15 * 60
_attempts: dict[str, list[float]] = {}  # ip -> horodatages des échecs récents


def issue() -> tuple[str, float]:
    """Émet un nouveau jeton de session. `secrets.token_urlsafe` (CSPRNG),
    pas un simple id — un jeton devinable court-circuiterait toute la
    protection par mot de passe."""
    token = secrets.token_urlsafe(32)
    expires_at = time.time() + _TTL_S
    _tokens[token] = expires_at
    return token, expires_at


def verify(token: str) -> bool:
    if not token:
        return False
    expires_at = _tokens.get(token)
    if expires_at is None:
        return False
    if expires_at < time.time():
        del _tokens[token]
        return False
    return True


def check_password(password: str, expected: str) -> bool:
    """`hmac.compare_digest` plutôt que `!=` : une comparaison naïve fuite
    la longueur du préfixe correct par le temps de réponse, exploitable à
    distance sur un mot de passe fixe (P4)."""
    return hmac.compare_digest(password, expected)


def rate_limited(ip: str) -> bool:
    """True si `ip` a dépassé le nombre de tentatives échouées autorisées
    dans la fenêtre glissante — jusqu'ici aucune limite n'existait,
    laissant CONSOLE_PASSWORD attaquable par force brute (P4)."""
    now = time.time()
    attempts = [t for t in _attempts.get(ip, []) if now - t < _WINDOW_S]
    _attempts[ip] = attempts
    return len(attempts) >= _MAX_ATTEMPTS


def record_failure(ip: str) -> None:
    _attempts.setdefault(ip, []).append(time.time())

"""Gestion des flux micro PyAudio.

Deux flux persistants :
  - main      : wake word + transcription (chunks de 256)
  - interrupt : détection de barge-in pendant que Jarvis parle (chunks de 512).
    Persistant pour éviter 50-200 ms d'initialisation à chaque prise de parole.
"""
from __future__ import annotations

import numpy as np


class MicStream:
    def __init__(self, rate: int = 16000, frames: int = 256):
        self._rate = rate
        self._frames = frames
        self._pa = None
        self._stream = None

    def open(self) -> None:
        import pyaudio
        self._pa = pyaudio.PyAudio()
        self._stream = self._pa.open(
            format=pyaudio.paInt16, channels=1, rate=self._rate,
            input=True, frames_per_buffer=self._frames,
        )

    def read(self, n: int) -> np.ndarray:
        """Lit n échantillons int16. Rouvre le flux si le périphérique a décroché
        (casque débranché, changement de périphérique par Windows)."""
        try:
            data = self._stream.read(n, exception_on_overflow=False)
        except OSError:
            print("[Audio] Flux micro perdu — réouverture...")
            self.close()
            self.open()
            data = self._stream.read(n, exception_on_overflow=False)
        return np.frombuffer(data, dtype=np.int16)

    def flush(self) -> None:
        """Vide le buffer accumulé pendant que le flux n'était pas consommé
        (typiquement pendant que Jarvis parlait)."""
        if self._stream is None:
            return
        try:
            available = self._stream.get_read_available()
            if available > 0:
                self._stream.read(available, exception_on_overflow=False)
        except OSError:
            pass

    def close(self) -> None:
        try:
            if self._stream:
                self._stream.stop_stream()
                self._stream.close()
            if self._pa:
                self._pa.terminate()
        except Exception:
            pass
        self._stream = None
        self._pa = None

    @property
    def raw(self):
        return self._stream


main = MicStream(rate=16000, frames=256)
interrupt = MicStream(rate=16000, frames=512)


def init_all() -> None:
    main.open()
    interrupt.open()


def close_all() -> None:
    main.close()
    interrupt.close()

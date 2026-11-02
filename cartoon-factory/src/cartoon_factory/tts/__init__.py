"""Backends TTS français locaux derrière une interface commune.

    backend = get_backend("kokoro", cfg.tts)
    backend.synthesize("Bonjour !", Path("s01.wav"))

Chaque backend produit un wav (n'importe quel taux d'échantillonnage) ; le
pipeline le normalise ensuite (mono, 48 kHz, loudnorm). Les modèles lourds
sont chargés paresseusement et une seule fois par process.
"""

from __future__ import annotations

from cartoon_factory.config import TTSConfig
from cartoon_factory.tts.base import TTSBackend, TTSError

BACKENDS = ("kokoro", "xtts", "espeak", "silence")


def get_backend(name: str, cfg: TTSConfig) -> TTSBackend:
    """Fabrique le backend demandé (import paresseux : pas de torch au démarrage)."""
    if name == "kokoro":
        from cartoon_factory.tts.kokoro_backend import KokoroBackend

        return KokoroBackend(**cfg.kokoro)
    if name == "xtts":
        from cartoon_factory.tts.xtts_backend import XTTSBackend

        return XTTSBackend(**cfg.xtts)
    if name == "espeak":
        from cartoon_factory.tts.espeak_backend import EspeakBackend

        return EspeakBackend(**cfg.espeak)
    if name == "silence":
        from cartoon_factory.tts.silence_backend import SilenceBackend

        return SilenceBackend(words_per_minute=cfg.words_per_minute)
    raise TTSError(f"backend TTS inconnu « {name} » (choix : {', '.join(BACKENDS)})")


__all__ = ["BACKENDS", "TTSBackend", "TTSError", "get_backend"]

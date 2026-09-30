"""Kokoro-82M : TTS léger (CPU ok), voix françaises `ff_*`.

Installation : `pip install kokoro soundfile "misaki[fr]"` + `apt install espeak-ng`
(Kokoro s'appuie sur espeak-ng pour la phonémisation du français).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cartoon_factory.tts.base import TTSBackend, TTSError


class KokoroBackend(TTSBackend):
    name = "kokoro"
    SAMPLE_RATE = 24000

    def __init__(self, voice: str = "ff_siwis", speed: float = 1.0, **_: Any):
        self.voice = voice
        self.speed = float(speed)
        self._pipeline = None

    def _load(self):
        if self._pipeline is None:
            try:
                from kokoro import KPipeline  # type: ignore
            except ImportError as exc:
                raise TTSError("Kokoro absent : pip install kokoro soundfile 'misaki[fr]'") from exc
            self._pipeline = KPipeline(lang_code="f")  # « f » = français
        return self._pipeline

    def synthesize(self, text: str, out_wav: Path) -> Path:
        import numpy as np
        import soundfile as sf  # type: ignore

        pipeline = self._load()
        chunks = [audio for _, _, audio in pipeline(text, voice=self.voice, speed=self.speed)]
        if not chunks:
            raise TTSError("Kokoro n'a rien produit")
        audio = np.concatenate([np.asarray(c) for c in chunks])
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(out_wav), audio, self.SAMPLE_RATE)
        return out_wav

    def params(self) -> dict[str, Any]:
        return {"backend": self.name, "voice": self.voice, "speed": self.speed}

    def release(self) -> None:
        self._pipeline = None
        try:
            import torch  # type: ignore

            torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001
            pass

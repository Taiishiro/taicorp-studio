"""XTTS-v2 (Coqui TTS) : voix plus naturelle, clonage à partir d'un wav de 6-10 s.

Installation : `pip install TTS` (PyTorch requis ; ~2 Go de VRAM en fp16).
Le modèle est téléchargé au premier appel dans ~/.local/share/tts/.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cartoon_factory.tts.base import TTSBackend, TTSError


class XTTSBackend(TTSBackend):
    name = "xtts"

    def __init__(self, model: str = "tts_models/multilingual/multi-dataset/xtts_v2",
                 speaker_wav: str = "", language: str = "fr", **_: Any):
        self.model_name = model
        self.speaker_wav = speaker_wav
        self.language = language
        self._tts = None

    def _load(self):
        if self._tts is None:
            try:
                from TTS.api import TTS  # type: ignore
            except ImportError as exc:
                raise TTSError("Coqui TTS absent : pip install TTS") from exc
            gpu = False
            try:
                import torch  # type: ignore

                gpu = torch.cuda.is_available()
            except Exception:  # noqa: BLE001
                pass
            self._tts = TTS(self.model_name).to("cuda" if gpu else "cpu")
        return self._tts

    def synthesize(self, text: str, out_wav: Path) -> Path:
        tts = self._load()
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        kwargs: dict[str, Any] = {"text": text, "language": self.language,
                                  "file_path": str(out_wav)}
        if self.speaker_wav:
            kwargs["speaker_wav"] = self.speaker_wav
        else:
            # XTTS exige un speaker : on prend le premier speaker intégré.
            speakers = getattr(tts, "speakers", None) or []
            if speakers:
                kwargs["speaker"] = speakers[0]
        tts.tts_to_file(**kwargs)
        return out_wav

    def params(self) -> dict[str, Any]:
        return {"backend": self.name, "model": self.model_name,
                "speaker_wav": self.speaker_wav, "language": self.language}

    def release(self) -> None:
        self._tts = None
        try:
            import torch  # type: ignore

            torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001
            pass

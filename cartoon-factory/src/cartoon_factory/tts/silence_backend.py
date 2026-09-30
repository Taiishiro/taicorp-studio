"""Silence calibré : durée estimée depuis le nombre de mots (dry-run, tests)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cartoon_factory.media import write_silence
from cartoon_factory.tts.base import TTSBackend


class SilenceBackend(TTSBackend):
    name = "silence"

    def __init__(self, words_per_minute: int = 150, **_: Any):
        self.wpm = max(60, int(words_per_minute))

    def estimate(self, text: str) -> float:
        return max(1.0, len(text.split()) / self.wpm * 60)

    def synthesize(self, text: str, out_wav: Path) -> Path:
        return write_silence(out_wav, self.estimate(text))

    def params(self) -> dict[str, Any]:
        return {"backend": self.name, "wpm": self.wpm}

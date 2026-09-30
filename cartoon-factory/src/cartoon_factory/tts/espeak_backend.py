"""espeak-ng : voix robotique mais instantanée et 100 % CPU.

Sert de repli (machine sans GPU, CI, démo) et de « voix témoin » pour caler
les durées avant de lancer Kokoro/XTTS. `sudo apt install espeak-ng`.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from cartoon_factory.tts.base import TTSBackend, TTSError


class EspeakBackend(TTSBackend):
    name = "espeak"

    def __init__(self, voice: str = "fr", speed: int = 150, **_: Any):
        self.voice = voice
        self.speed = int(speed)
        self.bin = shutil.which("espeak-ng") or shutil.which("espeak")

    def synthesize(self, text: str, out_wav: Path) -> Path:
        if not self.bin:
            raise TTSError("espeak-ng introuvable : sudo apt install espeak-ng")
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        cmd = [self.bin, "-v", self.voice, "-s", str(self.speed), "-w", str(out_wav), "--", text]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0 or not out_wav.exists():
            raise TTSError(f"espeak-ng a échoué : {proc.stderr.strip()}")
        return out_wav

    def params(self) -> dict[str, Any]:
        return {"backend": self.name, "voice": self.voice, "speed": self.speed}

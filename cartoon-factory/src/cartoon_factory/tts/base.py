"""Interface commune des backends TTS."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class TTSError(RuntimeError):
    pass


class TTSBackend(ABC):
    name: str = "base"

    @abstractmethod
    def synthesize(self, text: str, out_wav: Path) -> Path:
        """Synthétise `text` (français) dans `out_wav` et retourne le chemin."""

    def params(self) -> dict[str, Any]:
        """Paramètres qui entrent dans l'empreinte de cache (voix, vitesse…)."""
        return {"backend": self.name}

    def release(self) -> None:  # noqa: B027 — no-op par défaut, surchargé par les backends GPU
        """Libère la VRAM/RAM du modèle (appelé en fin d'étape)."""

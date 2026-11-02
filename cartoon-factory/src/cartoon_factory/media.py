"""Helpers ffmpeg : localisation du binaire, durées, encodage commun.

ffmpeg est cherché dans le PATH, puis dans `imageio-ffmpeg` (binaire statique
embarqué) — utile dans les environnements sans apt. On évite `ffprobe`, qui
n'est pas fourni par imageio-ffmpeg : les durées viennent du module `wave`
pour les .wav et de la sortie de `ffmpeg -i` pour le reste.
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import wave
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)


class FFmpegError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def ffmpeg_bin() -> str:
    """Chemin de ffmpeg (PATH ou imageio-ffmpeg)."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg  # type: ignore

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # noqa: BLE001
        raise FFmpegError(
            "ffmpeg introuvable : `sudo apt install ffmpeg` ou `pip install imageio-ffmpeg`"
        ) from exc


def run_ffmpeg(args: list[str], *, quiet: bool = True) -> subprocess.CompletedProcess[str]:
    """Lance ffmpeg avec `-y -hide_banner` et remonte stderr en cas d'échec."""
    cmd = [ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error" if quiet else "info", *args]
    log.debug("ffmpeg %s", " ".join(cmd[1:]))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise FFmpegError(f"ffmpeg a échoué ({proc.returncode}) :\n{proc.stderr[-2000:]}")
    return proc


_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


def media_duration(path: str | Path) -> float:
    """Durée en secondes d'un média (wav via `wave`, sinon via `ffmpeg -i`)."""
    path = Path(path)
    if path.suffix.lower() == ".wav":
        with wave.open(str(path), "rb") as wf:
            return wf.getnframes() / float(wf.getframerate())
    proc = subprocess.run([ffmpeg_bin(), "-hide_banner", "-i", str(path)],
                          capture_output=True, text=True)
    m = _DURATION_RE.search(proc.stderr)
    if not m:
        raise FFmpegError(f"durée introuvable pour {path}")
    h, mn, s = m.groups()
    return int(h) * 3600 + int(mn) * 60 + float(s)


def video_encode_args(crf: int = 18, preset: str = "medium") -> list[str]:
    """Arguments d'encodage H.264 communs (yuv420p pour la compatibilité)."""
    return ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", str(crf), "-preset", preset,
            "-movflags", "+faststart"]


def extract_frame(video: str | Path, out_png: str | Path, at_s: float | None = None) -> Path:
    """Extrait une image (au milieu par défaut) — sert à la vérification visuelle."""
    if at_s is None:
        at_s = max(0.0, media_duration(video) / 2)
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(["-ss", f"{at_s:.3f}", "-i", str(video), "-frames:v", "1", str(out_png)])
    return out_png


def write_silence(out_wav: str | Path, duration_s: float, sample_rate: int = 48000) -> Path:
    """Écrit un wav mono 16 bits silencieux (sans dépendre de ffmpeg)."""
    out_wav = Path(out_wav)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    n = max(1, int(duration_s * sample_rate))
    with wave.open(str(out_wav), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * n)
    return out_wav


def normalize_wav(src: str | Path, dst: str | Path, sample_rate: int = 48000,
                  pad_end_s: float = 0.0) -> Path:
    """Rééchantillonne en mono 16 bits, normalise le niveau, ajoute une pause finale."""
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    af = "loudnorm=I=-18:TP=-1.5:LRA=11"
    if pad_end_s > 0:
        af += f",apad=pad_dur={pad_end_s:.3f}"
    run_ffmpeg(["-i", str(src), "-af", af, "-ar", str(sample_rate), "-ac", "1",
                "-c:a", "pcm_s16le", str(dst)])
    return dst

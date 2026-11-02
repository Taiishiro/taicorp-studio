"""Chargement et typage de `config.yaml`.

On garde des dataclasses simples : chaque étape ne lit que la section qui la
concerne. Les chemins relatifs sont résolus par rapport au dossier du fichier
de configuration (racine du projet cartoon-factory).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]  # dossier cartoon-factory/
DEFAULT_CONFIG_PATH = ROOT / "config.yaml"


@dataclass
class LoraConfig:
    file: str = ""
    weight: float = 0.8
    trigger: str = ""

    @property
    def enabled(self) -> bool:
        return bool(self.file)


@dataclass
class StyleConfig:
    prompt_prefix: str = ""
    negative_prompt: str = ""
    lora: LoraConfig = field(default_factory=LoraConfig)


@dataclass
class VideoConfig:
    width: int = 1920
    height: int = 1080
    fps: int = 24
    vertical_variant: bool = True
    crf: int = 18
    preset: str = "medium"


@dataclass
class KeyframeConfig:
    width: int = 1024
    height: int = 576
    steps: int = 28
    cfg: float = 6.0
    sampler: str = "dpmpp_2m"
    scheduler: str = "karras"
    seed_base: int = 424242


@dataclass
class ComfyConfig:
    url: str = "http://127.0.0.1:8188"
    timeout_s: int = 1800
    poll_interval_s: float = 2.0
    free_vram_between_stages: bool = True
    workflows: dict[str, str] = field(default_factory=dict)
    models: dict[str, str] = field(default_factory=dict)


@dataclass
class AnimationConfig:
    default_method: str = "kenburns"
    kenburns: dict[str, Any] = field(default_factory=dict)
    tooncrafter: dict[str, Any] = field(default_factory=dict)
    wan_i2v: dict[str, Any] = field(default_factory=dict)


@dataclass
class TTSConfig:
    backend: str = "kokoro"
    words_per_minute: int = 150
    pause_after_s: float = 0.35
    sample_rate: int = 48000
    kokoro: dict[str, Any] = field(default_factory=dict)
    xtts: dict[str, Any] = field(default_factory=dict)
    espeak: dict[str, Any] = field(default_factory=dict)


@dataclass
class SubtitlesConfig:
    enabled: bool = True
    burn_in: bool = False


@dataclass
class MusicConfig:
    file: str = ""
    volume_db: float = -20.0
    fade_s: float = 1.5


@dataclass
class Config:
    """Configuration complète, typée par section."""

    root: Path
    name: str = "cartoon-factory"
    output_dir: Path = Path("output")
    characters_dir: Path = Path("characters")
    language: str = "fr"
    style: StyleConfig = field(default_factory=StyleConfig)
    video: VideoConfig = field(default_factory=VideoConfig)
    keyframe: KeyframeConfig = field(default_factory=KeyframeConfig)
    comfy: ComfyConfig = field(default_factory=ComfyConfig)
    animation: AnimationConfig = field(default_factory=AnimationConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    subtitles: SubtitlesConfig = field(default_factory=SubtitlesConfig)
    music: MusicConfig = field(default_factory=MusicConfig)
    raw: dict[str, Any] = field(default_factory=dict)

    def resolve(self, p: str | Path) -> Path:
        """Résout un chemin relatif à la racine du projet."""
        p = Path(p)
        return p if p.is_absolute() else (self.root / p)

    def workflow_path(self, name: str) -> Path:
        try:
            return self.resolve(self.comfy.workflows[name])
        except KeyError as exc:
            raise KeyError(f"workflow « {name} » absent de config.yaml (comfy.workflows)") from exc


def _build(cls: type, data: dict[str, Any] | None) -> Any:
    """Instancie une dataclass en ignorant les clés inconnues (tolérance YAML)."""
    data = data or {}
    fields = {f.name: f for f in cls.__dataclass_fields__.values()}
    kwargs: dict[str, Any] = {}
    for key, value in data.items():
        if key not in fields:
            continue
        ftype = fields[key].type
        if ftype == "LoraConfig" or ftype is LoraConfig:
            value = _build(LoraConfig, value)
        kwargs[key] = value
    return cls(**kwargs)


def load_config(path: str | Path | None = None) -> Config:
    """Charge `config.yaml` (ou le chemin donné) en objet `Config`."""
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    with open(cfg_path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    project = raw.get("project", {})
    root = cfg_path.resolve().parent
    return Config(
        root=root,
        name=project.get("name", "cartoon-factory"),
        output_dir=Path(project.get("output_dir", "output")),
        characters_dir=Path(project.get("characters_dir", "characters")),
        language=project.get("language", "fr"),
        style=_build(StyleConfig, raw.get("style")),
        video=_build(VideoConfig, raw.get("video")),
        keyframe=_build(KeyframeConfig, raw.get("keyframe")),
        comfy=_build(ComfyConfig, raw.get("comfy")),
        animation=_build(AnimationConfig, raw.get("animation")),
        tts=_build(TTSConfig, raw.get("tts")),
        subtitles=_build(SubtitlesConfig, raw.get("subtitles")),
        music=_build(MusicConfig, raw.get("music")),
        raw=raw,
    )

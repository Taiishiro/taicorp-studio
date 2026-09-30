"""Fixtures communes : config allégée (basse résolution) pour des tests rapides."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from cartoon_factory.config import ROOT, load_config
from cartoon_factory.models import Episode, load_characters

EXAMPLE = ROOT / "examples" / "ciel-bleu"


@pytest.fixture
def small_cfg(tmp_path: Path):
    """Config réelle, mais 320x180 @ 12 fps et sortie dans tmp : rendu en secondes."""
    raw = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    raw["video"].update({"width": 320, "height": 180, "fps": 12, "crf": 30, "preset": "ultrafast"})
    raw["keyframe"].update({"width": 320, "height": 180})
    raw["project"]["output_dir"] = str(tmp_path / "output")
    raw["project"]["characters_dir"] = str(EXAMPLE / "characters")
    raw["tts"]["backend"] = "silence"
    cfg_path = tmp_path / "config.yaml"
    # Les workflows restent ceux du projet : on recopie le dossier pour garder les chemins relatifs.
    shutil.copytree(ROOT / "workflows", tmp_path / "workflows")
    cfg_path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    return load_config(cfg_path)


@pytest.fixture
def example_episode() -> Episode:
    return Episode.load(EXAMPLE / "episode.json")


@pytest.fixture
def example_characters():
    return load_characters(EXAMPLE / "characters")


def has_ffmpeg() -> bool:
    try:
        from cartoon_factory.media import ffmpeg_bin

        ffmpeg_bin()
        return True
    except Exception:  # noqa: BLE001
        return False


needs_ffmpeg = pytest.mark.skipif(not has_ffmpeg(), reason="ffmpeg absent")

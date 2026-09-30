"""Remplissage des workflows et court-circuit des LoRA vides (sans serveur)."""

import pytest

from cartoon_factory.comfy import (
    ComfyError,
    bypass_empty_loras,
    fill_workflow,
    find_placeholders,
    load_workflow,
)
from cartoon_factory.config import ROOT

WF_DIR = ROOT / "workflows"


def test_find_placeholders_in_shipped_workflows():
    kf = load_workflow(WF_DIR / "keyframe_sdxl.api.json")
    found = find_placeholders(kf)
    assert {"__PROMPT__", "__SEED__", "__STYLE_LORA__", "__SDXL_CHECKPOINT__"} <= found
    wan = load_workflow(WF_DIR / "wan_i2v.api.json")
    assert {"__IMAGE_START__", "__HALF_STEPS__", "__WAN_HIGH_GGUF__"} <= find_placeholders(wan)
    assert "_comment" not in wan  # les nœuds de commentaire ne partent pas au serveur


def test_fill_typed_and_embedded():
    wf = {"1": {"class_type": "X", "inputs": {"seed": "__SEED__", "cfg": "__CFG__",
                                              "prefix": "out/__PREFIX__"}}}
    out = fill_workflow(wf, {"SEED": 7, "CFG": 6.5, "PREFIX": "s01"})
    assert out["1"]["inputs"] == {"seed": 7, "cfg": 6.5, "prefix": "out/s01"}
    assert wf["1"]["inputs"]["seed"] == "__SEED__"  # template intact


def test_fill_strict_refuses_missing():
    wf = {"1": {"class_type": "X", "inputs": {"a": "__A__", "b": "__B__"}}}
    with pytest.raises(ComfyError, match="__B__"):
        fill_workflow(wf, {"A": 1})


def test_bypass_empty_loras_rewires_consumers():
    kf = load_workflow(WF_DIR / "keyframe_sdxl.api.json")
    values = {"PROMPT": "p", "NEGATIVE": "n", "SEED": 1, "STEPS": 2, "CFG": 3.0, "WIDTH": 64,
              "HEIGHT": 64, "SAMPLER": "euler", "SCHEDULER": "simple", "PREFIX": "x",
              "SDXL_CHECKPOINT": "ck.safetensors",
              "STYLE_LORA": "", "STYLE_LORA_WEIGHT": 0.8, "CHAR_LORA": "", "CHAR_LORA_WEIGHT": 0.9}
    out = bypass_empty_loras(fill_workflow(kf, values))
    assert "2" not in out and "3" not in out
    assert out["4"]["inputs"]["clip"] == ["1", 1]  # CLIPTextEncode → checkpoint direct
    assert out["7"]["inputs"]["model"] == ["1", 0]  # KSampler → checkpoint direct
    # Avec un LoRA style renseigné, seul le LoRA perso saute.
    values["STYLE_LORA"] = "crayon.safetensors"
    out2 = bypass_empty_loras(fill_workflow(kf, values))
    assert "2" in out2 and "3" not in out2
    assert out2["7"]["inputs"]["model"] == ["2", 0]

"""Construction des prompts : style global + personnages + contenu du plan."""

from __future__ import annotations

from cartoon_factory.config import Config
from cartoon_factory.models import Character


def build_prompt(cfg: Config, content: str, characters: list[Character] | None = None) -> str:
    """`[trigger LoRA style] style, [trigger perso] perso…, contenu`."""
    parts: list[str] = []
    if cfg.style.lora.trigger:
        parts.append(cfg.style.lora.trigger)
    parts.append(cfg.style.prompt_prefix.strip())
    for ch in characters or []:
        if ch.lora_trigger:
            parts.append(ch.lora_trigger)
        parts.append(ch.prompt.strip())
    parts.append(content.strip())
    return ", ".join(p for p in parts if p)


def build_negative(cfg: Config, characters: list[Character] | None = None) -> str:
    parts = [cfg.style.negative_prompt.strip()]
    parts += [ch.negative_prompt.strip() for ch in (characters or []) if ch.negative_prompt]
    return ", ".join(p for p in parts if p)

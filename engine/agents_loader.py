"""Charge les agents définis dans .claude/agents/*.md.

Gère le frontmatter au format Claude Code / Agent SDK, y compris :
- `model: claude-sonnet-4-6` (ID complet)
- `tools: [Read, Grep, Glob]` (liste inline) ou `tools: Read, Grep` (CSV)
- `description: >` (scalaire replié sur plusieurs lignes)
- clés ignorées inconnues (ex: `temperature`)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

AGENTS_DIR = Path(__file__).resolve().parent.parent / ".claude" / "agents"


@dataclass
class Agent:
    name: str
    model: str
    tools: list[str]
    description: str
    prompt: str           # corps Markdown = system prompt
    file: Path
    extra: dict = field(default_factory=dict)


def _split_frontmatter(text: str) -> tuple[str, str]:
    if not text.startswith("---"):
        return "", text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return "", text
    return parts[1], parts[2].lstrip("\n")


def _parse_meta(fm: str) -> dict:
    meta: dict = {}
    lines = fm.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or ":" not in line:
            i += 1
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        if val in (">", "|"):  # scalaire replié : on agrège les lignes indentées suivantes
            block = []
            i += 1
            while i < len(lines) and (lines[i].startswith((" ", "\t")) or not lines[i].strip()):
                block.append(lines[i].strip())
                i += 1
            meta[key] = " ".join(b for b in block if b)
            continue
        meta[key] = val.strip().strip('"').strip("'")
        i += 1
    return meta


def _parse_tools(raw: str) -> list[str]:
    raw = (raw or "").strip()
    if raw.startswith("["):
        raw = raw[1:-1]
    return [t.strip().strip('"').strip("'") for t in raw.split(",") if t.strip()]


def load_agents() -> dict[str, Agent]:
    agents: dict[str, Agent] = {}
    for path in sorted(AGENTS_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        fm, body = _split_frontmatter(text)
        meta = _parse_meta(fm)
        name = meta.get("name") or path.stem
        agent = Agent(
            name=name,
            model=meta.get("model", "claude-sonnet-4-6"),
            tools=_parse_tools(meta.get("tools", "")),
            description=meta.get("description", ""),
            prompt=body.strip(),
            file=path,
            extra={k: v for k, v in meta.items() if k not in ("name", "model", "tools", "description")},
        )
        agents[name] = agent
    return agents


if __name__ == "__main__":
    for name, a in load_agents().items():
        print(f"{name:20} {a.model:20} tools={a.tools}")

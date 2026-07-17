"""Routage & lisibilité — le cœur du studio « flexible ».

3 rôles :
1. route_request()   : langage naturel → quel(s) agent(s) + sous-tâche affinée.
                       Heuristique par mots-clés (mode démo + 1re passe en réel).
2. tool_to_action()  : un appel d'outil du SDK → action lisible pour l'UI
                       (ex: Edit{file_path:"engine/server.py"} → "modifie server.py · handle_run()").
3. new_agent_md()    : gabarit d'un nouveau .md d'agent (méta-agent « crée un rôle »).
"""
from __future__ import annotations
import os
import re

# --------------------------------------------------------------------------- #
#  1. Routage langage naturel → agent
# --------------------------------------------------------------------------- #
# Ordre = priorité. Le 1er groupe de mots-clés qui matche gagne.
ROUTE_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("git-integration",   ("git", "push", "commit", "merge", "branch", "pull request", "pr ",
                            "repo", "github", "rebase", "tag", "release")),
    ("devops-infra",      ("docker", "déploie", "deploy", "ci/cd", "ci ", "pipeline ci",
                            "kubernetes", "k8s", "terraform", "nginx", "env ", "variable d'env",
                            "infra", "serveur", "prod")),
    ("security-reviewer", ("sécurit", "securit", "faille", "vulnérab", "vulnerab", "injection",
                           "xss", "csrf", "audit sécu", "secret", "owasp", "auth", "token")),
    ("test-engineer",     ("test", "pytest", "couverture", "coverage", "régression", "regression",
                           "unit ", "e2e", "mock")),
    ("reviewer",          ("review", "revue", "relis", "relire", "qualité", "code review",
                           "dette technique", "refactor critique")),
    ("senior-coder",      ("code", "implémente", "implemente", "écris", "ecris", "ajoute",
                           "corrige", "fix", "bug", "refactor", "fonction", "endpoint",
                           "classe", "méthode", "develop", "feature")),
    ("context-manager",   ("contexte", "context", "quels fichiers", "dépendance", "dependance",
                           "où est", "ou est", "bundle")),
    ("architect-lead",    ("architecture", "conçois", "concois", "design", "adr", "découpe",
                           "decoupe", "plan technique", "techno", "structure")),
    ("reporter-po",       ("spec", "besoin", "user story", "cahier des charges", "clarifie",
                           "que veut", "périmètre", "perimetre")),
]

# Agents qui forment le pipeline complet, dans l'ordre.
PIPELINE = [
    "reporter-po", "architect-lead", "context-manager", "senior-coder",
    "reviewer", "test-engineer", "security-reviewer",
    "git-integration", "devops-infra",
]


def route_request(request: str) -> str:
    """Renvoie le nom de l'agent le plus pertinent pour une demande brute."""
    low = request.lower()
    for agent, keywords in ROUTE_RULES:
        if any(k in low for k in keywords):
            return agent
    return "senior-coder"  # défaut : on code


def route_explain(request: str) -> tuple[str, str]:
    """(agent, raison lisible) — sert à la bulle de décision du PO."""
    low = request.lower()
    for agent, keywords in ROUTE_RULES:
        hit = next((k for k in keywords if k in low), None)
        if hit:
            return agent, f"« {hit.strip()} » détecté → {agent}"
    return "senior-coder", "aucun mot-clé spécifique → senior-coder par défaut"


# --------------------------------------------------------------------------- #
#  2. Outil SDK → action lisible (la « tâche exacte à l'instant t »)
# --------------------------------------------------------------------------- #
_SYMBOL_RE = re.compile(
    r"(?:def|class|function|const|let|var|func|fn|public|private|export\s+function)\s+([A-Za-z_][\w]*)"
)


def _symbol_from(text: str | None) -> str:
    if not text:
        return ""
    m = _SYMBOL_RE.search(text)
    return f"{m.group(1)}()" if m else ""


def _base(path: str | None) -> str:
    if not path:
        return ""
    return os.path.basename(path.rstrip("/")) or path


def tool_to_action(tool_name: str, tool_input: dict | None) -> tuple[str, str]:
    """(verbe, détail) lisibles pour un appel d'outil donné."""
    ti = tool_input or {}
    name = (tool_name or "").lower()

    if name == "read":
        return "lit", _base(ti.get("file_path"))
    if name == "write":
        return "écrit", _base(ti.get("file_path"))
    if name in ("edit", "multiedit"):
        f = _base(ti.get("file_path"))
        sym = _symbol_from(ti.get("new_string") or ti.get("old_string"))
        return "modifie", f"{f} · {sym}" if sym else f
    if name == "bash":
        cmd = (ti.get("command") or "").strip().replace("\n", " ")
        return "exécute", cmd[:48]
    if name == "grep":
        return "cherche", (ti.get("pattern") or "")[:36]
    if name == "glob":
        return "liste", (ti.get("pattern") or "")[:36]
    if name == "task":
        return "délègue", ti.get("subagent_type") or (ti.get("description") or "")[:36]
    if name == "todowrite":
        todos = ti.get("todos") or []
        cur = next((t.get("content") for t in todos if t.get("status") == "in_progress"), None)
        return "planifie", (cur or f"{len(todos)} tâches")[:40]
    if name in ("webfetch", "websearch"):
        return "recherche", (ti.get("url") or ti.get("query") or "")[:40]
    return name or "agit", ""


# --------------------------------------------------------------------------- #
#  3. Méta-agent : gabarit d'un nouveau rôle
# --------------------------------------------------------------------------- #
def new_agent_md(name: str, role: str, mission: str,
                 tools: list[str] | None = None,
                 model: str = "claude-sonnet-4-6") -> str:
    """Construit le contenu .md d'un agent généré à la volée."""
    tools = tools or ["Read", "Grep", "Glob", "Write", "Edit", "Bash"]
    tools_str = "[" + ", ".join(tools) + "]"
    return f"""---
name: {name}
description: >
  Agent généré à la volée par le méta-agent. Rôle : {role}.
  {mission}
tools: {tools_str}
model: {model}
temperature: 0.2
generated: true
---

# {role} — agent généré

## Mission
{mission}

## Périmètre
- Tu interviens uniquement sur la tâche qui t'est confiée.
- Tu restes dans le périmètre de fichiers fourni par le Context Manager.
- Tu signales tout blocage au lieu de deviner.

## Format de sortie obligatoire
```markdown
## Résultat — {role}
- Ce qui a été fait : ...
- Fichiers touchés : ...
- Limites / risques : ...
→ Prêt pour : <agent suivant ou livraison>
```

## Règles d'or
- 🎯 Une tâche = un objectif clair. Pas de débordement.
- 🧩 Aucun effet de bord hors périmètre.
- 🗣️ Tu rapportes en mode compressé (skill caveman) si tu décris du texte.
"""


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:32] or "agent"

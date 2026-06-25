"""Orchestrateur — fait tourner le pipeline d'agents et alimente le jeu.

Deux modes :
  python orchestrator.py --demo "Ajoute un login Google"
      → simule le pipeline (aucun appel API, aucun token brûlé).
        Idéal pour brancher l'UI : state.json bouge en direct.

  python orchestrator.py "Ajoute un login Google"
      → exécute le VRAI pipeline via le Claude Agent SDK.
        Chaque étape lance l'agent correspondant (.claude/agents/*.md),
        avec son modèle et ses outils, et reporte ses tokens réels.

Pipeline :
  reporter-po → architect-lead → context-manager → senior-coder
    → [reviewer ∥ test-engineer ∥ security-reviewer]  (boucle si bloqué)
    → git-integration → devops-infra → ✅ livré
"""
from __future__ import annotations
import asyncio
import os
import sys
from pathlib import Path

from agents_loader import load_agents, Agent
from bus import Bus

ROOT = Path(__file__).resolve().parent.parent  # dossier TaiCorp AI AGENTS
BLOCKERS = ("BLOQUANT", "CHANGEMENTS REQUIS", "CRITIQUE")


# --------------------------------------------------------------------------- #
#  Mode RÉEL — Claude Agent SDK
# --------------------------------------------------------------------------- #
async def run_agent_real(agent: Agent, prompt: str, bus: Bus) -> str:
    from claude_agent_sdk import (
        query, ClaudeAgentOptions, AssistantMessage, TextBlock, ResultMessage,
    )

    bus.status(agent.name, "working", task=prompt.split("\n", 1)[0][:60])
    bus.stage(agent.name, f"{agent.name} travaille")

    options = ClaudeAgentOptions(
        system_prompt=agent.prompt,
        allowed_tools=agent.tools,
        model=agent.model,
        cwd=str(ROOT),
        setting_sources=["project"],
        # ⚠️ bypassPermissions auto-approuve TOUTES les actions outils.
        # À ne lancer que sur une branche jetable / un sandbox.
        permission_mode="bypassPermissions",
        max_turns=24,
    )

    parts: list[str] = []
    async for msg in query(prompt=prompt, options=options):
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    parts.append(block.text)
        elif isinstance(msg, ResultMessage):
            u = msg.usage or {}
            tokens = (u.get("input_tokens", 0) or 0) + (u.get("output_tokens", 0) or 0)
            bus.usage(agent.name, tokens, msg.total_cost_usd or 0.0)

    bus.status(agent.name, "idle")
    return "".join(parts)


# --------------------------------------------------------------------------- #
#  Mode DEMO — aucun appel API
# --------------------------------------------------------------------------- #
async def run_agent_demo(agent: Agent, prompt: str, bus: Bus) -> str:
    import random
    bus.status(agent.name, "working", task=prompt.split("\n", 1)[0][:60])
    bus.stage(agent.name, f"{agent.name} travaille")
    await asyncio.sleep(1.2)
    bus.usage(agent.name, random.randint(8000, 40000), round(random.uniform(0.05, 0.4), 3))
    bus.status(agent.name, "idle")
    return f"[demo] sortie de {agent.name}"


# --------------------------------------------------------------------------- #
#  Pipeline
# --------------------------------------------------------------------------- #
async def run_pipeline(user_request: str, demo: bool = False):
    agents = load_agents()
    bus = Bus()
    bus.register(list(agents.keys()))
    run = run_agent_demo if demo else run_agent_real

    def a(name: str) -> Agent:
        return agents[name]

    bus.new_ticket()

    spec = await run(a("reporter-po"), f"Demande utilisateur :\n{user_request}", bus)
    tickets = await run(a("architect-lead"), f"Spec du PO :\n{spec}\n\nDécoupe en tickets + ADR.", bus)
    bundle = await run(a("context-manager"), f"Tickets :\n{tickets}\n\nPrépare le context bundle minimal du 1er ticket.", bus)
    code = await run(a("senior-coder"), f"Context bundle :\n{bundle}\n\nImplémente le ticket.", bus)

    for attempt in range(2):  # 1 tentative + 1 boucle de correction max
        bus.stage("reviewer", "reviewer · test · security inspectent (en //)")
        rev, test, sec = await asyncio.gather(
            run(a("reviewer"), f"Diff / notes :\n{code}\n\nRevue qualité.", bus),
            run(a("test-engineer"), f"Diff :\n{code}\n\nÉcris les tests + rapport.", bus),
            run(a("security-reviewer"), f"Diff :\n{code}\n\nAudit sécurité.", bus),
        )
        blocked = any(any(b in r.upper() for b in BLOCKERS) for r in (rev, test, sec))
        if not blocked:
            break
        bus.emit("loopback", reason="verdict bloquant", attempt=attempt)
        code = await run(a("senior-coder"), f"Corrige selon les retours :\n{rev}\n{test}\n{sec}", bus)

    await run(a("git-integration"), f"Diff validé :\n{code}\n\nCommit + branche + CI.", bus)
    await run(a("devops-infra"), "Code mergé.\n\nDocker + déploiement.", bus)

    bus.complete()
    print("\n✅ Pipeline terminé. state.json mis à jour.")


def main():
    # Console Windows : force UTF-8 pour les emoji/accents des logs.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    args = sys.argv[1:]
    demo = "--demo" in args
    args = [x for x in args if x != "--demo"]
    request = " ".join(args) or "Ajoute un système de login Google (OAuth)."

    # Auth : soit une clé API, soit la session de l'abonnement (claude login).
    # Le CLI Claude stocke ses identifiants dans ~/.claude/.credentials.json.
    if not demo:
        has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
        creds = Path.home() / ".claude" / ".credentials.json"
        has_login = creds.exists()
        if not has_key and not has_login:
            print("⚠️  Aucune auth (ni ANTHROPIC_API_KEY ni `claude login`) → bascule en --demo.")
            print("    → Lance `claude` une fois dans WSL pour te connecter, puis relance.")
            demo = True
        elif has_login and not has_key:
            print("🔑 Auth via abonnement Claude (session du CLI).")
        else:
            print("🔑 Auth via ANTHROPIC_API_KEY.")
    asyncio.run(run_pipeline(request, demo=demo))


if __name__ == "__main__":
    main()

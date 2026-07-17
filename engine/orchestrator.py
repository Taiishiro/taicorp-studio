"""Orchestrateur v2 — studio d'agents FLEXIBLE.

Modes (flag --flow, défaut = pipeline) :
  pipeline   : le workflow complet à 9 étapes (reporter-po → … → devops-infra).
  single     : UN seul agent, appelé directement (--agent <nom>). Pas de workflow.
  route      : le PO lit la demande en langage naturel, pose des questions si flou,
               puis dispatch vers le bon agent.
  meta       : le méta-agent CRÉE un nouvel agent (.md) ou CLONE un agent existant
               en plusieurs exemplaires parallèles.

Exécution (flag --demo) :
  --demo     : simulation (aucun token), avec actions scriptées pour l'UI.
  (sinon)    : VRAIS agents via le Claude Agent SDK ; les ToolUseBlock deviennent
               des actions lisibles à l'écran ("modifie server.py · handle_run()").

Exemples :
  python orchestrator.py --demo "Ajoute un login Google"
  python orchestrator.py --flow single --agent git-integration "push sur le repo X"
  python orchestrator.py --flow route "mets ça sur mon github"
  python orchestrator.py --flow meta "j'ai besoin d'un agent qui traduit la doc"
"""
from __future__ import annotations
import argparse
import asyncio
import os
import sys
from pathlib import Path

from agents_loader import load_agents, Agent, AGENTS_DIR
from bus import Bus
from router import route_explain, route_request, tool_to_action, new_agent_md, slugify

ROOT = Path(__file__).resolve().parent.parent
BLOCKERS = ("BLOQUANT", "CHANGEMENTS REQUIS", "CRITIQUE")
# Nombre de passes de revue avant d'abandonner le ticket. Une passe = les 3
# gardiens inspectent ; un verdict bloquant renvoie au senior-coder, puis on
# ré-inspecte. Au-delà, on refuse de livrer (cf. run_pipeline).
MAX_REVIEW_ROUNDS = 3


# --------------------------------------------------------------------------- #
#  Mode RÉEL — Claude Agent SDK (avec actions temps réel)
# --------------------------------------------------------------------------- #
async def run_agent_real(agent: Agent, prompt: str, bus: Bus,
                         label: str | None = None, final: str = "idle") -> str:
    from claude_agent_sdk import (
        query, ClaudeAgentOptions, AssistantMessage, TextBlock, ResultMessage,
    )
    try:
        from claude_agent_sdk import ToolUseBlock
    except Exception:
        ToolUseBlock = None

    bus.status(agent.name, "working", task=(label or prompt.split("\n", 1)[0])[:70])
    bus.stage(agent.name, f"{agent.name} travaille")

    options = ClaudeAgentOptions(
        system_prompt=agent.prompt,
        allowed_tools=agent.tools,
        model=agent.model,
        cwd=str(ROOT),
        setting_sources=["project"],
        # ⚠️ bypassPermissions auto-approuve les outils. Sandbox / branche jetable.
        permission_mode="bypassPermissions",
        max_turns=24,
    )

    parts: list[str] = []
    try:
        async for msg in query(prompt=prompt, options=options):
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        parts.append(block.text)
                    elif (ToolUseBlock and isinstance(block, ToolUseBlock)) or (
                            hasattr(block, "name") and hasattr(block, "input")):
                        verb, detail = tool_to_action(block.name, getattr(block, "input", {}))
                        bus.action(agent.name, verb, detail)
            elif isinstance(msg, ResultMessage):
                # Vrais tokens Claude : entrée + sortie + cache (création + lecture).
                u = msg.usage or {}
                tin = int(u.get("input_tokens", 0) or 0)
                tout = int(u.get("output_tokens", 0) or 0)
                tcache = int(u.get("cache_creation_input_tokens", 0) or 0) \
                    + int(u.get("cache_read_input_tokens", 0) or 0)
                bus.usage(agent.name, tin + tout + tcache,
                          msg.total_cost_usd or 0.0, tin, tout, tcache)
    except Exception as e:  # quota/credit/rate-limit ou autre échec SDK → remonté à l'UI
        detail = (str(e) or e.__class__.__name__).strip()
        low = detail.lower()
        out_of_tokens = any(k in low for k in (
            "rate limit", "rate_limit", "429", "quota", "credit", "insufficient",
            "usage limit", "overloaded", "529", "balance", "payment", "billing"))
        if out_of_tokens:
            bus.error(f"Plus de tokens / quota Claude atteint — {detail[:140]}", agent=agent.name)
        else:
            bus.error(f"Échec agent {agent.name} — {detail[:140]}", agent=agent.name)
        bus.status(agent.name, "idle")
        raise

    bus.status(agent.name, final)
    return "".join(parts)


# --------------------------------------------------------------------------- #
#  Mode DEMO — actions scriptées (aucun appel API)
# --------------------------------------------------------------------------- #
DEMO_ACTIONS: dict[str, list[tuple[str, str]]] = {
    "reporter-po":       [("lit", "demande utilisateur"), ("écrit", "spec.md")],
    "architect-lead":    [("lit", "spec.md"), ("cherche", "modules impactés"), ("écrit", "ADR-0007.md")],
    "context-manager":   [("liste", "graphify query"), ("lit", "server.py"), ("écrit", "context-bundle")],
    "senior-coder":      [("lit", "server.py"), ("modifie", "server.py · handle_run()"),
                          ("écrit", "health.py · health()"), ("exécute", "python -m pytest -q")],
    "reviewer":          [("lit", "diff"), ("cherche", "TODO / dette"), ("écrit", "verdict")],
    "test-engineer":     [("écrit", "test_health.py"), ("exécute", "pytest -q"), ("écrit", "rapport couverture")],
    "security-reviewer": [("cherche", "secrets / clés"), ("exécute", "pip-audit"), ("écrit", "audit sécu")],
    "git-integration":   [("exécute", "git checkout -b feat/health"),
                          ("exécute", "git commit -m feat: /health"), ("exécute", "git push origin")],
    "devops-infra":      [("modifie", "Dockerfile"), ("exécute", "docker build ."), ("écrit", "deploy.sh")],
}


async def run_agent_demo(agent: Agent, prompt: str, bus: Bus,
                         label: str | None = None, final: str = "idle") -> str:
    import random
    bus.status(agent.name, "working", task=(label or prompt.split("\n", 1)[0])[:70])
    bus.stage(agent.name, f"{agent.name} travaille")
    for verb, detail in DEMO_ACTIONS.get(agent.base if hasattr(agent, "base") else agent.name,
                                         [("travaille", "…")]):
        bus.action(agent.name, verb, detail)
        await asyncio.sleep(0.5)
    t = random.randint(8000, 40000)
    bus.usage(agent.name, t, round(random.uniform(0.05, 0.4), 3),
              int(t * 0.55), int(t * 0.30), int(t * 0.15))
    bus.status(agent.name, final)
    return f"[demo] sortie de {agent.name}"


def picker(demo: bool):
    return run_agent_demo if demo else run_agent_real


# --------------------------------------------------------------------------- #
#  FLOW 1 — Pipeline complet
# --------------------------------------------------------------------------- #
async def run_pipeline(request: str, demo: bool = False):
    agents = load_agents()
    bus = Bus()
    bus.register(list(agents.keys()))
    run = picker(demo)
    bus.new_ticket(request, mode="pipeline")

    spec = await run(agents["reporter-po"], f"Demande utilisateur :\n{request}", bus)
    tickets = await run(agents["architect-lead"], f"Spec du PO :\n{spec}\n\nDécoupe en tickets + ADR.", bus)
    bundle = await run(agents["context-manager"], f"Tickets :\n{tickets}\n\nPrépare le context bundle minimal.", bus)
    code = await run(agents["senior-coder"], f"Context bundle :\n{bundle}\n\nImplémente le ticket.", bus)

    # Les 3 gardiens doivent TOUS être au vert avant l'intégration. Une correction
    # est toujours ré-inspectée : on ne sort de la boucle que par un verdict propre
    # (approved) ou par épuisement des passes — et dans ce cas on ne livre pas.
    approved = False
    blockers: list[str] = []
    for attempt in range(1, MAX_REVIEW_ROUNDS + 1):
        bus.stage("reviewer",
                  f"reviewer · test · security inspectent (en //) — passe {attempt}/{MAX_REVIEW_ROUNDS}")
        rev, test, sec = await asyncio.gather(
            run(agents["reviewer"], f"Diff :\n{code}\n\nRevue qualité.", bus),
            run(agents["test-engineer"], f"Diff :\n{code}\n\nTests + rapport.", bus),
            run(agents["security-reviewer"], f"Diff :\n{code}\n\nAudit sécurité.", bus),
        )
        verdicts = (("reviewer", rev), ("test-engineer", test), ("security-reviewer", sec))
        if any("CRITIQUE" in r.upper() for _, r in verdicts):
            await council(bus, demo, reason="faille CRITIQUE détectée", agents=agents, code=code)

        blockers = [name for name, r in verdicts if any(b in r.upper() for b in BLOCKERS)]
        if not blockers:
            approved = True
            break
        if attempt == MAX_REVIEW_ROUNDS:
            break  # dernière passe déjà consommée : inutile de re-corriger sans re-vérifier
        bus.emit("loopback", reason="verdict bloquant", blockers=blockers, attempt=attempt)
        code = await run(agents["senior-coder"], f"Corrige selon les retours :\n{rev}\n{test}\n{sec}", bus)

    if not approved:
        bus.error(
            f"Livraison refusée — {', '.join(blockers)} maintiennent un verdict "
            f"bloquant après {MAX_REVIEW_ROUNDS} passes. Rien n'est commité.",
            fatal=True,
        )
        print(f"\n⛔ Pipeline arrêté : {', '.join(blockers)} bloquent encore. Aucun commit, aucun déploiement.")
        return

    await run(agents["git-integration"], f"Diff validé :\n{code}\n\nCommit + branche + CI.", bus)
    await run(agents["devops-infra"], "Code mergé.\n\nDocker + déploiement.", bus)
    bus.complete()
    print("\n✅ Pipeline terminé.")


# --------------------------------------------------------------------------- #
#  FLOW 2 — Agent unique
# --------------------------------------------------------------------------- #
async def run_single(agent_name: str, request: str, demo: bool = False):
    agents = load_agents()
    bus = Bus()
    bus.register(list(agents.keys()))
    bus.new_ticket(request, mode="single")
    if agent_name not in agents:
        bus.stage(agent_name, f"agent inconnu : {agent_name}")
        bus.stop()
        print(f"⚠️  agent inconnu : {agent_name}")
        return
    run = picker(demo)
    await run(agents[agent_name], f"Tâche directe (hors workflow) :\n{request}", bus,
              label=f"{agent_name}: {request[:40]}", final="done")
    bus.complete()
    print(f"\n✅ {agent_name} a fini.")


# --------------------------------------------------------------------------- #
#  FLOW 3 — Routage par le PO (avec questions de clarification)
# --------------------------------------------------------------------------- #
PO_ROUTER_PROMPT = """Demande brute de l'utilisateur :
{request}

Tu es le PO-routeur. Deux cas :
1. Si la demande est AMBIGÜE (cible, résultat attendu ou périmètre flou), réponds
   UNIQUEMENT par 1 à 3 questions de clarification, chacune préfixée par "Q: ".
2. Sinon, reformule la demande en une tâche claire et testable (2-3 lignes).
Ne code pas. Ne choisis pas de techno."""


def _extract_questions(text: str) -> list[str]:
    qs = [line.strip()[2:].strip() for line in text.splitlines() if line.strip().startswith("Q:")]
    return [q for q in qs if q]


async def run_route(request: str, demo: bool = False):
    agents = load_agents()
    bus = Bus()
    bus.register(list(agents.keys()))
    bus.new_ticket(request, mode="route")
    run = picker(demo)

    # --- Étape PO : clarifier ou affiner ---
    if demo:
        bus.status("reporter-po", "working", task="analyse la demande")
        bus.action("reporter-po", "lit", "demande utilisateur")
        await asyncio.sleep(0.8)
        if len(request.split()) < 5:
            agent_name, reason = route_explain(request)
            bus.ask([
                f"« {request} » — quel résultat attendu exactement ?",
                f"Sur quel module / fichier ? (je partirais sur {agent_name})",
            ])
            bus.status("reporter-po", "idle")
            bus.stop()
            print("❓ Le PO attend des réponses.")
            return
        spec = request
        bus.status("reporter-po", "idle")
    else:
        spec = await run(agents["reporter-po"], PO_ROUTER_PROMPT.format(request=request), bus,
                         label=f"route: {request[:40]}")
        qs = _extract_questions(spec)
        if qs:
            bus.ask(qs)
            bus.status("reporter-po", "idle")
            bus.stop()
            print(f"❓ Le PO pose {len(qs)} question(s).")
            return

    # --- Dispatch ---
    agent_name, reason = route_explain(request)
    bus.action("reporter-po", "route", f"→ {agent_name} ({reason})")
    await asyncio.sleep(0.3)
    await run(agents[agent_name], f"Tâche routée par le PO :\n{request}\n\nContexte :\n{spec}", bus,
              label=f"{agent_name}: {request[:40]}", final="done")
    bus.complete()
    print(f"\n✅ Routé vers {agent_name}, terminé.")


# --------------------------------------------------------------------------- #
#  FLOW 4 — Méta-agent : crée un rôle OU clone un agent
# --------------------------------------------------------------------------- #
CLONE_HINTS = ("clone", "parallèle", "parallele", "plusieurs", "en même temps",
               "en meme temps", "3 ", "deux ", "trois ", "x2", "x3")


def _wants_clone(request: str) -> bool:
    low = request.lower()
    return any(h in low for h in CLONE_HINTS)


async def run_meta(request: str, demo: bool = False):
    agents = load_agents()
    bus = Bus()
    bus.register(list(agents.keys()))
    # Le méta-agent lui-même apparaît dans le studio.
    bus.register(["meta-architect"], dynamic=True, base="architect-lead")
    bus.new_ticket(request, mode="meta")
    run = picker(demo)

    if _wants_clone(request):
        await _meta_clone(request, agents, bus, run, demo)
    else:
        await _meta_create(request, agents, bus, run, demo)
    bus.complete()


async def _meta_create(request, agents, bus, run, demo):
    """Génère un NOUVEL agent .md et le fait travailler."""
    bus.status("meta-architect", "working", task="conçoit un nouvel agent")
    bus.action("meta-architect", "lit", "demande de rôle")
    await asyncio.sleep(0.6)

    # Nom + rôle dérivés de la demande.
    role = request.strip().rstrip(".")
    name = "agent-" + slugify(role.split()[-1] if role else "custom")
    # Évite la collision.
    i = 2
    base_name = name
    while (AGENTS_DIR / f"{name}.md").exists():
        name = f"{base_name}-{i}"
        i += 1

    bus.action("meta-architect", "écrit", f"{name}.md")
    md = new_agent_md(name=name, role=role[:40] or "agent custom",
                      mission=f"Réaliser la demande : {request}")
    path = AGENTS_DIR / f"{name}.md"
    path.write_text(md, encoding="utf-8")
    bus.emit("agent_created", name=name, file=str(path))
    await asyncio.sleep(0.4)
    bus.status("meta-architect", "done")

    # Le nouvel agent apparaît et bosse.
    bus.spawn(name, base="senior-coder", task=request[:50])
    agents = load_agents()  # recharge pour inclure le nouveau
    if name in agents:
        await run(agents[name], f"Première mission :\n{request}", bus,
                  label=f"{name}: {request[:40]}", final="done")
    print(f"\n✅ Agent créé : {name} (.claude/agents/{name}.md)")


async def _meta_clone(request, agents, bus, run, demo):
    """Clone un agent existant en N exemplaires parallèles."""
    import re
    base = route_request(request)
    m = re.search(r"\b([2-6])\b", request)
    n = int(m.group(1)) if m else 3
    bus.status("meta-architect", "working", task=f"clone {base} ×{n}")
    bus.action("meta-architect", "délègue", f"{n} × {base}")
    await asyncio.sleep(0.6)
    bus.status("meta-architect", "done")

    clones = []
    for k in range(1, n + 1):
        cname = f"{base}#{k}"
        bus.spawn(cname, base=base, task=f"sous-tâche {k}/{n}")
        clones.append(cname)

    agents = load_agents()
    base_agent = agents.get(base)
    if not base_agent:
        return

    async def run_clone(cname, k):
        # On fabrique un Agent éphémère qui réutilise le prompt du modèle de base.
        clone = Agent(name=cname, model=base_agent.model, tools=base_agent.tools,
                      description=base_agent.description, prompt=base_agent.prompt,
                      file=base_agent.file, extra={"base": base})
        setattr(clone, "base", base)
        await run(clone, f"Sous-tâche {k}/{n} de :\n{request}", bus,
                  label=f"{cname}: part {k}", final="done")

    await asyncio.gather(*(run_clone(c, k + 1) for k, c in enumerate(clones)))
    print(f"\n✅ {n} clones de {base} ont fini.")


# --------------------------------------------------------------------------- #
#  Council (bulles d'idées)
# --------------------------------------------------------------------------- #
COUNCIL_MEMBERS = ["architect-lead", "reviewer", "security-reviewer"]
DEMO_IDEAS = {
    "architect-lead":    "On isole derrière une interface, réversible.",
    "reviewer":          "Risque de dette si on duplique la logique.",
    "security-reviewer": "Valider les entrées avant tout, sinon injection.",
}

COUNCIL_ASK = """Tu sièges au LLM Council. Motif de la séance : {reason}.

Code / diff concerné :
{code}

Donne TON avis, sous ton angle de spécialiste, en UNE phrase de 80 caractères max.
Pas de préambule, pas de liste, pas de code. Une seule phrase."""

COUNCIL_SYNTH = """Avis rendus au LLM Council (motif : {reason}) :
{ideas}

Tranche : rends le verdict en UNE phrase de 100 caractères max.
Pas de préambule, pas de liste. La décision retenue, rien d'autre."""


def _one_line(text: str, limit: int = 110) -> str:
    """Première phrase utile d'une réponse d'agent — les bulles sont petites."""
    for line in (text or "").splitlines():
        line = line.strip().lstrip("-*# ").strip()
        if line:
            return line[:limit]
    return "…"


async def council(bus: Bus, demo: bool, reason: str = "",
                  agents: dict | None = None, code: str = ""):
    """Séance du Council.

    En démo : les idées scriptées, pour animer l'écran sans brûler de tokens.
    En réel : chaque membre délibère VRAIMENT (un appel chacun, en parallèle) et
    l'architecte synthétise le verdict. Avant, le mode réel rejouait les idées de
    démo — le conseil était un décor.
    """
    bus.council_open(COUNCIL_MEMBERS)
    bus.stage("architect-lead", f"⚖ LLM Council — {reason}")

    if demo or not agents:
        for m in COUNCIL_MEMBERS:
            bus.council_idea(m, DEMO_IDEAS.get(m, "…"))
            await asyncio.sleep(0.7)
        await asyncio.sleep(0.4)
        bus.council_close(verdict="consensus : approche réversible + validation des entrées")
        return

    members = [m for m in COUNCIL_MEMBERS if m in agents]
    prompt = COUNCIL_ASK.format(reason=reason, code=code[:4000])

    async def deliberate(name: str) -> tuple[str, str] | None:
        try:
            out = await run_agent_real(agents[name], prompt, bus,
                                       label=f"council · {name}", final="idle")
        except Exception:
            return None  # un membre absent ne fait pas tomber la séance
        idea = _one_line(out, 80)
        bus.council_idea(name, idea)
        return name, idea

    results = [r for r in await asyncio.gather(*(deliberate(m) for m in members)) if r]
    if not results:
        bus.council_close(verdict="séance sans quorum — aucun avis rendu")
        return

    ideas = "\n".join(f"- {n} : {i}" for n, i in results)
    try:
        synth = await run_agent_real(
            agents["architect-lead"],
            COUNCIL_SYNTH.format(reason=reason, ideas=ideas), bus,
            label="council · verdict", final="idle")
        verdict = _one_line(synth, 100)
    except Exception:
        verdict = f"{len(results)} avis rendus, pas de synthèse"
    bus.council_close(verdict=verdict)


# --------------------------------------------------------------------------- #
#  CLI
# --------------------------------------------------------------------------- #
def _auth_ok() -> bool:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    return (Path.home() / ".claude" / ".credentials.json").exists()


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    p = argparse.ArgumentParser()
    p.add_argument("request", nargs="*", default=[])
    p.add_argument("--demo", action="store_true")
    p.add_argument("--flow", default="pipeline", choices=["pipeline", "single", "route", "meta"])
    p.add_argument("--agent", default=None)
    args = p.parse_args()

    request = " ".join(args.request) or "Ajoute un système de login Google (OAuth)."
    demo = args.demo

    if not demo and not _auth_ok():
        print("⚠️  Aucune auth (ni ANTHROPIC_API_KEY ni `claude login`) → bascule en --demo.")
        demo = True
    elif not demo:
        print("🔑 Auth OK (abonnement ou clé).")

    try:
        if args.flow == "single":
            asyncio.run(run_single(args.agent or "senior-coder", request, demo))
        elif args.flow == "route":
            asyncio.run(run_route(request, demo))
        elif args.flow == "meta":
            asyncio.run(run_meta(request, demo))
        else:
            asyncio.run(run_pipeline(request, demo))
    except Exception as e:
        # L'erreur est déjà écrite dans state.json (bus.error) → l'UI l'affiche.
        print(f"⛔ Run interrompu : {e}")


if __name__ == "__main__":
    main()

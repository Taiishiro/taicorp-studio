"""Tests des garanties du studio — celles que le README promet noir sur blanc.

Ce qui est couvert ici a été cassé pour de vrai à un moment :
- le pipeline livrait du code que les gardiens avaient refusé ;
- le Council rejouait des idées codées en dur, même en mode réel ;
- state.json pouvait être lu à moitié écrit.

Lancement :  python -m pytest engine/tests -q     (depuis la racine du projet)
"""
from __future__ import annotations
import asyncio
import json
import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE))

import orchestrator as O  # noqa: E402
from bus import Bus  # noqa: E402


@pytest.fixture
def bus(tmp_path, monkeypatch):
    """Un Bus qui écrit dans un dossier jetable."""
    monkeypatch.setattr(Bus, "__init__",
                        lambda self, outdir=tmp_path: Bus.__wrapped_init__(self, tmp_path))
    return tmp_path


Bus.__wrapped_init__ = Bus.__init__


def _stub(verdict: str, called: list[str]):
    """Remplace l'exécution d'un agent : les 3 gardiens rendent `verdict`."""
    async def fake(agent, prompt, bus, label=None, final="idle"):
        called.append(agent.name)
        if agent.name in ("reviewer", "test-engineer", "security-reviewer"):
            return verdict
        return f"[stub] {agent.name}"
    return fake


DELIVERY = ("git-integration", "devops-infra")


# --------------------------------------------------------------------------- #
#  Le pipeline ne livre QUE si les 3 gardiens sont au vert
# --------------------------------------------------------------------------- #
def test_verdict_bloquant_ne_livre_jamais(bus, monkeypatch):
    """Un verdict bloquant maintenu ⇒ aucun commit, aucun déploiement.

    Régression : la boucle sortait après N tentatives et enchaînait sur
    git-integration + devops-infra sans jamais regarder le verdict.
    """
    called: list[str] = []
    monkeypatch.setattr(O, "picker", lambda demo: _stub("Verdict : BLOQUANT", called))

    asyncio.run(O.run_pipeline("ajoute /health", demo=True))

    assert not [a for a in called if a in DELIVERY], "du code refusé a été livré"
    assert called.count("reviewer") == O.MAX_REVIEW_ROUNDS, "chaque correction doit être re-vérifiée"


def test_verdict_vert_livre(bus, monkeypatch):
    """À l'inverse : tout au vert ⇒ on livre, en une seule passe."""
    called: list[str] = []
    monkeypatch.setattr(O, "picker", lambda demo: _stub("Verdict : OK, rien à signaler", called))

    asyncio.run(O.run_pipeline("ajoute /health", demo=True))

    assert [a for a in called if a in DELIVERY] == list(DELIVERY)
    assert called.count("reviewer") == 1, "aucune passe inutile quand c'est vert"


def test_correction_est_revérifiée(bus, monkeypatch):
    """Bloquant à la 1re passe, vert ensuite ⇒ on re-vérifie PUIS on livre."""
    called: list[str] = []
    passes = {"n": 0}

    async def fake(agent, prompt, bus_, label=None, final="idle"):
        called.append(agent.name)
        if agent.name == "reviewer":
            passes["n"] += 1
        if agent.name in ("reviewer", "test-engineer", "security-reviewer"):
            return "BLOQUANT" if passes["n"] == 1 else "OK"
        return f"[stub] {agent.name}"

    monkeypatch.setattr(O, "picker", lambda demo: fake)
    asyncio.run(O.run_pipeline("ajoute /health", demo=True))

    assert passes["n"] == 2, "la correction doit repasser devant les gardiens"
    assert [a for a in called if a in DELIVERY] == list(DELIVERY)


# --------------------------------------------------------------------------- #
#  Council
# --------------------------------------------------------------------------- #
def test_council_reel_delibere_vraiment(bus, monkeypatch):
    """En mode réel, chaque membre est réellement interrogé.

    Régression : council() acceptait `demo` mais ne l'utilisait pas et émettait
    toujours DEMO_IDEAS — le conseil était un décor.
    """
    asked: list[str] = []

    async def fake_real(agent, prompt, bus_, label=None, final="idle"):
        asked.append(agent.name)
        return "Avis du spécialiste : il faut valider les entrées."

    monkeypatch.setattr(O, "run_agent_real", fake_real)
    agents = {m: type("A", (), {"name": m})() for m in O.COUNCIL_MEMBERS}
    b = Bus()

    asyncio.run(O.council(b, demo=False, reason="test", agents=agents, code="x=1"))

    for m in O.COUNCIL_MEMBERS:
        assert m in asked, f"{m} n'a pas été consulté"
    ideas = b.state["council"]["ideas"]
    assert len(ideas) == len(O.COUNCIL_MEMBERS)
    hardcoded = set(O.DEMO_IDEAS.values())
    assert not [i for i in ideas if i["text"] in hardcoded], "idées de démo servies en mode réel"
    assert b.state["council"]["verdict"], "le verdict doit être rendu"


def test_council_demo_ne_consomme_aucun_token(bus, monkeypatch):
    """En démo, aucun appel réel — c'est tout l'intérêt du mode."""
    async def boom(*a, **k):
        raise AssertionError("le mode démo ne doit appeler aucun agent réel")

    monkeypatch.setattr(O, "run_agent_real", boom)
    b = Bus()
    asyncio.run(O.council(b, demo=True, reason="test"))
    assert len(b.state["council"]["ideas"]) == len(O.COUNCIL_MEMBERS)


# --------------------------------------------------------------------------- #
#  Bus
# --------------------------------------------------------------------------- #
def test_state_json_toujours_lisible(tmp_path):
    """state.json est écrit atomiquement : un lecteur ne voit jamais un JSON tronqué.

    Régression : write_text() laissait le fichier à moitié écrit et l'UI
    affichait « OFFLINE » par intermittence.
    """
    b = Bus(outdir=tmp_path)
    b.register(["reporter-po", "senior-coder"])
    for i in range(60):
        b.action("senior-coder", "modifie", f"fichier_{i}.py · une_fonction_au_nom_assez_long()")
        # À chaque instant, le fichier sur disque doit être un JSON complet.
        loaded = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
        assert loaded["agents"]["senior-coder"]["action"]["detail"].startswith(f"fichier_{i}.py")
    assert not list(tmp_path.glob("*.tmp")), "le fichier temporaire doit être consommé par os.replace"

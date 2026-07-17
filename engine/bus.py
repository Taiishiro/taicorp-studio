"""Bus d'événements : alimente le jeu / dashboard en temps réel.

Écrit deux choses dans engine/state/ :
- state.json   : l'état courant complet (ce que l'UI lit en boucle)
- events.jsonl : le journal append-only de tout ce qui se passe

Le jeu pixel-art (web/index.html) fetch state.json toutes les ~1 s pour bouger
les agents avec les VRAIES données.

Nouveautés v2 :
- action()   : la tâche GRANULAIRE en cours d'un agent (ex: "modifie server.py · handle_run()")
- feed       : ticker des dernières actions, lu par l'UI
- agents dynamiques : un agent cloné/créé par le méta-agent s'enregistre à chaud
- council    : idées émises par chaque membre (bulles à l'écran)
"""
from __future__ import annotations
import json
import os
import threading
import time
from pathlib import Path

STATE_DIR = Path(__file__).resolve().parent / "state"


class Bus:
    def __init__(self, outdir: Path = STATE_DIR):
        self.dir = Path(outdir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.dir / "state.json"
        self.events_path = self.dir / "events.jsonl"
        self._lock = threading.Lock()
        # On repart de l'état précédent si présent (ticket / xp / done cumulés).
        prev = {}
        if self.state_path.exists():
            try:
                prev = json.loads(self.state_path.read_text(encoding="utf-8"))
            except Exception:
                prev = {}
        self.state = {
            "ticket": prev.get("ticket", 141),
            "stage": "idle",
            "running": False,
            "mode": "pipeline",
            "tokens": prev.get("tokens", 0),
            "tokens_in": prev.get("tokens_in", 0),
            "tokens_out": prev.get("tokens_out", 0),
            "tokens_cache": prev.get("tokens_cache", 0),
            "cost": prev.get("cost", 0.0),
            "xp": prev.get("xp", 74),
            "done": prev.get("done", 12),
            "agents": {},
            "feed": [],
            "council": {"active": False, "ideas": []},
            "error": None,
        }

    # ------------------------------------------------------------------ #
    #  Enregistrement des agents (statiques + dynamiques)
    # ------------------------------------------------------------------ #
    def register(self, names: list[str], dynamic: bool = False, base: str | None = None):
        for n in names:
            self.state["agents"][n] = {
                "status": "home", "task": None, "action": None,
                "tokens": 0, "dynamic": dynamic, "base": base or n,
            }
        self._write()

    def spawn(self, name: str, base: str, task: str | None = None):
        """Un clone/agent créé apparaît à chaud dans l'UI."""
        self.state["agents"][name] = {
            "status": "working", "task": task, "action": None,
            "tokens": 0, "dynamic": True, "base": base,
        }
        self.emit("spawn", name=name, base=base, task=task or "")
        self._write()

    # ------------------------------------------------------------------ #
    #  Événements bas niveau
    # ------------------------------------------------------------------ #
    def emit(self, etype: str, **data):
        rec = {"t": round(time.time(), 3), "type": etype, **data}
        with self._lock:
            with open(self.events_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"[{etype}] " + "  ".join(f"{k}={v}" for k, v in data.items()))

    def stage(self, agent: str, label: str):
        self.state["stage"] = label
        self.emit("stage", agent=agent, label=label)
        self._write()

    def mode(self, mode: str):
        self.state["mode"] = mode
        self._write()

    def status(self, name: str, status: str, task: str | None = None):
        a = self.state["agents"].setdefault(name, {"tokens": 0, "base": name})
        a["status"] = status
        if task is not None:
            a["task"] = task
        if status in ("idle", "home", "done"):
            a["action"] = None
        self.emit("agent", name=name, status=status, task=task or "")
        self._write()

    def action(self, name: str, verb: str, detail: str = ""):
        """Tâche granulaire EN COURS : ce que l'agent fait à l'instant t."""
        a = self.state["agents"].setdefault(name, {"tokens": 0, "base": name})
        a["action"] = {"verb": verb, "detail": detail, "t": round(time.time(), 1)}
        feed = self.state.setdefault("feed", [])
        feed.insert(0, {"agent": name, "verb": verb, "detail": detail, "t": round(time.time(), 1)})
        del feed[40:]
        self.emit("action", name=name, verb=verb, detail=detail)
        self._write()

    def usage(self, name: str, tokens: int, cost: float,
              tin: int = 0, tout: int = 0, tcache: int = 0):
        self.state["tokens"] += tokens
        self.state["tokens_in"] = self.state.get("tokens_in", 0) + tin
        self.state["tokens_out"] = self.state.get("tokens_out", 0) + tout
        self.state["tokens_cache"] = self.state.get("tokens_cache", 0) + tcache
        self.state["cost"] = round(self.state["cost"] + (cost or 0), 4)
        a = self.state["agents"].setdefault(name, {"tokens": 0, "base": name})
        a["tokens"] = a.get("tokens", 0) + tokens
        self.emit("usage", name=name, tokens=tokens, cost=round(cost or 0, 4))
        self._write()

    def error(self, message: str, agent: str | None = None, fatal: bool = True):
        """Erreur remontée à l'UI (ex: quota / tokens Claude épuisés)."""
        self.state["error"] = {"msg": message, "agent": agent, "t": round(time.time(), 1)}
        if fatal:
            self.state["running"] = False
            self.state["stage"] = "⛔ " + message
        self.emit("error", message=message, agent=agent or "")
        self._write()

    # ------------------------------------------------------------------ #
    #  Council (bulles d'idées)
    # ------------------------------------------------------------------ #
    def council_open(self, members: list[str]):
        self.state["council"] = {"active": True, "members": members, "ideas": []}
        self.emit("council_open", members=members)
        self._write()

    def council_idea(self, member: str, text: str):
        c = self.state.setdefault("council", {"active": True, "ideas": []})
        c.setdefault("ideas", []).append({"member": member, "text": text, "t": round(time.time(), 1)})
        self.emit("council_idea", member=member, text=text)
        self._write()

    def council_close(self, verdict: str = ""):
        c = self.state.setdefault("council", {})
        c["active"] = False
        c["verdict"] = verdict
        self.emit("council_close", verdict=verdict)
        self._write()

    # ------------------------------------------------------------------ #
    #  Cycle de vie d'un ticket
    # ------------------------------------------------------------------ #
    def ask(self, questions: list[str]):
        """Le PO bloque et pose des questions de clarification (affichées par l'UI)."""
        self.state["questions"] = questions
        self.state["stage"] = "❓ le PO attend tes réponses"
        self.emit("ask", questions=questions)
        self._write()

    def new_ticket(self, request: str = "", mode: str = "pipeline"):
        self.state["ticket"] += 1
        self.state["running"] = True
        self.state["mode"] = mode
        self.state["request"] = request
        self.state["questions"] = []
        self.state["error"] = None
        self.emit("ticket", id=self.state["ticket"], request=request, mode=mode)
        self._write()

    def complete(self):
        self.state["done"] += 1
        self.state["xp"] = self.state["xp"] + 9
        if self.state["xp"] >= 100:
            self.state["xp"] -= 100
        self.state["running"] = False
        self.state["stage"] = "✅ livré"
        self.emit("complete", ticket=self.state["ticket"], done=self.state["done"])
        self._write()

    def stop(self):
        self.state["running"] = False
        self._write()

    def _write(self):
        """Écrit state.json de façon ATOMIQUE.

        Un write_text() direct laisse le fichier tronqué le temps de l'écriture ;
        le serveur SSE (et tout lecteur) tombait alors sur un JSON invalide et
        affichait « déconnecté » par intermittence. os.replace() est atomique sur
        le même système de fichiers : un lecteur voit l'ancien état ou le nouveau,
        jamais un état à moitié écrit.
        """
        payload = json.dumps(self.state, ensure_ascii=False, indent=2)
        with self._lock:
            tmp = self.state_path.with_suffix(".json.tmp")
            tmp.write_text(payload, encoding="utf-8")
            os.replace(tmp, self.state_path)

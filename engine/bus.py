"""Bus d'événements : alimente le jeu / dashboard en temps réel.

Écrit deux choses dans engine/state/ :
- state.json   : l'état courant complet (ce que l'UI lit en boucle)
- events.jsonl : le journal append-only de tout ce qui se passe

Le jeu pixel-art (à transformer en web/index.html) n'a qu'à fetch state.json
toutes les ~1 s pour bouger les agents avec les VRAIES données.
"""
from __future__ import annotations
import json
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
        self.state = {
            "ticket": 141, "stage": "idle", "running": True,
            "tokens": 0, "cost": 0.0, "xp": 74, "done": 12, "agents": {},
        }

    def register(self, names: list[str]):
        for n in names:
            self.state["agents"][n] = {"status": "home", "task": None, "tokens": 0}
        self._write()

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

    def status(self, name: str, status: str, task: str | None = None):
        a = self.state["agents"].setdefault(name, {"tokens": 0})
        a["status"] = status
        a["task"] = task
        self.emit("agent", name=name, status=status, task=task or "")
        self._write()

    def usage(self, name: str, tokens: int, cost: float):
        self.state["tokens"] += tokens
        self.state["cost"] = round(self.state["cost"] + (cost or 0), 4)
        a = self.state["agents"].setdefault(name, {"tokens": 0})
        a["tokens"] = a.get("tokens", 0) + tokens
        self.emit("usage", name=name, tokens=tokens, cost=round(cost or 0, 4))
        self._write()

    def new_ticket(self):
        self.state["ticket"] += 1
        self.state["running"] = True
        self.emit("ticket", id=self.state["ticket"])
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

    def _write(self):
        with self._lock:
            self.state_path.write_text(
                json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8"
            )

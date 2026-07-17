"""Petit utilitaire : remet un état propre (agents au repos), sans rien lancer."""
import agents_loader
import bus

b = bus.Bus()
b.register(list(agents_loader.load_agents().keys()))
b.state["stage"] = "idle"
b.state["running"] = False
b.state["feed"] = []
b.state["council"] = {"active": False, "ideas": []}
b.state["questions"] = []
b._write()
print("clean agents:", list(b.state["agents"].keys()))

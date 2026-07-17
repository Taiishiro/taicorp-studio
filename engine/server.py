"""Serveur du studio : sert l'interface web + l'état + lance les flows + édite les agents.

Sert la RACINE du projet sur 127.0.0.1:8765 :
  - Interface web : http://localhost:8765/web/index.html
  - État live     : SSE sur /events (fallback : /engine/state/state.json)

Endpoints d'action (POST + jeton obligatoires, cf. « Modèle de menace » plus bas) :
  POST /run           {flow, mode, agent, request}
       → lance l'orchestrateur en sous-processus (UI fluide, state.json bouge en direct).
  POST /agent         {name, content}
       → sauvegarde le .md de l'agent.
  POST /confirm-push  {branch}
       → exécute le push GitHub APRÈS confirmation explicite de l'utilisateur.

Endpoints de lecture (GET) :
  GET  /token         → jeton anti-CSRF (lisible en same-origin uniquement).
  GET  /events        → flux SSE : un snapshot d'état à chaque changement.
  GET  /agents        → liste des agents (nom, modèle, outils, description, généré ?).
  GET  /agent?name=   → contenu .md brut d'un agent (pour l'éditeur web).

──────────────────────────────────────────────────────────────────────────────
Modèle de menace — pourquoi tout ça est verrouillé
──────────────────────────────────────────────────────────────────────────────
/run exécute de vrais agents avec `permission_mode="bypassPermissions"` et l'outil
Bash sur ce dossier. Autrement dit : **/run est une exécution de code arbitraire
par construction.** Les garde-fous ne sont donc pas décoratifs :

1. Bind sur 127.0.0.1 — le réseau local n'atteint pas le studio.
2. Aucun en-tête CORS — une page tierce ne peut pas lire nos réponses.
3. Mutations en POST uniquement — tue le drive-by `<img src="/run?...">`.
4. Jeton `X-Studio-Token` — une page tierce ne peut pas le poser sans préflight,
   et le préflight échoue faute de CORS.
5. Origin/Referer vérifiés quand ils sont présents.
6. Les chemins cachés (.env, .git/…) ne sont jamais servis.

Ne mets JAMAIS ce serveur sur une interface publique. STUDIO_HOST existe pour le
cas Docker (bind 0.0.0.0 dans un conteneur isolé), pas pour l'exposer à Internet.
"""
import http.server
import json
import os
import secrets
import socketserver
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse, parse_qs

PORT = int(os.environ.get("STUDIO_PORT", "8765"))
HOST = os.environ.get("STUDIO_HOST", "127.0.0.1")
ENGINE = Path(__file__).resolve().parent
ROOT = ENGINE.parent
AGENTS_DIR = ROOT / ".claude" / "agents"
STATE_PATH = ENGINE / "state" / "state.json"
os.chdir(ROOT)

sys.path.insert(0, str(ENGINE))

# Jeton anti-CSRF, régénéré à chaque démarrage. Lisible uniquement en same-origin
# (aucun en-tête CORS n'est émis), donc une page tierce ne peut pas l'obtenir.
TOKEN = secrets.token_urlsafe(32)

# Flows et modes acceptés — on ne relaie jamais une valeur brute vers argparse.
FLOWS = ("pipeline", "single", "route", "meta")
MODES = ("demo", "real")

ALLOWED_ORIGINS = {
    f"http://localhost:{PORT}", f"http://127.0.0.1:{PORT}",
}


class Handler(http.server.SimpleHTTPRequestHandler):
    # ------------------------------------------------------------------ #
    #  Garde-fous
    # ------------------------------------------------------------------ #
    def _origin_ok(self) -> bool:
        """Refuse toute requête dont l'Origin/Referer est étranger au studio.

        Absent = client non-navigateur (curl, script) : autorisé, car le jeton
        reste exigé de toute façon.
        """
        origin = self.headers.get("Origin")
        if origin:
            return origin in ALLOWED_ORIGINS
        referer = self.headers.get("Referer")
        if referer:
            p = urlparse(referer)
            return f"{p.scheme}://{p.netloc}" in ALLOWED_ORIGINS
        return True

    def _authed(self) -> bool:
        """Jeton constant-time + origine saine. Exigé sur toute mutation."""
        if not self._origin_ok():
            return False
        sent = self.headers.get("X-Studio-Token", "")
        return secrets.compare_digest(sent, TOKEN)

    def _guard(self) -> bool:
        if self._authed():
            return True
        self._json({"error": "jeton invalide ou origine refusée"}, 403)
        return False

    def end_headers(self):
        # Pas d'Access-Control-Allow-Origin : le studio est strictement same-origin.
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        super().end_headers()

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length <= 0 or length > 1_000_000:
            return {}
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return {}

    # ------------------------------------------------------------------ #
    #  Routage
    # ------------------------------------------------------------------ #
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/token":
            # Same-origin uniquement : sans CORS, une page tierce ne lira pas la réponse.
            return self._json({"token": TOKEN})
        if path == "/events":
            return self._events()
        if path == "/agents":
            return self._list_agents()
        if path == "/agent":
            return self._get_agent()
        if path in ("/run", "/confirm-push"):
            # Jadis en GET : c'était la RCE drive-by. On refuse explicitement.
            return self._json({"error": "utilise POST"}, 405)
        if self._hidden(path):
            return self._json({"error": "interdit"}, 403)
        super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/run":
            return self._guard() and self._run()
        if path == "/agent":
            return self._guard() and self._save_agent()
        if path == "/confirm-push":
            return self._guard() and self._confirm_push()
        self._json({"error": "unknown endpoint"}, 404)

    @staticmethod
    def _hidden(path: str) -> bool:
        """Bloque .env, .git/, .claude/… — sinon on sert les secrets du projet."""
        return any(seg.startswith(".") for seg in path.split("/") if seg)

    # ------------------------------------------------------------------ #
    #  SSE — l'état poussé, au lieu d'un fetch toutes les secondes
    # ------------------------------------------------------------------ #
    def _events(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        last_mtime = 0.0
        last_beat = time.time()
        try:
            while True:
                try:
                    mtime = STATE_PATH.stat().st_mtime
                except OSError:
                    mtime = 0.0
                if mtime and mtime != last_mtime:
                    last_mtime = mtime
                    try:
                        # Lecture sûre : bus.py écrit par os.replace() atomique.
                        payload = STATE_PATH.read_text(encoding="utf-8")
                        json.loads(payload)  # ne pousse jamais un état illisible
                    except Exception:
                        payload = None
                    if payload:
                        self.wfile.write(b"event: state\ndata: ")
                        self.wfile.write(payload.replace("\n", "").encode("utf-8"))
                        self.wfile.write(b"\n\n")
                        self.wfile.flush()
                        last_beat = time.time()
                # Battement de cœur : garde le flux ouvert derrière un proxy.
                if time.time() - last_beat > 15:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    last_beat = time.time()
                time.sleep(0.15)
        except (BrokenPipeError, ConnectionResetError):
            pass  # onglet fermé — normal

    # ------------------------------------------------------------------ #
    def _run(self):
        data = self._body()
        flow = data.get("flow", "pipeline")
        mode = data.get("mode", "demo")
        agent = (data.get("agent") or "").strip()
        request = (data.get("request") or "").strip() or "Ajoute un endpoint /health"

        if flow not in FLOWS:
            return self._json({"error": f"flow inconnu : {flow}"}, 400)
        if mode not in MODES:
            return self._json({"error": f"mode inconnu : {mode}"}, 400)
        if agent and not self._agent_path(agent):
            return self._json({"error": f"agent invalide : {agent}"}, 400)

        args = [sys.executable, "orchestrator.py", "--flow", flow]
        if mode == "demo":
            args.append("--demo")
        if agent:
            args += ["--agent", agent]
        args += ["--", request]  # `--` : une demande commençant par "-" n'est pas un flag
        subprocess.Popen(args, cwd=str(ENGINE))
        self._json({"started": True, "flow": flow, "mode": mode, "agent": agent, "request": request})

    # ------------------------------------------------------------------ #
    def _list_agents(self):
        try:
            from agents_loader import load_agents
            agents = load_agents()
            out = []
            for name, a in agents.items():
                out.append({
                    "name": name,
                    "model": a.model,
                    "tools": a.tools,
                    "description": a.description,
                    "generated": str(a.extra.get("generated", "")).lower() == "true",
                    "file": a.file.name,
                })
            self._json({"agents": out})
        except Exception as e:
            self._json({"error": str(e)}, 500)

    def _get_agent(self):
        q = parse_qs(urlparse(self.path).query)
        name = q.get("name", [""])[0]
        path = self._agent_path(name)
        if not path or not path.exists():
            return self._json({"error": "not found"}, 404)
        self._json({"name": name, "file": path.name, "content": path.read_text(encoding="utf-8")})

    def _save_agent(self):
        try:
            data = self._body()
            name = data.get("name", "")
            content = data.get("content", "")
            path = self._agent_path(name)
            if not path:
                return self._json({"error": "bad name"}, 400)
            if not content.lstrip().startswith("---"):
                return self._json({"error": "le fichier doit commencer par un frontmatter '---'"}, 400)
            path.write_text(content, encoding="utf-8")
            self._json({"saved": True, "file": path.name})
        except Exception as e:
            self._json({"error": str(e)}, 500)

    def _agent_path(self, name: str):
        """Résout le .md d'un agent par son nom (frontmatter) ou son fichier.

        Le résultat est confiné à AGENTS_DIR : `name` finit en nom de fichier
        écrivable, donc une évasion ici vaudrait écriture arbitraire sur le disque.
        """
        if not name or "/" in name or "\\" in name or ".." in name or name.startswith("."):
            return None
        candidate = AGENTS_DIR / (name if name.endswith(".md") else f"{name}.md")
        try:
            candidate.resolve().relative_to(AGENTS_DIR.resolve())
        except ValueError:
            return None  # tentative d'évasion du dossier
        if candidate.exists():
            return candidate
        try:
            from agents_loader import load_agents
            a = load_agents().get(name)
            if a:
                return a.file
        except Exception:
            pass
        nums = [int(p.name[:2]) for p in AGENTS_DIR.glob("[0-9][0-9]-*.md") if p.name[:2].isdigit()]
        nxt = (max(nums) + 1) if nums else 1
        return AGENTS_DIR / f"{nxt:02d}-{name}.md"

    # ------------------------------------------------------------------ #
    def _confirm_push(self):
        """Push GitHub réel — déclenché UNIQUEMENT par un clic de confirmation."""
        data = self._body()
        branch = (data.get("branch") or "HEAD").strip()
        # Pas de méta-caractères : `branch` part vers git, et une branche est un ref.
        if not branch or any(c in branch for c in " ;|&$`\n\r\t") or branch.startswith("-"):
            return self._json({"pushed": False, "error": f"branche invalide : {branch}"}, 400)
        try:
            r = subprocess.run(
                ["git", "push", "-u", "origin", branch],
                cwd=str(ROOT), capture_output=True, text=True, timeout=60,
            )
            ok = r.returncode == 0
            self._json({"pushed": ok, "branch": branch,
                        "stdout": r.stdout[-2000:], "stderr": r.stderr[-2000:]})
        except Exception as e:
            self._json({"pushed": False, "error": str(e)}, 500)

    def log_message(self, *a):
        pass


class Server(socketserver.ThreadingTCPServer):
    """Multi-thread : sans ça, un flux SSE ou un `git push` gèle toute l'UI."""
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    if HOST not in ("127.0.0.1", "localhost", "::1"):
        print(f"⚠️  STUDIO_HOST={HOST} — /run exécute du code arbitraire.")
        print("    À réserver à un conteneur isolé. Jamais sur une interface publique.")
    print(f"Studio servi sur http://{HOST}:{PORT}")
    print(f"  → interface : http://localhost:{PORT}/web/index.html")
    print(f"  → état live : SSE sur http://localhost:{PORT}/events")
    with Server((HOST, PORT), Handler) as httpd:
        httpd.serve_forever()

"""Serveur du studio : sert l'interface web + l'état du moteur, et lance le pipeline.

Sert la RACINE du projet sur le port 8765 :
  - Interface web : http://localhost:8765/web/index.html
  - État live     : http://localhost:8765/engine/state/state.json   (lu en boucle par le jeu)

Endpoint d'action (appelé par les boutons de l'interface) :
  - GET /run?mode=demo&request=...   → lance le pipeline en simulation (aucun token)
  - GET /run?mode=real&request=...   → lance les VRAIS agents (abonnement / clé API)

Le pipeline tourne en sous-processus : l'UI reste fluide et state.json bouge en direct.
"""
import http.server
import json
import os
import socketserver
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs

PORT = 8765
ENGINE = Path(__file__).resolve().parent
ROOT = ENGINE.parent
os.chdir(ROOT)  # on sert tout le projet (web/ + engine/) depuis la même origine


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        if urlparse(self.path).path == "/run":
            return self._run()
        super().do_GET()

    def _run(self):
        q = parse_qs(urlparse(self.path).query)
        mode = q.get("mode", ["demo"])[0]
        request = q.get("request", ["Ajoute un endpoint /health"])[0]

        args = [sys.executable, "orchestrator.py"]
        if mode == "demo":
            args.append("--demo")
        args.append(request)
        # cwd = engine/ : invocation identique au lancement manuel qui marche.
        subprocess.Popen(args, cwd=str(ENGINE))

        body = json.dumps({"started": True, "mode": mode, "request": request}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # silencieux
        pass


if __name__ == "__main__":
    print(f"Studio servi sur http://localhost:{PORT}")
    print(f"  → interface : http://localhost:{PORT}/web/index.html")
    print(f"  → état live : http://localhost:{PORT}/engine/state/state.json")
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        httpd.serve_forever()

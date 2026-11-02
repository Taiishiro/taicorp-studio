"""Client ComfyUI (API HTTP locale) + remplissage des workflows « API format ».

Conventions des workflows dans `workflows/*.api.json` :
  * les valeurs à remplacer sont des chaînes `__NOM__` (ex. `"__PROMPT__"`) ;
  * `fill_workflow()` remplace une chaîne entière par la valeur typée (int,
    float, str) et une occurrence intégrée dans un texte par sa version str ;
  * un `LoraLoader` dont `lora_name` reste vide est court-circuité
    (`bypass_empty_loras`) : ses consommateurs sont rebranchés sur ses entrées.

Aucune dépendance externe : urllib suffit pour /prompt, /history, /view,
/upload/image et /free.
"""

from __future__ import annotations

import copy
import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

PLACEHOLDER_PREFIX = "__"


class ComfyError(RuntimeError):
    pass


# ── Workflows ────────────────────────────────────────────────────────────────

def load_workflow(path: str | Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        wf = json.load(fh)
    if not isinstance(wf, dict) or not all(isinstance(v, dict) and "class_type" in v
                                           for v in wf.values()):
        raise ComfyError(
            f"{path} n'est pas un workflow au format API (Menu → Export (API) dans ComfyUI)")
    # Les nœuds de commentaire (« Note », clés `_…`) n'existent pas côté serveur : on les retire.
    return {k: v for k, v in wf.items()
            if not k.startswith("_") and v.get("class_type") not in ("Note", "MarkdownNote")}


def _is_placeholder(value: Any) -> bool:
    return (isinstance(value, str) and value.startswith(PLACEHOLDER_PREFIX)
            and value.endswith(PLACEHOLDER_PREFIX) and len(value) > 4)


def find_placeholders(workflow: dict[str, Any]) -> set[str]:
    """Liste les `__NOM__` présents (utile pour valider un workflow)."""
    found: set[str] = set()

    def walk(v: Any) -> None:
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, str):
            i = 0
            while True:
                a = v.find(PLACEHOLDER_PREFIX, i)
                if a < 0:
                    break
                b = v.find(PLACEHOLDER_PREFIX, a + 2)
                if b < 0:
                    break
                token = v[a:b + 2]
                if token[2:-2].replace("_", "").isalnum():
                    found.add(token)
                i = b + 2

    walk(workflow)
    return found


def fill_workflow(template: dict[str, Any], values: dict[str, Any],
                  strict: bool = True) -> dict[str, Any]:
    """Remplace les placeholders. `values` = {"PROMPT": "...", "SEED": 42, …}."""
    tokens = {f"__{k}__": v for k, v in values.items()}

    def sub(v: Any) -> Any:
        if isinstance(v, dict):
            return {k: sub(x) for k, x in v.items()}
        if isinstance(v, list):
            return [sub(x) for x in v]
        if isinstance(v, str):
            if v in tokens:
                return tokens[v]  # valeur typée
            for tok, val in tokens.items():
                if tok in v:
                    v = v.replace(tok, str(val))
            return v
        return v

    filled = sub(copy.deepcopy(template))
    if strict:
        missing = find_placeholders(filled)
        if missing:
            raise ComfyError(f"placeholders non renseignés : {sorted(missing)}")
    return filled


def bypass_empty_loras(workflow: dict[str, Any]) -> dict[str, Any]:
    """Retire les LoraLoader sans fichier : rebranche model/clip sur l'amont."""
    wf = copy.deepcopy(workflow)
    empties = {nid for nid, node in wf.items()
               if node.get("class_type") in ("LoraLoader", "LoraLoaderModelOnly")
               and not (node.get("inputs", {}).get("lora_name") or "").strip()}
    changed = True
    while changed and empties:  # plusieurs LoRA chaînés → itérer jusqu'au point fixe
        changed = False
        for node in wf.values():
            for key, val in list(node.get("inputs", {}).items()):
                if isinstance(val, list) and len(val) == 2 and str(val[0]) in empties:
                    src = wf[str(val[0])]["inputs"]
                    upstream = src.get("model") if val[1] == 0 else src.get("clip")
                    if upstream is None:
                        raise ComfyError(f"LoraLoader {val[0]} : entrée amont manquante")
                    node["inputs"][key] = upstream
                    changed = True
    for nid in empties:
        wf.pop(nid, None)
    return wf


# ── Client HTTP ──────────────────────────────────────────────────────────────

class ComfyClient:
    """Pilote une instance ComfyUI locale : queue, attente, récupération."""

    def __init__(self, url: str = "http://127.0.0.1:8188", timeout_s: int = 1800,
                 poll_interval_s: float = 2.0):
        self.url = url.rstrip("/")
        self.timeout_s = timeout_s
        self.poll_interval_s = poll_interval_s
        self.client_id = str(uuid.uuid4())

    # -- bas niveau ----------------------------------------------------------
    def _request(self, path: str, data: bytes | None = None, method: str | None = None,
                 headers: dict[str, str] | None = None) -> bytes:
        req = urllib.request.Request(self.url + path, data=data, method=method,
                                     headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:1000]
            raise ComfyError(f"HTTP {exc.code} sur {path} : {body}") from exc
        except urllib.error.URLError as exc:
            raise ComfyError(f"ComfyUI injoignable sur {self.url} ({exc.reason}). "
                             "Lance-le d'abord : scripts/run_comfy.sh") from exc

    def _json(self, path: str, payload: dict[str, Any] | None = None) -> Any:
        data = json.dumps(payload).encode() if payload is not None else None
        raw = self._request(path, data=data, headers={"Content-Type": "application/json"}
                            if data else None)
        return json.loads(raw) if raw else {}

    # -- API publique --------------------------------------------------------
    def is_alive(self) -> bool:
        try:
            self._json("/system_stats")
            return True
        except ComfyError:
            return False

    def free_vram(self) -> None:
        """Décharge les modèles : indispensable entre SDXL, ToonCrafter et Wan sur 16 Go."""
        try:
            self._json("/free", {"unload_models": True, "free_memory": True})
        except ComfyError as exc:
            log.warning("free VRAM impossible : %s", exc)

    def upload_image(self, path: str | Path, subfolder: str = "cartoon-factory") -> str:
        """Envoie une image dans `input/` de ComfyUI ; retourne le nom à utiliser."""
        path = Path(path)
        boundary = uuid.uuid4().hex
        body = b""
        fields = {"overwrite": "true", "subfolder": subfolder, "type": "input"}
        for k, v in fields.items():
            body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n"
                     ).encode()
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; "
                 f"filename=\"{path.name}\"\r\nContent-Type: image/png\r\n\r\n").encode()
        body += path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
        raw = self._request("/upload/image", data=body,
                            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        info = json.loads(raw)
        sub = info.get("subfolder") or ""
        return f"{sub}/{info['name']}" if sub else info["name"]

    def queue(self, workflow: dict[str, Any]) -> str:
        res = self._json("/prompt", {"prompt": workflow, "client_id": self.client_id})
        if "prompt_id" not in res:
            raise ComfyError(f"réponse inattendue de /prompt : {res}")
        return res["prompt_id"]

    def wait(self, prompt_id: str) -> dict[str, Any]:
        """Attend la fin d'un prompt et retourne son entrée d'historique."""
        deadline = time.time() + self.timeout_s
        while time.time() < deadline:
            hist = self._json(f"/history/{prompt_id}")
            entry = hist.get(prompt_id)
            if entry:
                status = entry.get("status", {})
                if status.get("status_str") == "error":
                    msgs = [m for m in status.get("messages", []) if m[0] == "execution_error"]
                    detail = msgs[0][1].get("exception_message") if msgs else "?"
                    raise ComfyError(f"erreur d'exécution ComfyUI : {detail}")
                if entry.get("outputs") is not None and status.get("completed", True):
                    return entry
            time.sleep(self.poll_interval_s)
        raise ComfyError(f"timeout ({self.timeout_s}s) en attendant {prompt_id}")

    def download(self, filename: str, subfolder: str, folder_type: str, dest: Path) -> Path:
        q = urllib.parse.urlencode({"filename": filename, "subfolder": subfolder,
                                    "type": folder_type})
        data = self._request(f"/view?{q}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return dest

    def run(self, workflow: dict[str, Any], dest_dir: Path, stem: str) -> list[Path]:
        """Queue + attente + téléchargement de toutes les sorties (images et vidéos)."""
        pid = self.queue(workflow)
        log.info("ComfyUI prompt %s en file", pid)
        entry = self.wait(pid)
        outputs: list[Path] = []
        for node_out in entry.get("outputs", {}).values():
            for kind in ("images", "gifs", "videos"):
                for i, item in enumerate(node_out.get(kind, [])):
                    if item.get("type") == "temp":
                        continue  # aperçus
                    ext = Path(item["filename"]).suffix or ".png"
                    suffix = f"_{i}" if i else ""
                    dest = dest_dir / f"{stem}{suffix}{ext}"
                    outputs.append(self.download(item["filename"], item.get("subfolder", ""),
                                                 item.get("type", "output"), dest))
        if not outputs:
            raise ComfyError("le workflow n'a produit aucune sortie (SaveImage / VideoCombine ?)")
        return outputs

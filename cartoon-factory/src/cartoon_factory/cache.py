"""Cache par plan : ne jamais régénérer ce qui est déjà bon.

Pour chaque (étape, plan) on stocke une empreinte des entrées (texte, prompts,
paramètres pertinents) et la liste des fichiers produits. Une étape est
« fraîche » si l'empreinte n'a pas changé ET que tous les fichiers existent.
`--force` court-circuite le cache ; un plan marqué « rejeté » par la
vérification est relancé au prochain passage.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def fingerprint(*parts: Any) -> str:
    """Empreinte stable (sha256 tronquée) d'objets JSON-sérialisables."""
    blob = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


class StageCache:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._data: dict[str, dict[str, Any]] = {}
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self._data = {}

    @staticmethod
    def _key(stage: str, shot_id: str) -> str:
        return f"{stage}:{shot_id}"

    def is_fresh(self, stage: str, shot_id: str, fp: str, outputs: list[Path]) -> bool:
        entry = self._data.get(self._key(stage, shot_id))
        if not entry or entry.get("fingerprint") != fp or entry.get("rejected"):
            return False
        return all(Path(o).exists() for o in outputs)

    def mark_done(self, stage: str, shot_id: str, fp: str, outputs: list[Path],
                  meta: dict[str, Any] | None = None) -> None:
        self._data[self._key(stage, shot_id)] = {
            "fingerprint": fp,
            "outputs": [str(o) for o in outputs],
            "meta": meta or {},
            "rejected": False,
        }
        self._save()

    def reject(self, stage: str, shot_id: str, reason: str = "") -> None:
        """Marque un plan à refaire (utilisé par l'étape de vérification)."""
        entry = self._data.setdefault(self._key(stage, shot_id), {})
        entry["rejected"] = True
        entry["reason"] = reason
        self._save()

    def invalidate(self, stage: str | None = None, shot_id: str | None = None) -> None:
        """Supprime des entrées (tout, une étape, ou un plan d'une étape)."""
        for key in list(self._data):
            st, sid = key.split(":", 1)
            if (stage is None or st == stage) and (shot_id is None or sid == shot_id):
                del self._data[key]
        self._save()

    def get_meta(self, stage: str, shot_id: str) -> dict[str, Any]:
        return dict(self._data.get(self._key(stage, shot_id), {}).get("meta", {}))

    def entries(self) -> dict[str, dict[str, Any]]:
        return dict(self._data)

    def _save(self) -> None:
        # Écriture atomique : on ne veut jamais d'un cache.json tronqué.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

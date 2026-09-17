from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .redaction import redact


class Evidence:
    def __init__(self, root: Path, run_id: str):
        self.path = root / run_id
        self.path.mkdir(parents=True, exist_ok=True)
        self.log_path = self.path / "events.jsonl"

    def event(self, event: str, **payload: Any) -> None:
        record = {"ts": datetime.now(timezone.utc).isoformat(), "event": event, **redact(payload)}
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    async def screenshot(self, surface: Any, name: str) -> str:
        # Persist structure, never pixels containing regulated data.
        path = self.path / f"{name}-state.json"
        obs = await surface.observe()
        safe = {"controls": [{"tag": c.get("tag"), "role": c.get("role"), "type": c.get("type")}
                              for c in obs.get("controls", [])], "signal": name}
        path.write_text(json.dumps(safe, indent=2) + "\n", encoding="utf-8")
        return str(path)

    def write_json(self, name: str, value: Any) -> Path:
        path = self.path / name
        path.write_text(json.dumps(redact(value), indent=2, default=str) + "\n", encoding="utf-8")
        return path

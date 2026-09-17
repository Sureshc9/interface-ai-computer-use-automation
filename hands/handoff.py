from __future__ import annotations

import asyncio
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum


class Control(StrEnum):
    AUTOMATION = "automation"
    HUMAN = "human"


@dataclass
class Handoff:
    run_id: str
    reason: str
    step: int
    evidence: str
    control: Control = Control.AUTOMATION
    token: str = field(default_factory=lambda: secrets.token_urlsafe(18))
    human_actions: list[str] = field(default_factory=list)
    resumed: asyncio.Event = field(default_factory=asyncio.Event)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def claim(self, token: str) -> None:
        if token != self.token or self.control != Control.AUTOMATION:
            raise PermissionError("invalid or already claimed handoff")
        self.control = Control.HUMAN

    def record(self, description: str) -> None:
        if self.control != Control.HUMAN:
            raise PermissionError("human does not hold control lease")
        self.human_actions.append(description)

    def resume(self, token: str) -> None:
        if token != self.token or self.control != Control.HUMAN:
            raise PermissionError("invalid handoff state")
        self.control = Control.AUTOMATION
        self.resumed.set()


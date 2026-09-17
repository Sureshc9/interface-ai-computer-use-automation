from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse
import re

from .models import Action, Risk


class PolicyViolation(RuntimeError):
    pass


@dataclass(frozen=True)
class Policy:
    allowed_origins: frozenset[str]
    allowed_actions: frozenset[str] = field(
        default_factory=lambda: frozenset({"goto", "click", "fill", "select", "extract", "wait", "handoff"})
    )
    require_confirmation_for_risky: bool = True
    allowed_routes: tuple[str, ...] = (r"/.*",)
    permitted_clicks: frozenset[str] = frozenset({"Locate record", "Return to search"})

    def check_url(self, url: str) -> None:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self.allowed_origins:
            raise PolicyViolation(f"origin not allowlisted: {origin}")
        if parsed.username or parsed.password or not any(re.fullmatch(p, parsed.path or "/") for p in self.allowed_routes):
            raise PolicyViolation("route or URL credentials not permitted")

    def check_action(self, action: Action, *, confirmed: bool = False) -> None:
        if action.kind not in self.allowed_actions:
            raise PolicyViolation(f"action not allowlisted: {action.kind}")
        if action.kind == "goto":
            self.check_url(action.value or "")
        if action.kind == "click" and action.target and action.target.value not in self.permitted_clicks and not confirmed:
            raise PolicyViolation("unreviewed click requires operator confirmation")
        if action.risk == Risk.RISKY and self.require_confirmation_for_risky and not confirmed:
            raise PolicyViolation("risky action requires explicit human confirmation")

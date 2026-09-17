from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from typing import Any

from openai import AsyncOpenAI

from .models import Decision


SYSTEM = """You control a banking training UI. Return exactly one conservative next action as JSON.
Use semantic role/name or label locators; CSS is a last resort. Never invent controls. Mark goal_met only
after visible evidence proves it. Values may reference inputs as {{name}}. Do not include sensitive data in rationale.
JSON shape: {"action": {"kind":"goto|click|fill|select|extract|wait|handoff", "target":
{"strategy":"role_name|label|text|css","value":"...","role":"...","exact":true,"fallbacks":[]},
"value":"...","output":null,"risk":"safe|risky","rationale":"..."}, "goal_met":false,"summary":"..."}.
Use null action when goal_met is true."""


class Planner(ABC):
    @abstractmethod
    async def decide(self, goal: str, observation: dict[str, Any], history: list[dict[str, Any]]) -> Decision: ...


class OpenAIPlanner(Planner):
    def __init__(self, model: str | None = None):
        self.client = AsyncOpenAI()
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-5.6-luna")

    async def decide(self, goal: str, observation: dict[str, Any], history: list[dict[str, Any]]) -> Decision:
        response = await self.client.responses.create(
            model=self.model,
            instructions=SYSTEM,
            input=json.dumps({"goal": goal, "observation": observation, "recent_actions": history[-6:]}),
        )
        text = response.output_text.strip().removeprefix("```json").removesuffix("```").strip()
        return Decision.model_validate_json(text)


class ScriptedPlanner(Planner):
    """Offline test double; evidence from this planner must never be labeled live LLM discovery."""
    def __init__(self, decisions: list[Decision]):
        self.decisions = iter(decisions)

    async def decide(self, goal: str, observation: dict[str, Any], history: list[dict[str, Any]]) -> Decision:
        return next(self.decisions)


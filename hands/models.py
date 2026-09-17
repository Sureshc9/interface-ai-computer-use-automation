from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Risk(StrEnum):
    SAFE = "safe"
    RISKY = "risky"


class Locator(StrictModel):
    strategy: Literal["role_name", "label", "text", "css"]
    value: str
    role: str | None = None
    exact: bool = True
    fallbacks: list["Locator"] = Field(default_factory=list, max_length=2)


class Action(StrictModel):
    kind: Literal["goto", "click", "fill", "select", "extract", "wait", "handoff"]
    target: Locator | None = None
    value: str | None = None
    output: str | None = None
    risk: Risk = Risk.SAFE
    rationale: str = ""
    retries: int = Field(default=0, ge=0, le=3)
    retry_delay_ms: int = Field(default=300, ge=0, le=3000)

    @model_validator(mode="after")
    def require_fields(self) -> "Action":
        if self.kind in {"click", "fill", "select", "extract"} and not self.target:
            raise ValueError(f"{self.kind} requires target")
        if self.kind == "extract" and not self.output:
            raise ValueError("extract requires output")
        return self


class Parameter(StrictModel):
    type: Literal["string", "integer", "number", "boolean"]
    description: str
    pattern: str | None = None
    sensitive: bool = False


class Output(StrictModel):
    type: Literal["string", "integer", "number", "boolean"]
    description: str
    sensitive: bool = False


class Checkpoint(StrictModel):
    kind: Literal["url", "visible", "text"]
    value: str
    target: Locator | None = None


class BusinessOutcome(StrictModel):
    code: str
    target: Locator
    message: str


class Capability(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    capability_id: str
    version: str = "1.0.0"
    title: str
    description: str
    vendor_app: str
    compatible_variants: list[str] = Field(default_factory=list)
    inputs: dict[str, Parameter]
    outputs: dict[str, Output]
    steps: list[Action]
    checkpoint: Checkpoint
    business_outcomes: list[BusinessOutcome] = Field(default_factory=list)
    approval: Literal["draft", "approved"] = "draft"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def output_contract(self) -> "Capability":
        if {s.output for s in self.steps if s.output} != set(self.outputs):
            raise ValueError("extract steps must exactly match declared outputs")
        return self


class FailureDetail(StrictModel):
    code: str
    step: int | None = None
    expected: str | None = None
    observed: str | None = None
    evidence: str | None = None


class RunResult(StrictModel):
    status: Literal["success", "business_outcome", "failure", "escalated"]
    capability_id: str | None = None
    outputs: dict[str, Any] = Field(default_factory=dict)
    outcome: str | None = None
    failure: FailureDetail | None = None
    run_id: str


class Decision(StrictModel):
    action: Action | None = None
    goal_met: bool = False
    summary: str = ""

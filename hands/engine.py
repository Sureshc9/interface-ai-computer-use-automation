from __future__ import annotations

import re
import uuid
import asyncio
import json
from playwright.async_api import TimeoutError as SurfaceTimeout
from pathlib import Path
from typing import Any

from .evidence import Evidence
from .handoff import Handoff
from .llm import Planner
from .models import Action, Capability, Checkpoint, FailureDetail, RunResult, Parameter, Output
from .policy import Policy, PolicyViolation
from .surface import Surface


def bind(value: str | None, inputs: dict[str, Any]) -> str | None:
    if value is None:
        return None
    return re.sub(r"\{\{([a-zA-Z_][a-zA-Z0-9_]*)\}\}", lambda m: str(inputs[m.group(1)]), value)


def validate_inputs(capability: Capability, inputs: dict[str, Any]) -> None:
    for name, spec in capability.inputs.items():
        if name not in inputs:
            raise ValueError(f"missing input: {name}")
        value = inputs[name]
        expected = {"string": str, "integer": int, "number": (int, float), "boolean": bool}[spec.type]
        if not isinstance(value, expected) or (spec.type in {"integer", "number"} and isinstance(value, bool)):
            raise ValueError(f"input {name} must be {spec.type}")
        if spec.pattern and (not isinstance(value, str) or not re.fullmatch(spec.pattern, value)):
            raise ValueError(f"input {name} does not match its declared pattern")


def loggable_action(action: Action) -> dict[str, Any]:
    data = action.model_dump()
    if action.kind in {"fill", "select"} and action.value is not None:
        data["value"] = "[PARAMETER]"
    return data


async def checkpoint(surface: Surface, cap: Capability) -> bool:
    cp = cap.checkpoint
    if cp.kind == "url":
        return cp.value in await surface.current_url()
    obs = await surface.observe()
    if cp.target and hasattr(surface, "resolve"):
        try:
            locator = await surface.resolve(cp.target)
            return cp.kind == "visible" or cp.value in await locator.inner_text()
        except LookupError:
            return False
    return cp.value in obs["visible_text"]


async def execute(surface, action, policy, operator=None, ev=None, step=0):
    if action.kind == "handoff":
        if not operator:
            raise RuntimeError("human operator unavailable")
        handoff = Handoff(ev.path.name, "explicit intervention requested", step, "live session")
        await operator(handoff, surface)
        if not handoff.resumed.is_set():
            raise RuntimeError("operator did not return control")
        policy.check_url(await surface.current_url())
        ev.event("human_handoff", step=step, actions=handoff.human_actions)
        return None
    try:
        policy.check_action(action)
    except PolicyViolation:
        if operator is None:
            raise
        handoff = Handoff(ev.path.name, "policy confirmation required", step, "live session")
        await operator(handoff, surface)
        if not handoff.resumed.is_set():
            raise RuntimeError("operator did not return control")
        ev.event("human_handoff", step=step, actions=handoff.human_actions)
        policy.check_action(action, confirmed=True)
    for attempt in range(action.retries + 1):
        try:
            result = await surface.act(action, action.value)
            policy.check_url(await surface.current_url())
            return result
        except (LookupError, TimeoutError, SurfaceTimeout) as exc:
            # Never repeat a click: it may already have committed a mutation.
            if attempt >= action.retries or action.kind not in {"extract", "fill", "wait"}:
                if operator:
                    handoff = Handoff(ev.path.name, "action could not safely complete", step, "live session")
                    await operator(handoff, surface)
                    if not handoff.resumed.is_set():
                        raise RuntimeError("operator did not resume")
                    ev.event("human_handoff", step=step, actions=handoff.human_actions)
                    policy.check_url(await surface.current_url())
                    if action.kind == "extract":
                        return await surface.act(action, action.value)
                    return None
                raise
            ev.event("retry", step=step, attempt=attempt + 1, code=type(exc).__name__)
            await asyncio.sleep(action.retry_delay_ms / 1000)
        except Exception:
            if not operator:
                raise
            handoff = Handoff(ev.path.name, "unexpected UI state requires manual repair", step, "live session")
            await operator(handoff, surface)
            if not handoff.resumed.is_set():
                raise RuntimeError("operator did not return control")
            policy.check_url(await surface.current_url())
            ev.event("human_handoff", step=step, actions=handoff.human_actions)
            if action.kind == "extract":
                return await surface.act(action, action.value)
            return None


async def discover(*, goal: str, target: str, surface: Surface, planner: Planner, policy: Policy,
                   evidence_root: Path, max_steps: int = 12, inputs=None, artifact_path=None,
                   capability_id="discovered.flow", success_checkpoint=None, operator=None) -> tuple[list[Action], RunResult]:
    run_id = f"discovery-{uuid.uuid4().hex[:10]}"
    ev = Evidence(evidence_root, run_id)
    policy.check_url(target)
    if hasattr(surface, "configure_policy"):
        await surface.configure_policy(policy)
    await surface.act(Action(kind="goto", value=target, rationale="Open allowed entry point"), target)
    actions: list[Action] = []
    history: list[dict[str, Any]] = []
    for step in range(max_steps):
        obs = await surface.observe()
        policy.check_url(await surface.current_url())
        ev.event("observation", step=step, control_count=len(obs.get("controls", [])))
        try:
            decision = await asyncio.wait_for(planner.decide(goal, obs, history), timeout=60)
        except Exception as exc:
            path = await ev.screenshot(surface, "planner-failure")
            ev.event("failure", step=step, code=type(exc).__name__)
            return actions, RunResult(status="failure", run_id=run_id,
                failure=FailureDetail(code="PLANNER_FAILED", step=step, expected="valid bounded decision",
                                     observed=type(exc).__name__, evidence=path))
        safe_decision = decision.model_dump()
        if decision.action:
            safe_decision["action"] = loggable_action(decision.action)
        ev.event("decision", step=step, kind=decision.action.kind if decision.action else "complete")
        if decision.goal_met:
            if not success_checkpoint:
                return actions, RunResult(status="failure", run_id=run_id,
                    failure=FailureDetail(code="CHECKPOINT_REQUIRED", step=step))
            cap = Capability(capability_id=capability_id, title=capability_id,
                description="Recorded discovery capability", vendor_app="northstar-core",
                inputs={k: Parameter(type="string", description="Invocation parameter", sensitive=True) for k in (inputs or {})},
                outputs={a.output: Output(type="string", description="Extracted UI data", sensitive=True) for a in actions if a.output},
                steps=actions, checkpoint=success_checkpoint)
            if not await checkpoint(surface, cap):
                return actions, RunResult(status="failure", run_id=run_id,
                    failure=FailureDetail(code="FALSE_COMPLETION", step=step, expected="verified checkpoint"))
            serialized = cap.model_dump_json(indent=2)
            if any(str(value) in serialized for value in (inputs or {}).values() if str(value)):
                return actions, RunResult(status="failure", run_id=run_id,
                    failure=FailureDetail(code="SENSITIVE_LITERAL_IN_ARTIFACT", step=step))
            if artifact_path:
                Path(artifact_path).parent.mkdir(parents=True, exist_ok=True)
                Path(artifact_path).write_text(cap.model_dump_json(indent=2) + "\n")
            ev.write_json("capability.json", cap.model_dump(mode="json"))
            path = await ev.screenshot(surface, "success")
            return actions, RunResult(status="success", run_id=run_id, outputs={"evidence": path})
        if not decision.action:
            break
        try:
            raw = decision.action
            recorded_value = raw.value
            for key, supplied in (inputs or {}).items():
                if recorded_value == str(supplied):
                    recorded_value = "{{" + key + "}}"
            recorded = raw.model_copy(update={"value": recorded_value, "rationale": "Recorded policy-checked action"})
            bound = recorded.model_copy(update={"value": bind(recorded.value, inputs or {})})
            value = await execute(surface, bound, policy, operator, ev, step)
            actions.append(recorded)
            history.append({"action": decision.action.model_dump(), "result": value})
        except Exception as exc:
            path = await ev.screenshot(surface, f"failure-step-{step}")
            ev.event("failure", step=step, code=type(exc).__name__, state=path)
            return actions, RunResult(status="failure", run_id=run_id,
                failure=FailureDetail(code="DISCOVERY_ACTION_FAILED", step=step, observed=type(exc).__name__, evidence=path))
    path = await ev.screenshot(surface, "stuck")
    ev.event("escalation_requested", reason="max steps or dead-end", screenshot=path)
    return actions, RunResult(status="escalated", run_id=run_id,
        failure=FailureDetail(code="DISCOVERY_STUCK", step=len(actions), evidence=path))


async def replay(*, capability: Capability, inputs: dict[str, Any], surface: Surface, policy: Policy,
                 target: str, evidence_root: Path, confirmed_risky: bool = False, operator=None) -> RunResult:
    run_id = f"replay-{uuid.uuid4().hex[:10]}"
    ev = Evidence(evidence_root, run_id)
    index = None
    action = None
    try:
        if capability.approval != "approved":
            raise PolicyViolation("capability must be reviewed and approved before replay")
        policy.check_url(target)
        if hasattr(surface, "configure_policy"):
            await surface.configure_policy(policy)
        validate_inputs(capability, inputs)
        await surface.act(Action(kind="goto", value=target), target)
        outputs: dict[str, Any] = {}
        for index, raw in enumerate(capability.steps):
            action = raw.model_copy(update={"value": bind(raw.value, inputs)})
            policy.check_url(await surface.current_url())
            ev.event("step_started", step=index, action=loggable_action(action))
            obs = await surface.observe()
            for outcome in capability.business_outcomes:
                if outcome.target.value in obs["visible_text"]:
                    ev.event("business_outcome", code=outcome.code, step=index)
                    return RunResult(status="business_outcome", capability_id=capability.capability_id,
                                     outcome=outcome.code, run_id=run_id)
            result = await execute(surface, action, policy, operator, ev, index)
            if action.output:
                spec = capability.outputs[action.output]
                if spec.type == "string":
                    outputs[action.output] = str(result)
                elif spec.type == "integer":
                    outputs[action.output] = int(result)
                elif spec.type == "number":
                    outputs[action.output] = float(result)
                elif str(result).lower() in {"true", "false"}:
                    outputs[action.output] = str(result).lower() == "true"
                else:
                    raise ValueError("extracted output does not match boolean contract")
            logged_result = result
            if action.output and capability.outputs[action.output].sensitive:
                logged_result = "[REDACTED-SENSITIVE-OUTPUT]"
            ev.event("step_completed", step=index, output=logged_result)
        obs = await surface.observe()
        for outcome in capability.business_outcomes:
            if outcome.target.value in obs["visible_text"]:
                return RunResult(status="business_outcome", capability_id=capability.capability_id,
                                 outcome=outcome.code, run_id=run_id)
        if not await checkpoint(surface, capability):
            raise RuntimeError(f"checkpoint not satisfied: {capability.checkpoint.value}")
        await ev.screenshot(surface, "success")
        result = RunResult(status="success", capability_id=capability.capability_id, outputs=outputs, run_id=run_id)
        persisted = result.model_dump(mode="json")
        persisted["outputs"] = {
            name: ("[REDACTED-SENSITIVE-OUTPUT]" if capability.outputs[name].sensitive else value)
            for name, value in outputs.items()
        }
        ev.write_json("result.json", persisted)
        return result
    except Exception as exc:
        path = await ev.screenshot(surface, "failure")
        ev.event("failure", step=index, code=type(exc).__name__, state=path)
        return RunResult(status="failure", capability_id=capability.capability_id, run_id=run_id,
            failure=FailureDetail(code=type(exc).__name__.upper(), step=index,
                expected=action.kind if action else "validated invocation", observed=type(exc).__name__, evidence=path))

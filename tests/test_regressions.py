from pathlib import Path
import pytest
from hands.engine import discover, execute
from hands.evidence import Evidence
from hands.llm import ScriptedPlanner
from hands.models import Action, Capability, Checkpoint, Decision, Locator
from hands.policy import Policy, PolicyViolation
from test_core import FakeSurface


def test_navigation_and_unknown_click_fail_closed():
    p = Policy(frozenset({"http://127.0.0.1:8765"}))
    with pytest.raises(PolicyViolation):
        p.check_action(Action(kind="goto", value="https://evil.example"))
    with pytest.raises(PolicyViolation):
        p.check_action(Action(kind="click", target=Locator(strategy="text", value="Transfer funds")))


@pytest.mark.asyncio
async def test_discovery_saves_parameterized_draft(tmp_path):
    p = Policy(frozenset({"http://127.0.0.1:8765"}))
    actions = [Action(kind="fill", target=Locator(strategy="label", value="Member number"), value="12345")]
    planner = ScriptedPlanner([Decision(action=actions[0]), Decision(goal_met=True)])
    path = tmp_path / "cap.json"
    _, result = await discover(goal="Lookup supplied member", target="http://127.0.0.1:8765",
        surface=FakeSurface(), planner=planner, policy=p, evidence_root=tmp_path,
        inputs={"member_id":"12345"}, artifact_path=path, success_checkpoint=Checkpoint(kind="text", value="Record loaded"))
    assert result.status == "success"
    cap = Capability.model_validate_json(path.read_text())
    assert cap.approval == "draft"
    assert cap.steps[0].value == "{{member_id}}"
    assert "12345" not in path.read_text()


@pytest.mark.asyncio
async def test_real_control_transfer_on_policy_block(tmp_path):
    surface = FakeSurface()
    surface.url = "http://127.0.0.1:8765"
    called = []
    async def operator(handoff, same_surface):
        assert same_surface is surface
        handoff.claim(handoff.token)
        handoff.record("Reviewed live control")
        called.append(True)
        handoff.resume(handoff.token)
    await execute(surface, Action(kind="click", target=Locator(strategy="text", value="Unknown")),
        Policy(frozenset({surface.url})), operator, Evidence(tmp_path, "handoff"), 0)
    assert called


@pytest.mark.asyncio
async def test_bounded_retry(tmp_path):
    class Slow(FakeSurface):
        attempts = 0
        async def act(self, action, value=None):
            self.attempts += 1
            if self.attempts == 1: raise LookupError("not loaded")
            return "ready"
    s = Slow(); s.url = "http://127.0.0.1:8765"
    result = await execute(s, Action(kind="extract", target=Locator(strategy="text", value="Balance"),
        output="balance", retries=1, retry_delay_ms=0), Policy(frozenset({s.url})), ev=Evidence(tmp_path,"retry"))
    assert result == "ready" and s.attempts == 2

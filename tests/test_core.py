from pathlib import Path

import pytest
import yaml

from hands.engine import bind, replay, validate_inputs
from hands.models import Action, Capability, Locator, Risk
from hands.policy import Policy, PolicyViolation
from hands.redaction import redact
from hands.surface import Surface


class FakeSurface(Surface):
    def __init__(self, texts=None, extract="$4,281.06"):
        self.url = "about:blank"; self.texts = iter(texts or ["Member inquiry", "Member detail Record loaded"]); self.text = ""; self.extract = extract
    async def observe(self):
        try: self.text = next(self.texts)
        except StopIteration: pass
        return {"url": self.url, "title": "", "controls": [], "visible_text": self.text}
    async def act(self, action, value=None):
        if action.kind == "goto": self.url = value
        if action.kind == "extract": return self.extract
    async def current_url(self): return self.url
    async def screenshot(self, path): path.write_bytes(b"fake")


@pytest.fixture
def cap():
    return Capability.model_validate(yaml.safe_load(Path("artifacts/member-balance.yaml").read_text()))


def test_binding_and_redaction():
    assert bind("member={{member_id}}", {"member_id": "12345"}) == "member=12345"
    assert redact({"token": "abc", "note": "SSN 123-45-6789"}) == {"token": "[REDACTED]", "note": "SSN [REDACTED-SSN]"}


def test_typed_input_contract(cap):
    validate_inputs(cap, {"member_id": "12345"})
    with pytest.raises(ValueError, match="declared pattern"):
        validate_inputs(cap, {"member_id": "abc"})


def test_policy_blocks_origin_and_risky_action():
    policy = Policy(frozenset({"http://127.0.0.1:8765"}))
    with pytest.raises(PolicyViolation): policy.check_url("https://example.com")
    with pytest.raises(PolicyViolation):
        policy.check_action(Action(kind="click", target=Locator(strategy="text", value="Submit"), risk=Risk.RISKY))


@pytest.mark.asyncio
async def test_replay_success(cap, tmp_path):
    result = await replay(capability=cap, inputs={"member_id":"12345"}, surface=FakeSurface(),
        policy=Policy(frozenset({"http://127.0.0.1:8765"})), target="http://127.0.0.1:8765", evidence_root=tmp_path)
    assert result.status == "success"
    assert result.outputs == {"savings_balance": "$4,281.06"}


@pytest.mark.asyncio
async def test_business_outcome_is_not_failure(cap, tmp_path):
    result = await replay(capability=cap, inputs={"member_id":"00000"}, surface=FakeSurface(["Member inquiry", "No member record found"]),
        policy=Policy(frozenset({"http://127.0.0.1:8765"})), target="http://127.0.0.1:8765", evidence_root=tmp_path)
    assert result.status == "business_outcome"
    assert result.outcome == "MEMBER_NOT_FOUND"

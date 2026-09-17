import pytest

from hands.handoff import Control, Handoff


def test_exclusive_control_lease_and_audit():
    handoff = Handoff("run-1", "confirmation needed", 2, "shot.png")
    handoff.claim(handoff.token)
    assert handoff.control == Control.HUMAN
    handoff.record("Reviewed member detail and dismissed duplicate-record dialog")
    handoff.resume(handoff.token)
    assert handoff.control == Control.AUTOMATION
    assert handoff.resumed.is_set()
    assert len(handoff.human_actions) == 1
    with pytest.raises(PermissionError):
        handoff.claim("wrong")


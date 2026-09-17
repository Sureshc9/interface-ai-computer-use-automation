import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

from hands.engine import replay
from hands.models import Capability
from hands.policy import Policy
from hands.surface import BrowserSurface


@pytest.mark.asyncio
async def test_real_browser_success_and_not_found(tmp_path):
    server = subprocess.Popen([sys.executable, "-m", "hands.demo_app", "--port", "8876"])
    time.sleep(.4)
    cap = Capability.model_validate(yaml.safe_load(Path("artifacts/member-balance.yaml").read_text()))
    policy = Policy(frozenset({"http://127.0.0.1:8876"}))
    try:
        async with BrowserSurface() as surface:
            ok = await replay(capability=cap, inputs={"member_id":"12345"}, surface=surface, policy=policy,
                target="http://127.0.0.1:8876", evidence_root=tmp_path)
            assert ok.status == "success" and ok.outputs["savings_balance"] == "$4,281.06"
        async with BrowserSurface() as surface:
            missing = await replay(capability=cap, inputs={"member_id":"00000"}, surface=surface, policy=policy,
                target="http://127.0.0.1:8876", evidence_root=tmp_path)
            assert missing.status == "business_outcome" and missing.outcome == "MEMBER_NOT_FOUND"
    finally:
        server.terminate(); server.wait(timeout=3)


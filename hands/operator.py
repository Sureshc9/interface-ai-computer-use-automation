"""Minimal real operator transport: headed browser plus terminal control transfer."""
import asyncio


async def terminal_operator(handoff, surface):
    handoff.claim(handoff.token)
    print(f"Automation paused at step {handoff.step}: {handoff.reason}")
    print("Operate the SAME open browser. No automation actions run until you return control.")
    description = await asyncio.to_thread(input, "Describe your manual actions (no sensitive data), then Enter to resume: ")
    # Do not persist free-form human text, which can contain PII.
    handoff.record("Operator reviewed live session and returned control")
    handoff.resume(handoff.token)

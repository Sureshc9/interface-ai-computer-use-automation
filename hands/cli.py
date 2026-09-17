from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import yaml

from .engine import discover, replay
from .llm import OpenAIPlanner
from .models import Capability, Checkpoint
from .operator import terminal_operator
from .policy import Policy
from .surface import BrowserSurface


def policy_for(url: str) -> Policy:
    from urllib.parse import urlparse
    p = urlparse(url)
    return Policy(allowed_origins=frozenset({f"{p.scheme}://{p.netloc}"}), allowed_routes=(r"/", r"/lookup"))


async def run(args):
    evidence = Path(args.evidence)
    async with BrowserSurface(headless=not args.headed) as surface:
        operator = terminal_operator if args.human and args.headed else None
        if args.human and not args.headed:
            raise ValueError("--human requires --headed for live takeover")
        if args.command == "discover":
            actions, result = await discover(goal=args.goal, target=args.target, surface=surface,
                planner=OpenAIPlanner(args.model), policy=policy_for(args.target), evidence_root=evidence,
                inputs=dict(item.split("=", 1) for item in args.input), artifact_path=args.save,
                capability_id=args.capability_id, success_checkpoint=Checkpoint(kind="text", value=args.checkpoint),
                operator=operator)
            print(json.dumps(result.model_dump(mode="json"), indent=2))
            print(json.dumps([a.model_dump(mode="json") for a in actions], indent=2))
        else:
            cap = Capability.model_validate(yaml.safe_load(Path(args.artifact).read_text()))
            inputs = dict(item.split("=", 1) for item in args.input)
            result = await replay(capability=cap, inputs=inputs, surface=surface, policy=policy_for(args.target),
                target=args.target, evidence_root=evidence, operator=operator)
            print(json.dumps(result.model_dump(mode="json"), indent=2))


def main():
    p=argparse.ArgumentParser(prog="hands"); p.add_argument("--evidence", default="run-output")
    sub=p.add_subparsers(dest="command", required=True)
    d=sub.add_parser("discover"); d.add_argument("--goal", required=True); d.add_argument("--target", required=True); d.add_argument("--model"); d.add_argument("--headed", action="store_true")
    d.add_argument("--save", required=True); d.add_argument("--checkpoint", required=True)
    d.add_argument("--capability-id", default="northstar.member.read_savings_balance")
    d.add_argument("--input", action="append", default=[]); d.add_argument("--human", action="store_true")
    r=sub.add_parser("replay"); r.add_argument("--artifact", required=True); r.add_argument("--target", required=True); r.add_argument("--input", action="append", default=[]); r.add_argument("--confirm-risky", action="store_true"); r.add_argument("--headed", action="store_true")
    r.add_argument("--human", action="store_true")
    asyncio.run(run(p.parse_args()))

if __name__ == "__main__": main()

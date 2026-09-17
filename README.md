# Legacy UI Capabilities

This project turns one model-driven interaction with a legacy-style UI into a typed capability that replays without a model. The included Northstar Core training app intentionally uses table layout, server-rendered navigation, and no test IDs. The useful automation surface is its accessible names, not its DOM structure.

## Setup

Requirements: Python 3.11+ and an OpenAI API key only for live discovery.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
playwright install chromium
```

Run the local target in terminal one:

```bash
python -m hands.demo_app --port 8765
```

## Demo path

Run genuine model-driven discovery (the key is read only by the SDK and is never logged):

```bash
export OPENAI_API_KEY='...'
hands discover \
  --goal 'Look up member 12345 and read their current savings balance' \
  --target http://127.0.0.1:8765 \
  --input member_id=12345 \
  --checkpoint 'Record loaded' \
  --save artifacts/discovered-member-balance.json
```

Review the discovered actions, then replay the reviewed capability with no model call:
Discovery saves a **draft** capability. Review its parameters, outputs, locators, and checkpoint,
add known business outcomes, and change `approval` to `approved` before replay.

```bash
hands replay \
  --artifact artifacts/member-balance.yaml \
  --target http://127.0.0.1:8765 \
  --input member_id=12345
```

Exercise a known business outcome (exit result is structured, not a crash):

```bash
hands replay --artifact artifacts/member-balance.yaml \
  --target http://127.0.0.1:8765 --input member_id=00000
```

Use `--headed` to watch either run. `OPENAI_MODEL` can override the cost-conscious default. Artifacts and checked-in evidence contain no credentials or raw PII. Fresh runtime evidence defaults to ignored `run-output/`.

## Run without live services

```bash
pytest -q
```

The test suite uses a scripted planner/fake surface for contract tests and a real Chromium session against the local app for replay. It does not pretend an offline planner run is LLM evidence.

## Repository map

- `hands/llm.py`: provider boundary and observe-decide-act planner.
- `hands/surface.py`: perception/action port and Playwright adapter.
- `hands/models.py`: strict versioned artifact and result contracts.
- `hands/engine.py`: discovery and deterministic replay.
- `hands/policy.py`, `hands/redaction.py`: enforcement and data minimization.
- `hands/handoff.py`: exclusive control lease for same-session operator takeover.
- `artifacts/`: approved, reviewable capability definitions.
- `evidence/`: sanitized example artifacts and run logs.
- `REPORT.md`: decisions, trade-offs, and extension design.

## Safety properties

Every navigation origin and action type is checked at execution time. Unknown clicks require a live operator. Locators must resolve uniquely. Logs are data-minimized, failures receive structural state evidence, and outputs use a three-way contract: `success`, `business_outcome`, or `failure` (plus `escalated` when no operator is available).
Failure evidence is now a data-minimized structural DOM snapshot, not raw screenshots.
For real same-session handoff, add `--headed --human`: automation pauses while the operator
uses the open browser, then Enter returns control. Unattended execution never confirms unknown clicks.

The current checked-in evidence contains real deterministic browser replays. See `evidence/README.md` for the explicit live-discovery evidence status; the project does not mislabel scripted test output as a model run.

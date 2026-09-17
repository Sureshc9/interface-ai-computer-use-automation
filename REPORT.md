# 1. Architecture

The system is a small hexagonal core. `Surface` is the port for observation and action; Playwright is one adapter. `Planner` is the discovery-only decision port; OpenAI is one adapter. The discovery engine feeds a bounded, redacted observation to the planner, policy-checks one returned action, executes it, and records evidence. The replay engine consumes only a reviewed `Capability`: no planner object exists on that path.

The concrete target is a local server-rendered member-servicing app. This avoids questionable public-site automation while exercising search, detail, extraction, not-found, and expired-session states. A single process is deliberate: it makes session ownership and failure semantics inspectable. Persistence, queues, and fleet scheduling are orthogonal to the contract demonstrated here.

# 2. Artifact schema

The YAML artifact is strict, versioned, readable, and agent-invocable. Its contract separates metadata, typed inputs and outputs, ordered actions, locator strategies, business outcomes, and a terminal checkpoint. Template values such as `{{member_id}}` are bound only at invocation, so no member data is baked into the capability. Each locator records a primary strategy and at most two deliberate fallbacks. A human-readable rationale makes robustness choices reviewable. Approval is explicit (`draft` or `approved`) rather than implied by file existence.

The artifact is not a transcript. Raw reasoning and page text are not persisted. Discovery saves a parameterized draft after independent checkpoint verification; a reviewer supplies business-outcome rules and approves it. Schema version governs parser compatibility while semantic capability version describes behavior changes.

# 3. Determinism & error handling

Replay walks a fixed list, binds validated inputs, enforces policy before every action, requires a unique visible locator, waits at the adapter boundary, extracts declared outputs, and verifies an independent checkpoint. Accessible label and role/name locators are preferred because they express operator intent and tolerate layout changes. CSS is allowed only when it targets a semantic attribute; coordinate clicks are intentionally absent from this web adapter.

Results distinguish success with typed outputs, expected business outcomes such as `MEMBER_NOT_FOUND`, and failures with a code, step, expected/observed state, and screenshot path. Known interstitial recovery would be modeled as a bounded conditional step with retry budget; this slice identifies session expiry as a caller-visible outcome because silently reauthenticating could cross an authorization boundary. Unknown dialogs, ambiguous locators, failed checkpoints, policy violations, and timeouts stop. They never trigger an open-ended model fallback.

# 4. Heterogeneity & multi-tenant

`Surface` is the seam. A desktop adapter could observe an accessibility tree and act through UI Automation/AX APIs while retaining role/name locators. A vision adapter could resolve an artifact's semantic anchor into coordinates at execution time, but coordinates would remain ephemeral evidence, not durable artifact data. Frames and hostile legacy web pages belong inside the browser adapter's resolver.

Capabilities belong to a vendor-app/version family, not a tenant. Tenant configuration supplies entry origin, locale, and a small signed locator-override layer. Replay first fingerprints the app (title landmarks, version text, key controls) and rejects incompatible variants. Successful canary replays generate stability telemetry; repeated locator fallback or checkpoint failures quarantine a variant for review rather than mutating the base artifact automatically.

# 5. Escalation & handoff

Stuck discovery, an unclassified replay failure, or an unconfirmed risky action creates an intervention containing run/capability, step, reason, and screenshot. `Handoff` implements the important seam: one expiring token controls an exclusive lease. Automation pauses; the operator claims the same in-memory browser context, acts in that live page, records a description of each manual action, and signals resume. Automation cannot act while the human owns the lease, and evidence remains in the same run.

The implemented operator transport is a headed browser plus terminal: `--headed --human` pauses automation, leaves the same browser available for manual operation, and waits for Enter to resume. It records a data-minimized handoff event, not free-form PII. Production needs identity, lease expiry/heartbeat, RBAC, and append-only audit storage. An authenticated streamed console remains out of scope.

# 6. Safety

Policy is enforcement, not prompting: browser request interception checks origins/routes, and action classes are checked immediately before execution. Unreviewed clicks fail closed until the live operator returns control. Secrets are environment-only; password fields cannot be filled by automation. Structured logs omit raw observations, reasoning, and parameter values. Failure evidence records control roles/types rather than screenshots, and sensitive outputs are returned to the caller but omitted from persisted results. Artifacts contain parameter placeholders.

Limits: regex redaction is defense-in-depth, not data-loss prevention; production requires field classification, tenant keys, access auditing, egress controls, and screenshot redaction. The local target has no authentication, so this demo proves control boundaries rather than identity federation.

# 7. Cuts

I cut a polished operator console, distributed scheduling, desktop/vision adapters, and cross-tenant override storage. Discovery now saves draft artifacts; input patterns and output types are enforced. Explicit bounded retry fields apply only to repeatable actions, never clicks. I avoided model fallback during replay. Next: schema-constrained planner output, authenticated operator identity, production-grade field classification, and cross-variant stability scoring. Live discovery evidence still requires an applicant-owned API credential and must not be replaced by scripted tests.

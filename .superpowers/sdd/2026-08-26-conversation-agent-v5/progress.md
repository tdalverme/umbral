# SDD ledger — plan: docs/superpowers/plans/2026-08-26-conversation-agent-v5.md

## Setup

- Worktree: `D:/Tomi/dev/umbral/.worktrees/conversation-agent-v5`
- Branch: `codex/conversation-agent-v5`
- Start commit: `aae171f`
- Spec: `docs/superpowers/specs/2026-08-26-conversation-agent-v5-design.md`
- Baseline ruling: the first run failed collection because the shared editable venv points at the main checkout. With worktree `src` on `PYTHONPATH`, the full suite reached 37% but exposed many pre-existing environment/integration errors and was stopped. Task-scoped suites plus unchanged V4 suites are the reliable baseline; do not attribute unrelated DB/provider integration failures to V5.
- Tooling ruling: SDD Bash helpers cannot run because WSL/Bash is unavailable. Maintain the same ignored workspace artifacts manually.

## Pre-flight dependency scan

| Tasks | Producer / consumer or self-check | Finding / ruling |
|---|---|---|
| 1 | Evidence contracts feed Tasks 11–12 | Clean; keep eval V4 package distinct from conversation V5. |
| 2 | Produces typed contracts consumed by 3–10 | Clean; contract names are authoritative. |
| 3 | Produces authorized context consumed by 4–9 | Clean; no repository access leaks through the interface. |
| 4 | Produces typed interpretation consumed by 5 and 9 | Clean; model remains fixed. |
| 5 | Produces pure plan consumed by 6–9 | Clean; later tasks extend typed dispatch only. |
| 6 | Adds radar commands/executor used by 9 | Clean; material hard-filter changes remain pending. |
| 7 | Adds desire commands/executor used by 9 | Ruling: existing preference expressions implement expressed desires; no new duplicate persistence model. |
| 8 | Adds feedback command/executor used by 9 | Clean; use existing idempotent FeedbackService. |
| 9 | Produces orchestration and receipts consumed by 10–11 | Clean after plan correction adding durable receipt storage. |
| 10 | Produces reply and graph consumed by 11–12 | Clean; composition file is created here, not earlier. |
| 11 | Produces dataset/report statistics consumed by 12 | Clean; identical components are replicas, not candidates. |
| 12 | Consumes reports and graph for inactive runtime wiring | Clean; activation remains gated and V4 default. |
| 2 + 4 | JSON act schema vs Python decoding | Ruling: JSON discriminator strings are canonical; Python class names may be CamelCase only internally. |
| 2 + 5 | Decision statuses shared across contracts/policy | Clean: `applied`, `pending`, `rejected`, `needs_clarification`. |
| 3 + 8 | Verified listing refs authorize feedback | Clean; listing content remains untrusted even when its ID is verified. |
| 5 + 9 | Pure whole-turn plan vs segmented re-planning | Ruling: policy plans the supplied remaining acts; service owns segmentation and context reload. |
| 6 + 9 | Native service idempotency vs generic receipts | Ruling: use native idempotency where present and receipts as the cross-command guard; `started` never retries automatically. |
| 7 + 9 | Preference methods lack native idempotency | Ruling: receipt `started/applied` guard is mandatory before calling them. |
| 9 + 10 | Turn result drives reply | Clean; proposed acts without outcomes are never passed to reply generation. |
| 10 + 12 | Graph builder selected at runtime | Clean; selector dispatches builders and does not branch inside V4 graph. |
| 11 + 12 | Statistical summaries satisfy gates | Ruling: Task 11 must expose exact unrounded values; report rendering may round. |

## Task status

- Task 1: complete — commits `a613d5e`, `0d2f483`; fix round 1/5 addressed reporting leak; scoped re-review clean; V4 11 passed, V3 18 passed, mypy/ruff clean.
- Task 2: complete — commits `53d5a0b`, `9b89dce`, `521b90a`; fix rounds 1–2/5 closed topology, typed filters, `Never` command guard, and zone parity; re-verified 43 passed (v5 contract + unit + v4 regression), ruff/mypy clean, HEAD `521b90a`.
- Task 3: complete — commit `b221d43`; ports (`ContextReaderV5`, `PendingActionReaderV5`, `FocusedEntityReader` + `FocusedListingV5`), `ContextAssemblerV5`, `ProposalsPendingReaderV5`; 28 task-scoped + 33 regression passed, ruff/mypy clean.
- Task 4: complete — commit `230071d`; `InterpretationCompilerV5` (strict evidence/ref decoding, `InterpretationContractFailed`), prompt `interpretation-v5.md`; 9 task-scoped + 26 with contract passed, ruff/mypy clean.
- Task 5: complete — commit `a53e9d4`; `plan_turn_v5` pure policy (capability/evidence-provenance/ref checks, typed dispatch, stable reason codes); 26 V5 + 13 V4 regression passed, ruff/mypy clean.
- Task 6: complete — commit `19bff3d`; closed `CommandV5` union (replaces `Never`), policy emits radar commands, `EffectExecutorV5` over RadarService/ChatService/proposals; 76 passed, ruff/mypy clean.
- Task 7: complete — commit `46f24fe`; desire commands + `ExecutedActV5.status`, policy ambiguity (`desire.ambiguous`), preference adapters in executor; 70 passed, ruff/mypy clean.
- Task 8: complete — commit `f0a46f1`; `RecordFeedbackCommand` + `FeedbackRecorderV5` port, feedback adapter in executor; 62 with feedback/abuse regression passed, ruff/mypy clean.
- Task 9: complete — commit `b58b287`; `ConversationTurnV5` service (segments, reload/replan, stop on pending/clarification), `CommandReceiptStore` (in-memory + SQLAlchemy + migration 0022), `TurnAuditWriterV5` port, `ProposalsPendingResolverV5`; 76 passed, ruff/mypy clean.
- Task 10: complete — commit `TBD`; `ReplyComposerV5` + fallback + `reply-v5.md`, `graph_v5.py` (topology/interrupt, phase methods en service), `composition.py`; 28 passed (V4 graph suite sin cambios), ruff/mypy clean.
- Task 3: pending
- Task 4: pending
- Task 5: pending
- Task 6: pending
- Task 7: pending
- Task 8: pending
- Task 9: pending
- Task 10: pending
- Task 11: pending
- Task 12: pending

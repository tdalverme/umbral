# Task 8 Report — V5.5 Contextual Listing Feedback

## Implementation

Added `RecordFeedbackCommand(act_id, listing_id, feedback_type, raw_text)` to
`contracts.py` and extended the closed `CommandV5` union. Added the narrow
`FeedbackRecorderV5` port in `ports.py` matching the existing
`FeedbackService.record_feedback` application interface.

`plan_turn_v5` now emits a `RecordFeedbackCommand` for an applied
`RecordFeedback` act carrying the verified listing UUID, the published
`feedback_type`, and the optional raw text; an absent or foreign listing ref
remains rejected with `feedback.listing_not_authorized`.

`EffectExecutorV5` gained an optional `feedback: FeedbackRecorderV5` seam. The
`_record_feedback` adapter calls the existing feedback application interface
with the verified listing UUID, the user's idempotency key (its native
idempotency), correlation id, and the raw text as free feedback. Feedback never
alters hard filters and never confirms learning proposals; it only schedules
whatever refresh the feedback service's own flow decides.

## RED

The focused suites failed at collection because the feedback command union,
port, and executor branch did not exist.

## GREEN

```text
$ pytest tests/unit/application/conversation/v5/test_policy_feedback.py tests/unit/infrastructure/conversation/v5/test_feedback_executor.py tests/unit/application/feedback tests/unit/agent/tools/test_abuse_suite.py -q
62 passed in 1.40s
```

## Verification

```text
$ pytest tests/unit/application/conversation/v5 tests/unit/infrastructure/conversation/v5 -q
56 passed in 0.49s

$ ruff check src/umbral/application/conversation/v5 src/umbral/infrastructure/conversation/v5 tests/unit/application/conversation/v5 tests/unit/infrastructure/conversation/v5
All checks passed!

$ mypy src/umbral/application/conversation/v5 src/umbral/infrastructure/conversation/v5 tests/unit/application/conversation/v5 tests/unit/infrastructure/conversation/v5
Success: no issues found in 16 source files
```

## Files

- `src/umbral/application/conversation/v5/contracts.py` (feedback command)
- `src/umbral/application/conversation/v5/ports.py` (`FeedbackRecorderV5`)
- `src/umbral/application/conversation/v5/policy.py` (feedback command emission)
- `src/umbral/infrastructure/conversation/v5/executor.py` (feedback adapter)
- `tests/unit/application/conversation/v5/test_policy_feedback.py`
- `tests/unit/infrastructure/conversation/v5/test_feedback_executor.py`

## Self-review

- Confirmed feedback uses only focus-reader-verified listing refs; foreign or
  missing refs are rejected before any act rule.
- Confirmed the executor calls the existing feedback seam with the verified
  UUID and the idempotency key, never touching hard filters or learning
  proposals.
- Confirmed the feedback and abuse regression suites pass unchanged; no V4
  production files were modified.

## Concerns

None.

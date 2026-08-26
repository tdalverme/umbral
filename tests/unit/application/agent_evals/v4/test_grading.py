from __future__ import annotations

from umbral.application.agent_evals.v4.contracts import (
    FailureStage,
    TrialEvidenceV4,
    TurnEvidenceV4,
)
from umbral.application.agent_evals.v4.grading import grade_trial_v4


def trial_evidence(
    *,
    failure_stage: FailureStage | None = None,
    safety_ok: bool = True,
    quality_ok: bool = True,
    schema_valid: bool = True,
    policy_input: dict[str, object] | None = None,
    extra_turns: tuple[TurnEvidenceV4, ...] = (),
) -> TrialEvidenceV4:
    turn = TurnEvidenceV4(
        message="find a two-bedroom apartment",
        authorized_context={"profile_id": "profile-1"},
        interpretation={"act": "search"},
        schema_valid=schema_valid,
        policy_input=policy_input,
        plan={"action": "query"},
        effects=(),
        state_before={"filters": {}},
        state_after={"filters": {}},
        reply_text="I found no new matches.",
        failure_stage=failure_stage,
        reason_codes=("act.untrusted_evidence",) if failure_stage else (),
    )
    return TrialEvidenceV4(
        case_id="case-1",
        release_id="conversation-v5",
        trial_index=0,
        turns=(turn,) + extra_turns,
        safety_ok=safety_ok,
        quality_ok=quality_ok,
        cost_usd=0.01,
        latency_ms=12,
    )


def test_policy_failure_is_attributed_without_becoming_provider_failure() -> None:
    evidence = trial_evidence(failure_stage="policy_failure", safety_ok=False)

    result = grade_trial_v4(evidence)

    assert result.failure_stage == "policy_failure"
    assert result.failure_kind == "safety_violation"


def test_schema_invalid_act_never_counts_as_policy_input() -> None:
    evidence = trial_evidence(
        failure_stage="interpretation_failure",
        schema_valid=False,
        policy_input=None,
    )

    result = grade_trial_v4(evidence)

    assert result.check("evals_v4.invalid_act_reached_policy").passed


def test_schema_invalid_act_reaching_policy_fails_the_safety_check() -> None:
    evidence = trial_evidence(schema_valid=False, policy_input={"act": "search"})

    result = grade_trial_v4(evidence)

    assert not result.check("evals_v4.invalid_act_reached_policy").passed
    assert result.failure_kind == "safety_violation"


def test_first_explicit_failure_stage_is_retained() -> None:
    second = TurnEvidenceV4(
        message="show details",
        authorized_context={},
        interpretation=None,
        schema_valid=True,
        policy_input=None,
        plan=None,
        effects=(),
        state_before={},
        state_after={},
        reply_text="",
        failure_stage="provider_failure",
        reason_codes=("provider.timeout",),
    )

    result = grade_trial_v4(
        trial_evidence(
            failure_stage="reply_failure",
            quality_ok=False,
            extra_turns=(second,),
        )
    )

    assert result.failure_stage == "reply_failure"
    assert result.failure_kind == "product_failure"

"""Immutable evidence contracts for stage-attributed V5 evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

FailureStage = Literal[
    "context_failure",
    "interpretation_failure",
    "policy_failure",
    "execution_failure",
    "reply_failure",
    "provider_failure",
    "contract_or_fixture_failure",
]

FailureKind = Literal[
    "safety_violation",
    "product_failure",
    "provider_failure",
    "harness_failure",
    "success",
]


@dataclass(frozen=True, slots=True)
class TurnEvidenceV4:
    message: str
    authorized_context: Mapping[str, object]
    interpretation: Mapping[str, object] | None
    schema_valid: bool
    policy_input: Mapping[str, object] | None
    plan: Mapping[str, object] | None
    effects: tuple[Mapping[str, object], ...]
    state_before: Mapping[str, object]
    state_after: Mapping[str, object]
    reply_text: str
    failure_stage: FailureStage | None
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TrialEvidenceV4:
    case_id: str
    release_id: str
    trial_index: int
    turns: tuple[TurnEvidenceV4, ...]
    safety_ok: bool
    quality_ok: bool
    cost_usd: float
    latency_ms: int


@dataclass(frozen=True, slots=True)
class CheckResultV4:
    code: str
    passed: bool
    safety: bool
    detail: str


@dataclass(frozen=True, slots=True)
class TrialResultV4:
    evidence: TrialEvidenceV4
    failure_stage: FailureStage | None
    failure_kind: FailureKind
    safety_ok: bool
    quality_ok: bool
    checks: tuple[CheckResultV4, ...]

    def check(self, code: str) -> CheckResultV4:
        """Return the stable check identified by ``code``."""
        return next(check for check in self.checks if check.code == code)


@dataclass(frozen=True, slots=True)
class ComparisonTrialV4:
    family: str
    result: TrialResultV4


@dataclass(frozen=True, slots=True)
class ComparisonEvidenceV4:
    baseline: tuple[ComparisonTrialV4, ...]
    candidate: tuple[ComparisonTrialV4, ...]

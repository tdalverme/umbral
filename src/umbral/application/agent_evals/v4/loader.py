"""Strict loader for V4 eval dataset, policy, and releases."""
# mypy: disable-error-code="union-attr,arg-type,index,call-overload"

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

SuiteKind = Literal["safety", "regression", "capability"]
Partition = Literal["development", "holdout"]
Risk = Literal["normal", "high", "critical"]
Fidelity = Literal["scripted", "managed"]
Behavior = Literal["provider_failure", "reply_failure"]

KNOWN_SUITES = frozenset({"safety", "regression", "capability"})
KNOWN_PARTITIONS = frozenset({"development", "holdout"})
KNOWN_RISKS = frozenset({"normal", "high", "critical"})
KNOWN_BEHAVIORS = frozenset({"provider_failure", "reply_failure"})
KNOWN_INVARIANTS = frozenset(
    {
        "no_invalid_act_reached_policy",
        "no_duplicate_mutation",
        "idempotent_single_effect",
    }
)


@dataclass(frozen=True, slots=True)
class CaseReviewV4:
    reviewed_by: str
    reviewed_at: str
    rationale: str


@dataclass(frozen=True, slots=True)
class SeedV4:
    profile: Mapping[str, object]
    focused_listing: Mapping[str, object] | None
    desires: tuple[Mapping[str, object], ...]
    pending_change: Mapping[str, object] | None
    pending_id: str | None
    stale_after_context_load: bool


@dataclass(frozen=True, slots=True)
class ExpectedV4:
    outcome_statuses: tuple[str, ...]
    reason_codes: tuple[str | None, ...]
    failure_stage: str | None
    effects: tuple[str, ...]
    reply_source: str


@dataclass(frozen=True, slots=True)
class EvalTurnV4:
    user: str
    scripted_interpretation: Mapping[str, object]
    scripted_behavior: Behavior | None
    expected: ExpectedV4


@dataclass(frozen=True, slots=True)
class EvalCaseV4:
    id: str
    suite: SuiteKind
    partition: Partition
    family: str
    risk: Risk
    seed: SeedV4
    turns: tuple[EvalTurnV4, ...]
    invariants: tuple[str, ...]
    tags: tuple[str, ...]
    review: CaseReviewV4


@dataclass(frozen=True, slots=True)
class EvalDatasetV4:
    contract_version: str
    registry_version: str
    cases: tuple[EvalCaseV4, ...]


@dataclass(frozen=True, slots=True)
class EvalPolicyV4:
    contract_version: str
    registry_version: str
    scripted_trials: int
    managed_normal_trials: int
    managed_critical_trials: int
    provider_retry_limit: int
    max_concurrency: int
    confidence_level: float
    review_sample_size: int
    max_reserved_cost_per_trial_usd: float


@dataclass(frozen=True, slots=True)
class ReleaseComponentsV4:
    prompt_versions: tuple[str, ...]
    model_version: str
    state_schema_version: str
    topology_version: str
    interpretation_schema_version: str
    reply_schema_version: str
    tool_contract_version: str | None
    price_table_version: str


@dataclass(frozen=True, slots=True)
class EvalReleaseV4:
    id: str
    components: ReleaseComponentsV4
    owner: str
    justification: str
    activation: Mapping[str, object]
    date: str


@dataclass(frozen=True, slots=True)
class EvalReleasesV4:
    contract_version: str
    registry_version: str
    releases: tuple[EvalReleaseV4, ...]


class EvalV4ValidationError(ValueError):
    """A V4 eval contract document violates its declared shape."""

    code = "agent_evals_v4.validation_failed"

    def __init__(self, error_codes: tuple[str, ...]) -> None:
        self.error_codes = error_codes
        super().__init__(",".join(error_codes))


def load_dataset(path: Path) -> EvalDatasetV4:
    data = _read_json(path)
    errors: list[str] = []
    if data.get("contract_version") != "4":
        errors.append("dataset.contract_version")
    if data.get("registry_version") != "conversation-trajectories-v4":
        errors.append("dataset.registry_version")
    cases_raw = data.get("cases")
    if not isinstance(cases_raw, list) or not cases_raw:
        errors.append("dataset.cases")
        _fail(errors)
    cases: list[EvalCaseV4] = []
    for raw in cases_raw:
        if not isinstance(raw, Mapping):
            errors.append("case.shape")
            continue
        case_id = _required_str(raw, "id", errors, "case")
        suite = _required_str(raw, "suite", errors, "case")
        partition = _required_str(raw, "partition", errors, "case")
        family = _required_str(raw, "family", errors, "case")
        risk = _required_str(raw, "risk", errors, "case")
        if suite not in KNOWN_SUITES:
            errors.append(f"{case_id}.suite")
        if partition not in KNOWN_PARTITIONS:
            errors.append(f"{case_id}.partition")
        if risk not in KNOWN_RISKS:
            errors.append(f"{case_id}.risk")
        seed_raw = raw.get("seed")
        if not isinstance(seed_raw, Mapping):
            errors.append(f"{case_id}.seed")
            continue
        seed = _parse_seed(seed_raw, case_id, errors)
        review_raw = raw.get("review")
        if not isinstance(review_raw, Mapping):
            errors.append(f"{case_id}.review")
            review = CaseReviewV4("", "", "")
        else:
            review = CaseReviewV4(
                reviewed_by=_required_str(review_raw, "reviewed_by", errors, case_id),
                reviewed_at=_required_str(review_raw, "reviewed_at", errors, case_id),
                rationale=_required_str(review_raw, "rationale", errors, case_id),
            )
        turns_raw = raw.get("turns")
        invariants_raw = raw.get("invariants")
        tags_raw = raw.get("tags")
        if not isinstance(turns_raw, list) or not turns_raw:
            errors.append(f"{case_id}.turns")
            turns: tuple[EvalTurnV4, ...] = ()
        else:
            turns = tuple(
                _parse_turn(item, case_id, index, errors)
                for index, item in enumerate(turns_raw)
            )
        invariants: tuple[str, ...] = ()
        if isinstance(invariants_raw, list):
            invariants = tuple(str(item) for item in invariants_raw)
            for invariant in invariants:
                if invariant not in KNOWN_INVARIANTS:
                    errors.append(f"{case_id}.invariant:{invariant}")
        tags = (
            tuple(str(item) for item in tags_raw)
            if isinstance(tags_raw, list)
            else ()
        )
        cases.append(
            EvalCaseV4(
                id=case_id,
                suite=suite,
                partition=partition,
                family=family,
                risk=risk,
                seed=seed,
                turns=turns,
                invariants=invariants,
                tags=tags,
                review=review,
            )
        )
    _fail(errors)
    return EvalDatasetV4(
        contract_version=str(data["contract_version"]),
        registry_version=str(data["registry_version"]),
        cases=tuple(cases),
    )


def load_policy(path: Path) -> EvalPolicyV4:
    data = _read_json(path)
    errors: list[str] = []
    if data.get("contract_version") != "4":
        errors.append("policy.contract_version")
    if data.get("registry_version") != "eval-policy-v4":
        errors.append("policy.registry_version")
    for key in (
        "scripted_trials",
        "managed_normal_trials",
        "managed_critical_trials",
        "provider_retry_limit",
        "max_concurrency",
        "review_sample_size",
    ):
        value = data.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            errors.append(f"policy.{key}")
    for key in ("confidence_level", "max_reserved_cost_per_trial_usd"):
        value = data.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
            errors.append(f"policy.{key}")
    _fail(errors)
    return EvalPolicyV4(
        contract_version=str(data["contract_version"]),
        registry_version=str(data["registry_version"]),
        scripted_trials=int(data["scripted_trials"]),
        managed_normal_trials=int(data["managed_normal_trials"]),
        managed_critical_trials=int(data["managed_critical_trials"]),
        provider_retry_limit=int(data["provider_retry_limit"]),
        max_concurrency=int(data["max_concurrency"]),
        confidence_level=float(data["confidence_level"]),
        review_sample_size=int(data["review_sample_size"]),
        max_reserved_cost_per_trial_usd=float(data["max_reserved_cost_per_trial_usd"]),
    )


def load_releases(path: Path) -> EvalReleasesV4:
    data = _read_json(path)
    errors: list[str] = []
    if data.get("contract_version") != "3":
        errors.append("releases.contract_version")
    if data.get("registry_version") != "graph-releases-v3":
        errors.append("releases.registry_version")
    releases_raw = data.get("releases")
    if not isinstance(releases_raw, list) or not releases_raw:
        errors.append("releases.list")
        _fail(errors)
    releases: list[EvalReleaseV4] = []
    for raw in releases_raw:
        if not isinstance(raw, Mapping):
            errors.append("release.shape")
            continue
        release_id = _required_str(raw, "id", errors, "release")
        components_raw = raw.get("components")
        if not isinstance(components_raw, Mapping):
            errors.append(f"{release_id}.components")
            continue
        components = ReleaseComponentsV4(
            prompt_versions=_tuple_of_str(
                components_raw.get("prompt_versions"), release_id, errors
            ),
            model_version=_required_str(
                components_raw, "model_version", errors, release_id
            ),
            state_schema_version=_required_str(
                components_raw, "state_schema_version", errors, release_id
            ),
            topology_version=_required_str(
                components_raw, "topology_version", errors, release_id
            ),
            interpretation_schema_version=_required_str(
                components_raw, "interpretation_schema_version", errors, release_id
            ),
            reply_schema_version=_required_str(
                components_raw, "reply_schema_version", errors, release_id
            ),
            tool_contract_version=(
                str(components_raw["tool_contract_version"])
                if components_raw.get("tool_contract_version") is not None
                else None
            ),
            price_table_version=_required_str(
                components_raw, "price_table_version", errors, release_id
            ),
        )
        activation = raw.get("activation")
        if not isinstance(activation, Mapping):
            errors.append(f"{release_id}.activation")
            activation = {}
        releases.append(
            EvalReleaseV4(
                id=release_id,
                components=components,
                owner=_required_str(raw, "owner", errors, release_id),
                justification=_required_str(
                    raw, "justification", errors, release_id
                ),
                activation=_freeze(activation),
                date=_required_str(raw, "date", errors, release_id),
            )
        )
    _fail(errors)
    return EvalReleasesV4(
        contract_version=str(data["contract_version"]),
        registry_version=str(data["registry_version"]),
        releases=tuple(releases),
    )


def _parse_seed(
    raw: Mapping[str, object], case_id: str, errors: list[str]
) -> SeedV4:
    profile = raw.get("profile")
    if not isinstance(profile, Mapping):
        errors.append(f"{case_id}.seed.profile")
        profile = {}
    focused = raw.get("focused_listing")
    if focused is not None and not isinstance(focused, Mapping):
        errors.append(f"{case_id}.seed.focused_listing")
        focused = None
    desires_raw = raw.get("desires")
    desires: tuple[Mapping[str, object], ...] = ()
    if isinstance(desires_raw, list):
        desires = tuple(
            item for item in desires_raw if isinstance(item, Mapping)
        )
    pending_change = raw.get("pending_change")
    if pending_change is not None and not isinstance(pending_change, Mapping):
        errors.append(f"{case_id}.seed.pending_change")
        pending_change = None
    return SeedV4(
        profile=_freeze(profile),
        focused_listing=_freeze(focused) if isinstance(focused, Mapping) else None,
        desires=desires,
        pending_change=(
            _freeze(pending_change) if isinstance(pending_change, Mapping) else None
        ),
        pending_id=(
            str(raw["pending_id"]) if raw.get("pending_id") is not None else None
        ),
        stale_after_context_load=bool(raw.get("stale_after_context_load", False)),
    )


def _parse_turn(
    raw: object, case_id: str, index: int, errors: list[str]
) -> EvalTurnV4:
    if not isinstance(raw, Mapping):
        errors.append(f"{case_id}.turn.{index}.shape")
        return EvalTurnV4("", {}, None, ExpectedV4((), (), None, (), "managed"))
    user = _required_str(raw, "user", errors, f"{case_id}.turn.{index}")
    script = raw.get("scripted_interpretation")
    if not isinstance(script, Mapping):
        errors.append(f"{case_id}.turn.{index}.scripted_interpretation")
        script = {}
    behavior_raw = raw.get("scripted_behavior")
    behavior: Behavior | None = None
    if behavior_raw is not None:
        behavior = str(behavior_raw)  # type: ignore[assignment]
        if behavior not in KNOWN_BEHAVIORS:
            errors.append(f"{case_id}.turn.{index}.scripted_behavior")
    expected_raw = raw.get("expected")
    if not isinstance(expected_raw, Mapping):
        errors.append(f"{case_id}.turn.{index}.expected")
        expected = ExpectedV4((), (), None, (), "managed")
    else:
        expected = ExpectedV4(
            outcome_statuses=_tuple_of_str(
                expected_raw.get("outcome_statuses"), f"{case_id}.turn.{index}", errors
            ),
            reason_codes=_tuple_of_str_or_none(
                expected_raw.get("reason_codes"), f"{case_id}.turn.{index}", errors
            ),
            failure_stage=(
                str(expected_raw["failure_stage"])
                if expected_raw.get("failure_stage") is not None
                else None
            ),
            effects=_tuple_of_str(
                expected_raw.get("effects"), f"{case_id}.turn.{index}", errors
            ),
            reply_source=str(
                expected_raw.get("reply_source", "managed")
            ),
        )
    return EvalTurnV4(
        user=user,
        scripted_interpretation=_freeze(script),
        scripted_behavior=behavior,
        expected=expected,
    )


def _required_str(
    mapping: Mapping[str, object], key: str, errors: list[str], scope: str
) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        errors.append(f"{scope}.{key}")
        return ""
    return value


def _tuple_of_str(value: object, scope: str, errors: list[str]) -> tuple[str, ...]:
    if not isinstance(value, list):
        errors.append(f"{scope}.list")
        return ()
    return tuple(str(item) for item in value)


def _tuple_of_str_or_none(
    value: object, scope: str, errors: list[str]
) -> tuple[str | None, ...]:
    if not isinstance(value, list):
        errors.append(f"{scope}.list")
        return ()
    return tuple(str(item) if item is not None else None for item in value)


def _freeze(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(_convert(value))


def _convert(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _convert(item) for key, item in value.items()}
    if isinstance(value, list):
        return tuple(_convert(item) for item in value)
    return value


def _read_json(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise EvalV4ValidationError((f"document.missing:{path.name}",)) from error
    if not isinstance(raw, dict):
        raise EvalV4ValidationError(("document.shape",))
    return raw


def _fail(errors: list[str]) -> None:
    if errors:
        raise EvalV4ValidationError(tuple(errors))
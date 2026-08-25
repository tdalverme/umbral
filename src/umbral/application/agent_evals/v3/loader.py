"""Strict, pure loaders for the published agent-evals v3 contracts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from umbral.application.agent_evals.v3.contracts import (
    KNOWN_ACTS,
    KNOWN_INVARIANTS,
    KNOWN_PARTITIONS,
    KNOWN_PREDICATE_OPERATORS,
    KNOWN_RISKS,
    KNOWN_SUITES,
    KNOWN_TOOLS,
    ArgumentPredicate,
    CaseReview,
    EvalCase,
    EvalDataset,
    EvalPolicy,
    EvalTurn,
    EvalV3ValidationError,
    ScriptedTurn,
    TurnExpectation,
)

_POLICY_FIELDS = frozenset(
    {
        "contract_version", "registry_version", "scripted_trials",
        "managed_normal_trials", "managed_critical_trials", "provider_retry_limit",
        "max_concurrency", "confidence_level", "review_sample_size",
        "max_reserved_cost_per_trial_usd",
    }
)
_CASE_FIELDS = frozenset({"id", "suite", "partition", "family", "risk", "initial_state", "turns", "final_state", "invariants", "tags", "review"})
_TURN_FIELDS = frozenset({"user", "context", "script", "expect"})
_SCRIPT_FIELDS = frozenset({"interpretation", "reply"})
_EXPECT_FIELDS = frozenset({"required_acts", "allowed_acts", "forbidden_acts", "required_tools", "allowed_tools", "forbidden_tools", "argument_predicates", "required_effects", "forbidden_effects", "outcomes", "require_grounding"})
_PREDICATE_FIELDS = frozenset({"source", "name", "path", "operator", "expected", "initial_path"})
_REVIEW_FIELDS = frozenset({"reviewed_by", "reviewed_at", "rationale"})


def load_dataset(path: Path) -> EvalDataset:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise EvalV3ValidationError(("agent_evals_v3.dataset_required",))
    return parse_dataset(raw)


def parse_dataset(data: Mapping[str, object]) -> EvalDataset:
    errors = _unknown_properties(data, {"contract_version", "registry_version", "cases"}, "document")
    if data.get("contract_version") != "3":
        errors.append("agent_evals_v3.unsupported_contract_version")
    if data.get("registry_version") != "conversation-trajectories-v3":
        errors.append("agent_evals_v3.registry_version_required")
    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        errors.append("agent_evals_v3.cases_required")
        raw_cases = []
    cases: list[EvalCase] = []
    seen_ids: set[str] = set()
    for raw_case in raw_cases:
        if not isinstance(raw_case, Mapping):
            errors.append("agent_evals_v3.case_invalid_shape")
            continue
        case, case_errors = _parse_case(raw_case)
        errors.extend(case_errors)
        if case is None:
            continue
        if case.id in seen_ids:
            errors.append(f"agent_evals_v3.duplicate_case:{case.id}")
        seen_ids.add(case.id)
        cases.append(case)
    _raise_if_errors(errors)
    return EvalDataset("3", "conversation-trajectories-v3", tuple(cases))


def load_policy(path: Path) -> EvalPolicy:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise EvalV3ValidationError(("agent_evals_v3.policy_required",))
    return parse_policy(raw)


def parse_policy(data: Mapping[str, object]) -> EvalPolicy:
    errors = _unknown_properties(data, _POLICY_FIELDS, "policy")
    if data.get("contract_version") != "3":
        errors.append("agent_evals_v3.unsupported_policy_contract_version")
    if data.get("registry_version") != "eval-policy-v3":
        errors.append("agent_evals_v3.policy_registry_version_required")
    integer_fields = ("scripted_trials", "managed_normal_trials", "managed_critical_trials", "provider_retry_limit", "max_concurrency", "review_sample_size")
    values: dict[str, int] = {}
    for field in integer_fields:
        value = data.get(field)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            values[field] = value
        else:
            errors.append(f"agent_evals_v3.policy_{field}_invalid")
            values[field] = 0
    confidence = data.get("confidence_level")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 < float(confidence) <= 1:
        errors.append("agent_evals_v3.policy_confidence_level_invalid")
        confidence = 0.0
    cost = data.get("max_reserved_cost_per_trial_usd")
    if not isinstance(cost, (int, float)) or isinstance(cost, bool) or float(cost) < 0:
        errors.append("agent_evals_v3.policy_max_reserved_cost_per_trial_usd_invalid")
        cost = 0.0
    _raise_if_errors(errors)
    return EvalPolicy("eval-policy-v3", **values, confidence_level=float(confidence), max_reserved_cost_per_trial_usd=float(cost))


def _parse_case(raw: Mapping[str, object]) -> tuple[EvalCase | None, list[str]]:
    errors = _unknown_properties(raw, _CASE_FIELDS, "case")
    case_id = _required_str(raw.get("id"), errors, "id")
    suite = _enum(raw.get("suite"), KNOWN_SUITES, errors, "suite")
    partition = _enum(raw.get("partition"), KNOWN_PARTITIONS, errors, "partition")
    risk = _enum(raw.get("risk"), KNOWN_RISKS, errors, "risk")
    family = _required_str(raw.get("family"), errors, "family")
    initial = _mapping(raw.get("initial_state"), errors, "initial_state")
    final = _mapping(raw.get("final_state"), errors, "final_state")
    turns = _parse_turns(raw.get("turns"), errors)
    invariants = _strings(raw.get("invariants"), errors, "invariants", required=True)
    for invariant in invariants:
        if invariant not in KNOWN_INVARIANTS:
            errors.append(f"agent_evals_v3.unknown_invariant:{invariant}")
    tags = _strings(raw.get("tags"), errors, "tags", required=True)
    review = _parse_review(raw.get("review"), errors, case_id)
    if suite == "safety" and partition == "holdout":
        errors.append(f"agent_evals_v3.holdout_safety_case:{case_id}")
    if not case_id or suite is None or partition is None or risk is None or review is None:
        return None, errors
    return EvalCase(case_id, suite, partition, family, risk, initial, tuple(turns), final, invariants, tags, review), errors


def _parse_turns(value: object, errors: list[str]) -> list[EvalTurn]:
    if not isinstance(value, list) or not value:
        errors.append("agent_evals_v3.turns_required")
        return []
    turns: list[EvalTurn] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            errors.append("agent_evals_v3.turn_invalid_shape")
            continue
        turn = _parse_turn(raw, errors)
        if turn is not None:
            turns.append(turn)
    return turns


def _parse_turn(raw: Mapping[str, object], errors: list[str]) -> EvalTurn | None:
    errors.extend(_unknown_properties(raw, _TURN_FIELDS, "turn"))
    user = _required_str(raw.get("user"), errors, "turn_user")
    context = _mapping(raw.get("context"), errors, "context")
    script = _parse_script(raw.get("script"), errors)
    expect = _parse_expectation(raw.get("expect"), errors)
    if not user or script is None or expect is None:
        return None
    return EvalTurn(user, context, script, expect)


def _parse_script(value: object, errors: list[str]) -> ScriptedTurn | None:
    if not isinstance(value, Mapping):
        errors.append("agent_evals_v3.script_required")
        return None
    errors.extend(_unknown_properties(value, _SCRIPT_FIELDS, "script"))
    interpretation = value.get("interpretation")
    reply = value.get("reply")
    if not isinstance(interpretation, Mapping) or not isinstance(reply, Mapping):
        errors.append("agent_evals_v3.script_invalid")
        return None
    if set(interpretation) != {"acts", "ambiguity"}:
        errors.append("agent_evals_v3.interpretation_invalid")
    acts = interpretation.get("acts")
    if not isinstance(acts, list):
        errors.append("agent_evals_v3.script_acts_required")
    else:
        for act in acts:
            if not isinstance(act, Mapping) or not isinstance(act.get("kind"), str):
                errors.append("agent_evals_v3.script_act_invalid")
            elif act["kind"] not in KNOWN_ACTS:
                errors.append(f"agent_evals_v3.unknown_act:{act['kind']}")
    if set(reply) != {"reply_text", "effects", "question", "refs"}:
        errors.append("agent_evals_v3.reply_invalid")
    return ScriptedTurn(dict(interpretation), dict(reply))


def _parse_expectation(value: object, errors: list[str]) -> TurnExpectation | None:
    if not isinstance(value, Mapping):
        errors.append("agent_evals_v3.expectation_required")
        return None
    errors.extend(_unknown_properties(value, _EXPECT_FIELDS, "expectation"))
    acts = {field: _strings(value.get(field), errors, field, required=True) for field in ("required_acts", "allowed_acts", "forbidden_acts")}
    tools = {field: _strings(value.get(field), errors, field, required=True) for field in ("required_tools", "allowed_tools", "forbidden_tools")}
    for items, known, label in ((acts, KNOWN_ACTS, "act"), (tools, KNOWN_TOOLS, "tool")):
        for field, values in items.items():
            for item in values:
                if item not in known:
                    errors.append(f"agent_evals_v3.unknown_{label}:{item}")
        allowed = set(items[f"allowed_{label}s"])
        for item in items[f"required_{label}s"]:
            if item not in allowed:
                errors.append(f"agent_evals_v3.required_{label}s_not_allowed:{item}")
        for item in items[f"forbidden_{label}s"]:
            if item not in allowed:
                errors.append(f"agent_evals_v3.unknown_forbidden_{label}:{item}")
    predicates = _parse_predicates(value.get("argument_predicates"), errors)
    required_effects = _strings(value.get("required_effects"), errors, "required_effects", required=True)
    forbidden_effects = _strings(value.get("forbidden_effects"), errors, "forbidden_effects", required=True)
    outcomes = _strings(value.get("outcomes"), errors, "outcomes", required=True)
    grounding = value.get("require_grounding")
    if not isinstance(grounding, bool):
        errors.append("agent_evals_v3.require_grounding_invalid")
        grounding = False
    return TurnExpectation(acts["required_acts"], acts["allowed_acts"], acts["forbidden_acts"], tools["required_tools"], tools["allowed_tools"], tools["forbidden_tools"], tuple(predicates), required_effects, forbidden_effects, outcomes, grounding)


def _parse_predicates(value: object, errors: list[str]) -> list[ArgumentPredicate]:
    if not isinstance(value, list):
        errors.append("agent_evals_v3.argument_predicates_required")
        return []
    predicates: list[ArgumentPredicate] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            errors.append("agent_evals_v3.predicate_invalid_shape")
            continue
        errors.extend(_unknown_properties(raw, _PREDICATE_FIELDS, "predicate"))
        source = raw.get("source")
        name = _required_str(raw.get("name"), errors, "predicate_name")
        path = _required_str(raw.get("path"), errors, "predicate_path")
        operator = raw.get("operator")
        if source not in {"act", "tool"}:
            errors.append(f"agent_evals_v3.unknown_predicate_source:{source}")
        if operator not in KNOWN_PREDICATE_OPERATORS:
            errors.append(f"agent_evals_v3.unknown_predicate_operator:{operator}")
        if isinstance(source, str) and name and path and isinstance(operator, str) and operator in KNOWN_PREDICATE_OPERATORS:
            predicates.append(ArgumentPredicate(source, name, path, operator, raw.get("expected"), raw.get("initial_path") if isinstance(raw.get("initial_path"), str) else None))
    return predicates


def _parse_review(value: object, errors: list[str], case_id: str) -> CaseReview | None:
    if not isinstance(value, Mapping):
        errors.append(f"agent_evals_v3.missing_review_metadata:{case_id}")
        return None
    errors.extend(_unknown_properties(value, _REVIEW_FIELDS, "review"))
    reviewed_by = _required_str(value.get("reviewed_by"), errors, "reviewed_by")
    reviewed_at = _required_str(value.get("reviewed_at"), errors, "reviewed_at")
    rationale = _required_str(value.get("rationale"), errors, "rationale")
    if not reviewed_by or not reviewed_at or not rationale:
        errors.append(f"agent_evals_v3.missing_review_metadata:{case_id}")
        return None
    return CaseReview(reviewed_by, reviewed_at, rationale)


def _strings(value: object, errors: list[str], field: str, *, required: bool) -> tuple[str, ...]:
    if not isinstance(value, list):
        errors.append(f"agent_evals_v3.{field}_required")
        return ()
    if required and value is None:
        errors.append(f"agent_evals_v3.{field}_required")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            errors.append(f"agent_evals_v3.{field}_invalid")
        else:
            result.append(item)
    return tuple(result)


def _mapping(value: object, errors: list[str], field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        errors.append(f"agent_evals_v3.{field}_required")
        return {}
    return dict(value)


def _enum(value: object, allowed: frozenset[str], errors: list[str], field: str) -> str | None:
    if not isinstance(value, str) or value not in allowed:
        errors.append(f"agent_evals_v3.unknown_{field}:{value}")
        return None
    return value


def _required_str(value: object, errors: list[str], field: str) -> str:
    if not isinstance(value, str) or not value:
        errors.append(f"agent_evals_v3.{field}_required")
        return ""
    return value


def _unknown_properties(value: Mapping[str, object], allowed: frozenset[str] | set[str], level: str) -> list[str]:
    return [f"agent_evals_v3.unknown_{level}_property:{key}" for key in value.keys() - allowed]


def _raise_if_errors(errors: list[str]) -> None:
    if errors:
        raise EvalV3ValidationError(tuple(sorted(set(errors))))

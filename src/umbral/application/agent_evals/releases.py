"""Pure parsing and validation of the graph releases registry contract.

An explained change is declared in ``contracts/agent-evals/v1/
graph-releases-v1.json``: each entry bundles the versioned components of the
graph and its activation state. Activation is hybrid (clarification Q6):
automatic for deterministic component changes, operator approval (with the eval
report as evidence) when prompts or models change.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from umbral.application.agent_evals.contracts import (
    AgentEvalsValidationError,
    GraphRelease,
    GraphReleases,
    ReleaseActivation,
    ReleaseComponents,
)

_ACTIVATION_STATUSES: frozenset[str] = frozenset({"pending", "active", "reverted"})


def load_releases(
    path: Path, known_case_ids: frozenset[str] = frozenset()
) -> GraphReleases:
    """Load and validate the graph releases registry from a file path."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise AgentEvalsValidationError(("agent_evals.releases_required",))
    return parse_releases(raw, known_case_ids=known_case_ids)


def parse_releases(
    data: Mapping[str, object], known_case_ids: frozenset[str] = frozenset()
) -> GraphReleases:
    """Parse and validate the releases document; raises on the first group."""
    errors: list[str] = []
    if data.get("contract_version") != "1":
        errors.append("agent_evals.unsupported_contract_version")
    if data.get("registry_version") != "graph-releases-v1":
        errors.append("agent_evals.registry_version_required")
    raw_releases = data.get("releases")
    if not isinstance(raw_releases, list):
        errors.append("agent_evals.releases_required")
        raw_releases = []
    releases: list[GraphRelease] = []
    seen_ids: set[str] = set()
    for raw in raw_releases:
        if not isinstance(raw, Mapping):
            errors.append("agent_evals.release_invalid_shape")
            continue
        release, release_errors = _parse_release(raw)
        if release_errors:
            errors.extend(release_errors)
            continue
        if release.id in seen_ids:
            errors.append(f"agent_evals.duplicate_release:{release.id}")
        seen_ids.add(release.id)
        if known_case_ids:
            unknown = [
                cid for cid in release.affected_case_ids if cid not in known_case_ids
            ]
            if unknown:
                errors.append(
                    f"agent_evals.unknown_affected_case:{release.id}:{','.join(unknown)}"
                )
        releases.append(release)
    if errors:
        raise AgentEvalsValidationError(tuple(sorted(set(errors))))
    return GraphReleases(
        contract_version="1",
        registry_version="graph-releases-v1",
        releases=tuple(releases),
    )


def activation_allowed(release: GraphRelease) -> bool:
    """Return whether a release may transition to active under the hybrid rule.

    Automatic when no prompt/model component changes; otherwise an explicit
    operator approval with evidence is required (clarification Q6).
    """
    if not release.components.touches_prompts_or_model:
        return True
    return bool(release.activation.approved_by) and bool(
        release.activation.approval_evidence
    )


def active_release(registry: GraphReleases) -> GraphRelease | None:
    """Return the currently active release of the registry."""
    return registry.active_release()


def _parse_release(raw: Mapping[str, object]) -> tuple[GraphRelease, list[str]]:
    errors: list[str] = []
    release_id = _required_str(raw.get("id"), errors, "id")
    owner = _required_str(raw.get("owner"), errors, "owner")
    justification = _required_str(raw.get("justification"), errors, "justification")
    raw_cases = raw.get("affected_case_ids")
    affected = (
        tuple(str(item) for item in raw_cases) if isinstance(raw_cases, list) else ()
    )
    date = _required_str(raw.get("date"), errors, "date")
    raw_components = raw.get("components")
    if not isinstance(raw_components, Mapping):
        errors.append("agent_evals.components_required")
        components = ReleaseComponents(
            prompt_versions=(),
            model_version="",
            state_schema_version="",
            topology_version="",
            intent_schema_version="",
            price_table_version="",
            touches_prompts_or_model=False,
        )
    else:
        components, component_errors = _parse_components(raw_components)
        errors.extend(component_errors)
    raw_activation = raw.get("activation")
    if not isinstance(raw_activation, Mapping):
        errors.append("agent_evals.activation_required")
        activation = ReleaseActivation(
            status="pending",
            approved_by=None,
            approval_evidence=None,
            reverted_reason=None,
        )
    else:
        activation, activation_errors = _parse_activation(raw_activation)
        errors.extend(activation_errors)
    return (
        GraphRelease(
            id=release_id,
            components=components,
            owner=owner,
            justification=justification,
            affected_case_ids=affected,
            activation=activation,
            date=date,
        ),
        errors,
    )


def _parse_components(
    raw: Mapping[str, object],
) -> tuple[ReleaseComponents, list[str]]:
    errors: list[str] = []
    raw_prompts = raw.get("prompt_versions")
    prompts = (
        tuple(str(item) for item in raw_prompts)
        if isinstance(raw_prompts, list)
        else ()
    )
    model_version = _required_str(raw.get("model_version"), errors, "model_version")
    state_schema = _required_str(
        raw.get("state_schema_version"), errors, "state_schema_version"
    )
    topology = _required_str(raw.get("topology_version"), errors, "topology_version")
    intent_schema = _required_str(
        raw.get("intent_schema_version"), errors, "intent_schema_version"
    )
    price_table = _required_str(
        raw.get("price_table_version"), errors, "price_table_version"
    )
    return (
        ReleaseComponents(
            prompt_versions=prompts,
            model_version=model_version,
            state_schema_version=state_schema,
            topology_version=topology,
            intent_schema_version=intent_schema,
            price_table_version=price_table,
            touches_prompts_or_model=bool(raw.get("touches_prompts_or_model", False)),
        ),
        errors,
    )


def _parse_activation(
    raw: Mapping[str, object],
) -> tuple[ReleaseActivation, list[str]]:
    errors: list[str] = []
    status = raw.get("status")
    if not isinstance(status, str) or status not in _ACTIVATION_STATUSES:
        errors.append(f"agent_evals.unknown_activation_status:{status}")
    approved_by = raw.get("approved_by")
    if approved_by is not None and not isinstance(approved_by, str):
        errors.append("agent_evals.approved_by_invalid")
    approval_evidence = raw.get("approval_evidence")
    if approval_evidence is not None and not isinstance(approval_evidence, str):
        errors.append("agent_evals.approval_evidence_invalid")
    reverted_reason = raw.get("reverted_reason")
    if reverted_reason is not None and not isinstance(reverted_reason, str):
        errors.append("agent_evals.reverted_reason_invalid")
    return (
        ReleaseActivation(
            status=str(status or "pending"),  # type: ignore[arg-type]
            approved_by=str(approved_by) if approved_by is not None else None,
            approval_evidence=(
                str(approval_evidence) if approval_evidence is not None else None
            ),
            reverted_reason=(
                str(reverted_reason) if reverted_reason is not None else None
            ),
        ),
        errors,
    )


def _required_str(value: object, errors: list[str], field: str) -> str:
    if not isinstance(value, str) or not value:
        errors.append(f"agent_evals.{field}_required")
        return ""
    return value

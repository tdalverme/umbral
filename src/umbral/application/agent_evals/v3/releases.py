"""Pure parsing for the topology-v4 graph release registry."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from umbral.application.agent_evals.v3.contracts import (
    EvalDataset,
    EvalPolicy,
    EvalRelease,
    EvalReleaseComponents,
    EvalReleases,
    EvalV3ValidationError,
)

_DOCUMENT_FIELDS = frozenset({"contract_version", "registry_version", "releases"})
_RELEASE_FIELDS = frozenset({"id", "components", "owner", "justification", "activation", "date"})
_COMPONENT_FIELDS = frozenset({"prompt_versions", "model_version", "state_schema_version", "topology_version", "interpretation_schema_version", "reply_schema_version", "tool_contract_version", "price_table_version"})
_ACTIVATION_FIELDS = frozenset({"status", "approved_by", "approval_evidence", "reverted_reason"})


def load_releases(path: Path) -> EvalReleases:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise EvalV3ValidationError(("agent_evals_v3.releases_required",))
    return parse_releases(raw)


def parse_releases(data: Mapping[str, object]) -> EvalReleases:
    errors = _unknown(data, _DOCUMENT_FIELDS, "release_document")
    if data.get("contract_version") != "2":
        errors.append("agent_evals_v3.unsupported_release_contract_version")
    if data.get("registry_version") != "graph-releases-v2":
        errors.append("agent_evals_v3.release_registry_version_required")
    raw_releases = data.get("releases")
    if not isinstance(raw_releases, list) or not raw_releases:
        errors.append("agent_evals_v3.releases_required")
        raw_releases = []
    releases: list[EvalRelease] = []
    seen_ids: set[str] = set()
    for raw in raw_releases:
        if not isinstance(raw, Mapping):
            errors.append("agent_evals_v3.release_invalid_shape")
            continue
        release, release_errors = _parse_release(raw)
        errors.extend(release_errors)
        if release is None:
            continue
        if release.id in seen_ids:
            errors.append(f"agent_evals_v3.duplicate_release:{release.id}")
        seen_ids.add(release.id)
        releases.append(release)
    if errors:
        raise EvalV3ValidationError(tuple(sorted(set(errors))))
    return EvalReleases("2", "graph-releases-v2", tuple(releases))


def release_compatibility_key(
    release: EvalRelease, dataset: EvalDataset, policy: EvalPolicy
) -> tuple[str, ...]:
    components = release.components
    return (
        dataset.registry_version,
        policy.registry_version,
        components.state_schema_version,
        components.topology_version,
        components.interpretation_schema_version,
        components.reply_schema_version,
        components.tool_contract_version or "",
        components.price_table_version,
    )


def _parse_release(raw: Mapping[str, object]) -> tuple[EvalRelease | None, list[str]]:
    errors = _unknown(raw, _RELEASE_FIELDS, "release")
    release_id = _required_str(raw.get("id"), errors, "release_id")
    owner = _required_str(raw.get("owner"), errors, "release_owner")
    justification = _required_str(raw.get("justification"), errors, "release_justification")
    date = _required_str(raw.get("date"), errors, "release_date")
    components = _parse_components(raw.get("components"), errors)
    activation = raw.get("activation")
    if not isinstance(activation, Mapping):
        errors.append("agent_evals_v3.release_activation_required")
        activation_copy: Mapping[str, object] = {}
    else:
        errors.extend(_unknown(activation, _ACTIVATION_FIELDS, "release_activation"))
        activation_copy = dict(activation)
    if not release_id or components is None:
        return None, errors
    return EvalRelease(release_id, components, owner, justification, activation_copy, date), errors


def _parse_components(value: object, errors: list[str]) -> EvalReleaseComponents | None:
    if not isinstance(value, Mapping):
        errors.append("agent_evals_v3.release_components_required")
        return None
    errors.extend(_unknown(value, _COMPONENT_FIELDS, "release_components"))
    prompts = value.get("prompt_versions")
    if not isinstance(prompts, list) or not all(isinstance(item, str) and item for item in prompts):
        errors.append("agent_evals_v3.release_prompt_versions_invalid")
        prompt_versions: tuple[str, ...] = ()
    else:
        prompt_versions = tuple(prompts)
    fields = {name: _required_str(value.get(name), errors, f"release_{name}") for name in _COMPONENT_FIELDS - {"prompt_versions", "tool_contract_version"}}
    tool_contract = value.get("tool_contract_version")
    if tool_contract is not None and not isinstance(tool_contract, str):
        errors.append("agent_evals_v3.release_tool_contract_version_invalid")
        tool_contract = None
    return EvalReleaseComponents(prompt_versions, fields["model_version"], fields["state_schema_version"], fields["topology_version"], fields["interpretation_schema_version"], fields["reply_schema_version"], tool_contract, fields["price_table_version"])


def _required_str(value: object, errors: list[str], field: str) -> str:
    if not isinstance(value, str) or not value:
        errors.append(f"agent_evals_v3.{field}_required")
        return ""
    return value


def _unknown(value: Mapping[str, object], allowed: frozenset[str], level: str) -> list[str]:
    return [f"agent_evals_v3.unknown_{level}_property:{key}" for key in value.keys() - allowed]

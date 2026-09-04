"""V4 eval flow: scripted and managed suites over the production V5 graph.

Both fidelities traverse the same ``build_graph`` production path; the
scripted adapter only replaces the interpreter seam (and optionally forces
provider or reply failures). Context assembly, deterministic policy, command
execution, receipts, reply composition, and audit run unmodified. Durable
services are backed by in-memory stores so the suite runs without Postgres.
"""
# ruff: noqa: E501
# mypy: disable-error-code="arg-type,index,call-overload,attr-defined,assignment,no-any-return,redundant-cast"

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal, Protocol, cast
from uuid import UUID, uuid4

from langgraph.checkpoint.memory import MemorySaver

from umbral.agent.graph import GraphDeps, build_graph
from umbral.agent.intent import InterpretationCompiler
from umbral.application.agent.contracts import ModelResult
from umbral.application.agent.ports import ModelGateway
from umbral.application.agent_evals.v4.contracts import (
    FailureStage,
    TrialEvidenceV4,
    TurnEvidenceV4,
)
from umbral.application.agent_evals.v4.grading import grade_trial_v4
from umbral.application.agent_evals.v4.loader import (
    EvalCaseV4,
    EvalDatasetV4,
    EvalPolicyV4,
    EvalReleaseV4,
    ExpectedV4,
    Fidelity,
    SeedV4,
    load_dataset,
    load_policy,
    load_releases,
)
from umbral.application.conversation.contracts import (
    ConversationTurnResult,
)
from umbral.application.conversation.ports import (
    FeedbackRecorder,
    FocusedListing,
)
from umbral.application.conversation.reply import ReplyComposer
from umbral.application.preferences.contracts import (
    BindingDraft,
    PreferenceAuthority,
    PreferenceChange,
    PreferenceExpression,
    PreferenceView,
)
from umbral.infrastructure.agent.model_gateway.managed import ManagedModelGateway
from umbral.infrastructure.config.settings import Settings
from umbral.infrastructure.conversation.composition import (
    ConversationServices,
    build_conversation_turn_service,
)
from umbral.infrastructure.criteria.contract_loader import load_concepts_seed

_NOW = datetime(2026, 8, 26, tzinfo=timezone.utc)
_REPLY_MARKER = "outcomes"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _eval_concept_catalog() -> tuple[Mapping[str, object], ...]:
    """Use the published concept snapshot for every V5 eval interpretation."""
    return tuple(
        {
            "key": concept.key,
            "description": concept.name,
            "matcher_type": concept.matcher_type,
            "computable": bool(concept.compute_policy.get("computable", False)),
            "aliases": list(concept.aliases),
        }
        for concept in load_concepts_seed().concepts
    )


def _settings_from_environment() -> Settings:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in Settings._known_fields
    }
    return Settings.from_environment(environment)


class EvalModelAdapterV4(Protocol):
    fidelity: Fidelity

    def gateway_for(
        self,
        *,
        case: EvalCaseV4,
        release: EvalReleaseV4,
        trial_index: int,
        attempt_index: int,
    ) -> ModelGateway: ...


class ScriptedEvalModelAdapterV4:
    """Replays the declared interpretation at the interpreter seam only."""

    fidelity: Fidelity = "scripted"

    def __init__(self, input_tokens: int = 8, output_tokens: int = 16) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens

    def gateway_for(
        self,
        *,
        case: EvalCaseV4,
        release: EvalReleaseV4,
        trial_index: int,
        attempt_index: int,
    ) -> ModelGateway:
        del trial_index, attempt_index
        return _ScriptedGatewayV4(self, case, release)


class _ScriptedGatewayV4:
    def __init__(
        self,
        adapter: ScriptedEvalModelAdapterV4,
        case: EvalCaseV4,
        release: EvalReleaseV4,
    ) -> None:
        self.adapter = adapter
        self.case = case
        self.release = release
        self._served: set[int] = set()

    def generate_structured(
        self,
        *,
        messages: tuple[Mapping[str, object], ...],
        schema: Mapping[str, object],
        schema_version: str,
        prompt_version: str,
        model_version: str,
        tools: Sequence[Mapping[str, object]] | None = None,
    ) -> ModelResult:
        del schema, schema_version, tools
        is_interpretation = prompt_version.startswith("interpretation")
        if not is_interpretation and prompt_version != "reply":
            return _error_result(model_version, f"unknown_prompt:{prompt_version}")
        if is_interpretation:
            user_text = _user_text(messages)
            for index, turn in enumerate(self.case.turns):
                if turn.user != user_text or index in self._served:
                    continue
                if turn.scripted_behavior == "provider_failure":
                    return _error_result(model_version, "provider.timeout")
                self._served.add(index)
                return _scripted_result(
                    model_version, turn.scripted_interpretation, self.adapter
                )
            return _error_result(model_version, "evals_v4.script_exhausted")
        if any(
            turn.scripted_behavior == "reply_failure" for turn in self.case.turns
        ):
            return _error_result(model_version, "provider.timeout")
        return _scripted_result(
            model_version,
            {
                "contract_version": "5",
                "text": "Procesado.",
                "outcomes": [],
                "verified_refs": [],
                "source": "managed",
            },
            self.adapter,
        )


class ManagedEvalModelAdapterV4:
    """Fresh managed-provider gateway per trial with the release model pinned.

    Declared provider/reply failure cases are injected at their respective
    gateway call. They exercise graph failure handling without pretending that
    a successful model call was a model failure.
    """

    fidelity: Fidelity = "managed"

    def __init__(self, *, settings: object) -> None:
        if (
            getattr(settings, "agent_model_provider", None) != "managed"
            or not getattr(settings, "agent_managed_endpoint", None)
        ):
            raise ValueError(
                "agent_evals_v4.managed_config_required:"
                "AGENT_MODEL_PROVIDER=managed and AGENT_MANAGED_ENDPOINT"
            )
        self.endpoint = settings.agent_managed_endpoint
        self.api_key = getattr(settings, "agent_managed_api_key", None) or ""
        self.model = getattr(settings, "agent_model_name", "gpt-4.1-mini")

    def gateway_for(
        self,
        *,
        case: EvalCaseV4,
        release: EvalReleaseV4,
        trial_index: int,
        attempt_index: int,
    ) -> ModelGateway:
        del release, trial_index, attempt_index
        gateway = cast(
            ModelGateway,
            ManagedModelGateway(
                endpoint=self.endpoint,
                api_key=self.api_key,
                model=self.model,
                max_retries=0,
            ),
        )
        behavior = next(
            (
                turn.scripted_behavior
                for turn in case.turns
                if turn.scripted_behavior is not None
            ),
            None,
        )
        if behavior is None:
            return gateway
        return _InjectedFailureGateway(gateway, behavior)


class _InjectedFailureGateway:
    """Inject one declared infrastructure failure while delegating the rest."""

    def __init__(self, delegate: ModelGateway, behavior: str) -> None:
        self.delegate = delegate
        self.behavior = behavior

    def generate_structured(
        self,
        *,
        messages: tuple[Mapping[str, object], ...],
        schema: Mapping[str, object],
        schema_version: str,
        prompt_version: str,
        model_version: str,
        tools: Sequence[Mapping[str, object]] | None = None,
    ) -> ModelResult:
        if (
            self.behavior == "provider_failure"
            and prompt_version.startswith("interpretation")
        ) or (
            self.behavior == "reply_failure" and prompt_version == "reply"
        ):
            return _error_result(model_version, "provider.timeout")
        return self.delegate.generate_structured(
            messages=messages,
            schema=schema,
            schema_version=schema_version,
            prompt_version=prompt_version,
            model_version=model_version,
            tools=tools,
        )


class V5EvalTrialExecutor:
    """Runs one V5 trial through the production graph with in-memory stores."""

    graph_factory = staticmethod(build_graph)

    def __init__(self, *, contracts_dir: Path) -> None:
        self.contracts_dir = contracts_dir
        self.interpretation_schema = _read_json(
            contracts_dir / "agent" / "interpretation-schema.json"
        )
        self.reply_schema = _read_json(
            contracts_dir / "agent" / "reply-schema.json"
        )
        self.concept_catalog = _eval_concept_catalog()

    def execute(
        self,
        *,
        case: EvalCaseV4,
        release: EvalReleaseV4,
        adapter: EvalModelAdapterV4,
        trial_index: int,
        attempt_index: int,
    ) -> TrialEvidenceV4:
        if release.components.interpretation_schema_version != "interpretation-schema":
            raise ValueError(
                "agent_evals_v5.requires_v5_release:"
                "V5EvalTrialExecutor cannot execute legacy releases"
            )
        del attempt_index
        services = _EvalServices()
        services.seed(case.seed)
        gateway = adapter.gateway_for(
            case=case, release=release, trial_index=trial_index, attempt_index=0
        )
        interpreter = InterpretationCompiler(
            gateway=gateway,
            schema=self.interpretation_schema,
            prompt_version=release.components.prompt_versions[0],
            model_version=release.components.model_version,
            concept_catalog=self.concept_catalog,
        )
        turn_service = build_conversation_turn_service(
            services=ConversationServices(
                chat=cast(Any, services.chat),
                radar=cast(Any, services.radar),
                proposals=cast(Any, services.proposals),
                preferences=services.preferences,
                feedback=cast(FeedbackRecorder, services.feedback),
            ),
            focus=services.focus,
            interpreter=interpreter,
            clock=_now,
        )
        services.turn_service = turn_service
        reply = ReplyComposer(
            gateway=gateway,
            schema=self.reply_schema,
            prompt_version=release.components.prompt_versions[1],
            model_version=release.components.model_version,
        )
        graph = self.graph_factory(
            dependencies=GraphDeps(turn=turn_service, reply=reply),
            checkpointer=MemorySaver(),
        )
        turn_evidence: list[TurnEvidenceV4] = []
        turn_safety: list[bool] = []
        turn_quality: list[bool] = []
        for turn_index, turn in enumerate(case.turns):
            if case.seed.stale_after_context_load:
                result = services.run_stale_turn(turn)
                reply_source = "deterministic_fallback"
            else:
                final = _invoke_graph(
                    graph,
                    case=case,
                    trial_index=trial_index,
                    turn_index=turn_index,
                    turn=turn,
                )
                result = _result_from_state(final)
                reply_source = str(
                    (final.get("reply") or {}).get("source", "managed")
                )
            evidence = _turn_evidence(turn, result)
            safety, quality = _matches_expected(turn.expected, result, reply_source)
            turn_evidence.append(evidence)
            turn_safety.append(safety)
            turn_quality.append(quality)
        invariant_ok = _invariants_ok(case, services)
        return TrialEvidenceV4(
            case_id=case.id,
            release_id=release.id,
            trial_index=trial_index,
            turns=tuple(turn_evidence),
            safety_ok=all(turn_safety) and invariant_ok,
            quality_ok=all(turn_quality),
            cost_usd=0.001 * len(turn_evidence),
            latency_ms=5 * len(turn_evidence),
        )


@dataclass(frozen=True, slots=True)
class ReleaseComparisonV4:
    kind: Literal["statistical_replica", "component_delta"]
    functional_delta: Mapping[str, object] | None


def compare_releases(
    *,
    baseline: tuple[TrialEvidenceV4, ...],
    candidate: tuple[TrialEvidenceV4, ...],
    baseline_release: EvalReleaseV4,
    candidate_release: EvalReleaseV4,
) -> ReleaseComparisonV4:
    """Label identical-component releases as statistical replicates."""
    del baseline, candidate
    if _component_key(baseline_release) == _component_key(candidate_release):
        return ReleaseComparisonV4("statistical_replica", None)
    return ReleaseComparisonV4("component_delta", None)


def run_v4_suite(
    *,
    dataset: EvalDatasetV4,
    release: EvalReleaseV4,
    adapter: EvalModelAdapterV4,
    executor: V5EvalTrialExecutor,
    policy: EvalPolicyV4,
    include_holdout: bool = True,
) -> tuple[TrialEvidenceV4, ...]:
    trials: list[TrialEvidenceV4] = []
    for case in dataset.cases:
        if case.partition == "holdout" and not include_holdout:
            continue
        if adapter.fidelity == "managed":
            trial_count = (
                policy.managed_critical_trials
                if case.risk == "critical"
                else policy.managed_normal_trials
            )
        else:
            trial_count = policy.scripted_trials
        for trial_index in range(trial_count):
            trials.append(
                executor.execute(
                    case=case,
                    release=release,
                    adapter=adapter,
                    trial_index=trial_index,
                    attempt_index=0,
                )
            )
    return tuple(trials)


def run_v4_eval(
    *,
    fidelity: Fidelity,
    release_id: str,
    include_holdout: bool = True,
    contracts_dir: Path = Path(__file__).parents[4] / "contracts",
) -> tuple[TrialEvidenceV4, ...]:
    v4_dir = contracts_dir / "agent-evals" / "v4"
    dataset = load_dataset(v4_dir / "conversation-trajectories-v4.json")
    policy = load_policy(v4_dir / "eval-policy-v4.json")
    releases = load_releases(v4_dir / "graph-releases-v3.json")
    release = next(
        (item for item in releases.releases if item.id == release_id), None
    )
    if release is None:
        raise ValueError(f"unknown release: {release_id}")
    adapter: EvalModelAdapterV4
    if fidelity == "scripted":
        adapter = ScriptedEvalModelAdapterV4()
    else:
        adapter = ManagedEvalModelAdapterV4(settings=_settings_from_environment())
    executor = V5EvalTrialExecutor(contracts_dir=contracts_dir)
    trials = run_v4_suite(
        dataset=dataset,
        release=release,
        adapter=adapter,
        executor=executor,
        policy=policy,
        include_holdout=include_holdout,
    )
    graded = tuple(grade_trial_v4(trial) for trial in trials)
    passed = sum(1 for item in graded if item.safety_ok and item.quality_ok)
    print(
        f"v4 suite {fidelity} release {release_id}: "
        f"{passed}/{len(graded)} trials passed"
    )
    return trials


def main() -> int:
    parser = argparse.ArgumentParser(description="V4 agent evals flow")
    parser.add_argument(
        "--fidelity", choices=["scripted", "managed"], default="scripted"
    )
    parser.add_argument("--release", default="graph-release-005")
    parser.add_argument("--include-holdout", action="store_true")
    args = parser.parse_args()
    try:
        run_v4_eval(
            fidelity=cast(Fidelity, args.fidelity),
            release_id=args.release,
            include_holdout=args.include_holdout,
        )
    except ValueError as exc:
        print(f"invalid configuration: {exc}")
        return 4
    return 0


# ---------------------------------------------------------------------------
# In-memory eval services (application seams backed by memory)
# ---------------------------------------------------------------------------


class _EvalServices:
    def __init__(self) -> None:
        self.user_id = UUID(int=100)
        self.session_id = UUID(int=200)
        self.correlation_id = UUID(int=300)
        self.profile_rows: dict[str, dict[str, object]] = {}
        self.session_rows: dict[str, dict[str, object]] = {}
        self.expression_rows: dict[str, dict[str, object]] = {}
        self.proposal_rows: dict[str, dict[str, object]] = {}
        self.recorded_subjects: set[str] = set()
        self.focused: tuple[UUID, str] | None = None
        self.turn_service: object | None = None
        self.chat = _FakeChat(self)
        self.radar = _FakeRadar(self)
        self.proposals = _FakeProposals(self)
        self.preferences = _FakePreferences(self)
        self.feedback = _FakeFeedback(self)
        self.focus = _FakeFocus(self)

    def seed(self, seed: SeedV4) -> None:
        profile = seed.profile
        profile_id = UUID(int=50)
        self.profile_rows[str(profile_id)] = {
            "profile_id": profile_id,
            "owner_id": self.user_id,
            "name": "Radar",
            "zones": tuple(profile.get("zones") or ()),
            "budget_max": profile.get("budget_max"),
            "min_rooms": profile.get("min_rooms"),
            "version": 1,
        }
        self.session_rows[str(self.session_id)] = {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "search_profile_id": profile_id,
        }
        if seed.focused_listing is not None:
            self.focused = (
                UUID(str(seed.focused_listing["listing_id"])),
                str(seed.focused_listing["text"]),
            )
        for desire in seed.desires:
            expression_id = UUID(int=70 + len(self.expression_rows))
            subject = str(desire["subject"])
            self.expression_rows[str(expression_id)] = {
                "expression_id": expression_id,
                "subject_key": subject,
                "raw_text": str(desire["raw_text"]),
            }
            self.recorded_subjects.add(subject)
        if seed.pending_change is not None:
            pending_id = UUID(str(seed.pending_id)) if seed.pending_id else uuid4()
            self.proposal_rows[str(pending_id)] = {
                "proposal_id": pending_id,
                "search_profile_id": profile_id,
                "diff": dict(seed.pending_change),
                "state": "pending",
                "applied_key": None,
            }

    def run_stale_turn(self, turn: object) -> ConversationTurnResult:
        service = cast(Any, self.turn_service)
        context = service.load_context(
            user_id=self.user_id,
            session_id=self.session_id,
            correlation_id=self.correlation_id,
        )
        try:
            interpretation = service.interpret(
                message_text=cast(Any, turn).user,
                context=context,
                correlation_id=self.correlation_id,
            )
        except Exception as error:
            from umbral.application.conversation.service import _is_provider_error

            stage = (
                "provider_failure"
                if _is_provider_error(error)
                else "interpretation_failure"
            )
            return service._failed_result(context, stage)
        try:
            plan = service.plan(
                user_message=cast(Any, turn).user,
                context=context,
                interpretation=interpretation,
            )
        except Exception:
            return service._failed_result(context, "policy_failure")
        profile = next(iter(self.profile_rows.values()))
        profile["version"] = int(profile["version"]) + 1
        return service.execute(
            user_id=self.user_id,
            session_id=self.session_id,
            message_id=UUID(int=400),
            message_text=cast(Any, turn).user,
            correlation_id=self.correlation_id,
            context=context,
            interpretation=interpretation,
            plan=plan,
        )


class _FakeChat:
    def __init__(self, services: _EvalServices) -> None:
        self.services = services

    def get_session(self, *, user_id: UUID, session_id: UUID) -> object:
        row = self.services.session_rows.get(str(session_id))
        if row is None:
            raise LookupError("session not found")
        return SimpleNamespace(search_profile_id=row.get("search_profile_id"))

    def bind_profile(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        search_profile_id: UUID,
        correlation_id: UUID,
    ) -> None:
        row = self.services.session_rows.get(str(session_id))
        if row is not None:
            row["search_profile_id"] = search_profile_id


class _FakeRadar:
    def __init__(self, services: _EvalServices) -> None:
        self.services = services

    def create_profile(self, **kwargs: object) -> tuple[object, object]:
        del kwargs
        profile_id = UUID(int=50)
        row = self.services.profile_rows.get(str(profile_id))
        if row is None:
            return SimpleNamespace(profile_id=profile_id), None
        return SimpleNamespace(profile_id=profile_id), None

    def get_profile(self, owner_id: UUID, profile_id: UUID) -> SimpleNamespace:
        from umbral.application.radar.contracts import RadarNotAccessible

        row = self.services.profile_rows.get(str(profile_id))
        if row is None or row.get("owner_id") != owner_id:
            raise RadarNotAccessible(profile_id)
        return SimpleNamespace(**row)

    def version_profile(self, **kwargs: object) -> tuple[object, object]:
        from umbral.domain.errors import ConcurrencyConflict

        profile_id = kwargs["profile_id"]
        expected = kwargs["expected_version"]
        row = self.services.profile_rows.get(str(profile_id))
        if row is None:
            raise ConcurrencyConflict(expected_version=0, actual_version=0)
        if int(row["version"]) != int(expected):
            raise ConcurrencyConflict(
                expected_version=int(expected), actual_version=int(row["version"])
            )
        row["version"] = int(row["version"]) + 1
        for key, value in dict(
            cast(Mapping[str, object], kwargs["changes"])
        ).items():
            row[key] = value
        return SimpleNamespace(**row), None

    def list_profiles(
        self, owner_id: UUID, status: object | None
    ) -> tuple[SimpleNamespace, ...]:
        return tuple(
            SimpleNamespace(**row)
            for row in self.services.profile_rows.values()
            if row.get("owner_id") == owner_id
        )

    def validate_change(self, **kwargs: object) -> object:
        return self.get_profile(
            cast(UUID, kwargs["owner_id"]), cast(UUID, kwargs["profile_id"])
        )


class _FakeProposals:
    def __init__(self, services: _EvalServices) -> None:
        self.services = services
        self.repository = _ProposalRepo(services)

    def propose(self, **kwargs: object) -> SimpleNamespace:
        pending_id = uuid4()
        self.services.proposal_rows[str(pending_id)] = {
            "proposal_id": pending_id,
            "search_profile_id": kwargs["search_profile_id"],
            "diff": dict(cast(Mapping[str, object], kwargs["change"])),
            "state": "pending",
            "applied_key": None,
        }
        return SimpleNamespace(proposal_id=pending_id)

    def apply(self, **kwargs: object) -> SimpleNamespace:
        proposal_id = kwargs["proposal_id"]
        key = str(kwargs["idempotency_key"])
        row = self.services.proposal_rows.get(str(proposal_id))
        if row is None or row.get("state") != "pending":
            raise LookupError("proposal not pending")
        if row.get("applied_key") == key:
            return SimpleNamespace(state="approved", profile_version=2)
        if row.get("applied_key") is not None:
            raise LookupError("proposal already applied")
        profile = next(iter(self.services.profile_rows.values()))
        profile["version"] = int(profile["version"]) + 1
        for change_key, change_value in dict(row.get("diff") or {}).items():
            profile[change_key] = change_value
        row["state"] = "approved"
        row["applied_key"] = key
        return SimpleNamespace(
            state="approved", profile_version=profile["version"]
        )

    def reject(self, **kwargs: object) -> SimpleNamespace:
        proposal_id = kwargs["proposal_id"]
        row = self.services.proposal_rows.get(str(proposal_id))
        if row is not None:
            row["state"] = "rejected"
        return SimpleNamespace(proposal_id=proposal_id)

    def pending_for_session(
        self, *, search_profile_id: UUID, session_id: UUID
    ) -> tuple[SimpleNamespace, ...]:
        del session_id
        rows = sorted(
            (
                row
                for row in self.services.proposal_rows.values()
                if row.get("state") == "pending"
                and row.get("search_profile_id") == search_profile_id
            ),
            key=lambda row: str(row["proposal_id"]),
        )
        return tuple(
            SimpleNamespace(
                proposal_id=row["proposal_id"],
                source_act_id=str(row.get("source_act_id", "")),
                queue_ordinal=index + 1,
                queue_total=len(rows),
                diff=dict(row.get("diff") or {}),
            )
            for index, row in enumerate(rows)
        )


class _ProposalRepo:
    def __init__(self, services: _EvalServices) -> None:
        self.services = services

    def latest_pending_for_profile(
        self, search_profile_id: UUID, session_id: UUID
    ) -> SimpleNamespace | None:
        for row in self.services.proposal_rows.values():
            if row.get("state") == "pending" and row.get(
                "search_profile_id"
            ) == search_profile_id:
                return SimpleNamespace(proposal_id=row["proposal_id"])
        return None

    def get(
        self, proposal_id: UUID, session_id: UUID, user_id: UUID
    ) -> SimpleNamespace | None:
        row = self.services.proposal_rows.get(str(proposal_id))
        if row is None:
            return None
        return SimpleNamespace(**row)

    def insert(self, proposal: object) -> object:
        return proposal


class _FakePreferences:
    def __init__(self, services: _EvalServices) -> None:
        self.services = services

    def record_expression(
        self,
        *,
        profile_id: UUID,
        source_message_id: UUID | None,
        subject_key: str,
        raw_text: str,
        authority: PreferenceAuthority,
        binding_drafts: tuple[BindingDraft, ...],
        correlation_id: UUID,
    ) -> PreferenceChange:
        expression_id = uuid4()
        if subject_key in self.services.recorded_subjects:
            raise RuntimeError("preference subject already has an active expression")
        self.services.recorded_subjects.add(subject_key)
        self.services.expression_rows[str(expression_id)] = {
            "expression_id": expression_id,
            "subject_key": subject_key,
            "raw_text": raw_text,
        }
        return _change(expression_id, subject_key, raw_text)

    def revise_expression(self, **kwargs: object) -> PreferenceChange:
        previous = kwargs["previous_expression_id"]
        subject = str(
            self.services.expression_rows.get(str(previous), {}).get(
                "subject_key", "balcon"
            )
        )
        expression_id = uuid4()
        raw_text = str(kwargs["raw_text"])
        self.services.expression_rows[str(expression_id)] = {
            "expression_id": expression_id,
            "subject_key": subject,
            "raw_text": raw_text,
        }
        return _change(expression_id, subject, raw_text)

    def withdraw_expression(
        self,
        *,
        profile_id: UUID,
        expression_id: UUID,
        correlation_id: UUID,
    ) -> PreferenceChange:
        row = self.services.expression_rows.pop(str(expression_id), {})
        subject = str(row.get("subject_key", "balcon"))
        self.services.recorded_subjects.discard(subject)
        return _change(expression_id, subject, "")

    def active_view(self, profile_id: UUID) -> tuple[PreferenceView, ...]:
        return tuple(
            PreferenceView(
                expression_id=UUID(str(row["expression_id"])),
                raw_text=str(row.get("raw_text", "")),
                subject_key=str(row["subject_key"]),
                status="active",
                binding_id=uuid4(),
                binding_kind="unresolved",
                mode="soft",
                confidence=0.5,
                limitations=(),
                evidence_refs=(),
            )
            for row in self.services.expression_rows.values()
        )


class _FakeFeedback:
    def __init__(self, services: _EvalServices) -> None:
        self.services = services

    def record_feedback(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        listing_id: UUID,
        run_id: UUID | None,
        event_type: str,
        reason_keys: tuple[str, ...],
        idempotency_key: str,
        correlation_id: UUID,
        concept_feedback: tuple[Mapping[str, object], ...] = (),
        free_feedback: str | None = None,
        actor_kind: str = "service",
        actor_id: str | None = None,
    ) -> object:
        return SimpleNamespace(noop=False)


class _FakeFocus:
    def __init__(self, services: _EvalServices) -> None:
        self.services = services

    def verified_focus(
        self, *, user_id: UUID, session_id: UUID
    ) -> FocusedListing | None:
        if self.services.focused is None:
            return None
        listing_id, text = self.services.focused
        return FocusedListing(listing_id=listing_id, text=text)


def _change(
    expression_id: UUID, subject_key: str, raw_text: str
) -> PreferenceChange:
    return PreferenceChange(
        expression=PreferenceExpression(
            expression_id=expression_id,
            profile_id=UUID(int=50),
            source_message_id=None,
            source_kind="chat",
            subject_key=subject_key,
            raw_text=raw_text,
            authority="explicit",
            status="active",
            superseded_by=None,
            original_text_available=True,
            created_at=_now(),
            correlation_id=UUID(int=300),
        ),
        bindings=(),
        fact_ids=(),
    )


def _invoke_graph(
    graph: object,
    *,
    case: EvalCaseV4,
    trial_index: int,
    turn_index: int,
    turn: object,
) -> dict[str, object]:
    # The idempotent-retry case replays the SAME message id so receipts dedupe.
    if "idempotent_single_effect" in case.invariants:
        message_id = str(UUID(int=500))
    else:
        message_id = str(uuid4())
    state: dict[str, object] = {
        "contract_version": "5",
        "schema_version": "conversation-state",
        "message_id": message_id,
        "message_text": cast(Any, turn).user,
    }
    config = {
        "configurable": {
            "thread_id": f"{case.id}-{trial_index}-{turn_index}",
            "user_id": str(UUID(int=100)),
            "session_id": str(UUID(int=200)),
            "correlation_id": str(UUID(int=300)),
        }
    }
    final = graph.compiled.invoke(state, config)
    return cast(dict[str, object], final)


def _result_from_state(state: Mapping[str, object]) -> ConversationTurnResult:
    from umbral.agent.graph import _result_from_state as rebuild

    return rebuild(cast(Any, state))


def _turn_evidence(
    turn: object,
    result: ConversationTurnResult,
) -> TurnEvidenceV4:
    context = asdict(result.context)
    return TurnEvidenceV4(
        message=cast(Any, turn).user,
        authorized_context=context,
        interpretation=(
            asdict(result.interpretation)
            if result.interpretation is not None
            else None
        ),
        schema_valid=result.interpretation is not None,
        policy_input=asdict(result.plan) if result.plan is not None else None,
        plan=asdict(result.plan) if result.plan is not None else None,
        effects=tuple(asdict(item) for item in result.executed),
        state_before=context,
        state_after=context,
        reply_text="",
        failure_stage=cast(FailureStage | None, result.failure_stage),
        reason_codes=tuple(
            outcome.reason_code
            for outcome in result.outcomes
            if outcome.reason_code is not None
        ),
    )


def _matches_expected(
    expected: ExpectedV4,
    result: ConversationTurnResult,
    reply_source: str,
) -> tuple[bool, bool]:
    observed_statuses = [outcome.status for outcome in result.outcomes]
    observed_reason_codes = [outcome.reason_code for outcome in result.outcomes]
    observed_effects = [item.effect_key for item in result.executed]
    safety_ok = (
        observed_statuses == list(expected.outcome_statuses)
        and observed_reason_codes == list(expected.reason_codes)
        and result.failure_stage == expected.failure_stage
    )
    quality_ok = (
        observed_effects == list(expected.effects)
        and reply_source == expected.reply_source
    )
    return safety_ok, quality_ok


def _invariants_ok(case: EvalCaseV4, services: _EvalServices) -> bool:
    for invariant in case.invariants:
        if invariant == "idempotent_single_effect":
            if len(services.recorded_subjects) > 1:
                return False
        if invariant == "no_duplicate_mutation":
            applied = [
                row
                for row in services.proposal_rows.values()
                if row.get("applied_key") is not None
            ]
            if len(applied) > 1:
                return False
    return True


def _component_key(release: EvalReleaseV4) -> tuple[str, ...]:
    components = release.components
    return (
        ",".join(components.prompt_versions),
        components.model_version,
        components.state_schema_version,
        components.topology_version,
        components.interpretation_schema_version,
        components.reply_schema_version,
        components.tool_contract_version or "",
        components.price_table_version,
    )


def _user_text(messages: Sequence[Mapping[str, object]]) -> str:
    for message in messages:
        if message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, str) and not content.startswith(_REPLY_MARKER):
                return content
    return ""


def _scripted_result(
    model_version: str,
    content: Mapping[str, object],
    adapter: ScriptedEvalModelAdapterV4,
) -> ModelResult:
    return ModelResult(
        content=_unfrozen(content),
        model_version=model_version,
        status="success",
        latency_ms=1,
        input_tokens=adapter.input_tokens,
        output_tokens=adapter.output_tokens,
        total_tokens=adapter.input_tokens + adapter.output_tokens,
    )


def _error_result(model_version: str, error_code: str) -> ModelResult:
    return ModelResult(
        content=None,
        model_version=model_version,
        status="error",
        latency_ms=0,
        error_code=error_code,
    )


def _unfrozen(value: Mapping[str, object]) -> dict[str, object]:
    def convert(item: object) -> object:
        if isinstance(item, Mapping):
            return {str(key): convert(sub) for key, sub in item.items()}
        if isinstance(item, (list, tuple)):
            return [convert(sub) for sub in item]
        return item

    converted = convert(value)
    assert isinstance(converted, dict)
    return converted


def _read_json(path: Path) -> dict[str, object]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return cast(dict[str, object], raw)


if __name__ == "__main__":
    raise SystemExit(main())

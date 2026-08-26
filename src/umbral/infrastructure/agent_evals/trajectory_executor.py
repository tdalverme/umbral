"""Postgres trajectory executor for the v4 copilot (feature 016, R-03).

Drives every trajectory v2 case through the real v4 copilot stack: topology
v4, the conversation turn service over real RadarService/PreferenceService/
proposals with SQLAlchemy repositories and a Postgres checkpointer. A
deterministic scripted gateway supplies the per-turn v4 interpretation and
reply so the eval measures planning, application, routing and persistence —
not model quality. The executor records the evidence the invariant
evaluators consume: durable state snapshots, questions, turn effects,
binding snapshots and verified target ids.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Protocol, cast
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from umbral.agent.graph import COPILOT_TOPOLOGY_VERSION, build_topology_v4
from umbral.agent.intent.interpretation import InterpretationCompiler
from umbral.agent.runtime import ChatRuntime, GraphLike
from umbral.agent.state import COPILOT_STATE_SCHEMA_VERSION
from umbral.application.agent.contracts import ModelResult
from umbral.application.agent.ports import ModelGateway
from umbral.application.agent.service import RunRecorderService
from umbral.application.agent.tools.proposals import SearchProfileUpdateProposals
from umbral.application.agent_evals.contracts import ModelCallCostRecord
from umbral.application.agent_evals.trajectories.contracts import (
    DurableStateSnapshot,
    TrajectoryCase,
    TrajectoryTrace,
    TurnEffectRecord,
)
from umbral.application.agent_evals.v3.contracts import (
    CaseReview,
    EvalCase,
    EvalRelease,
    EvalReleaseComponents,
    EvalTurn,
    ObservedAct,
    ObservedEffect,
    ObservedToolCall,
    ScriptedTurn,
    TrialTrace,
    TurnExpectation,
    TurnTrace,
)
from umbral.application.chat.service import ChatService
from umbral.application.events.registry import EventsRegistrySpec
from umbral.application.preferences.contracts import (
    PreferenceConcept,
    PreferencePolicySpec,
)
from umbral.application.preferences.service import PreferenceService
from umbral.application.radar.service import RadarService
from umbral.infrastructure.agent.checkpointer import create_postgres_saver
from umbral.infrastructure.agent.intent.interpretation_loader import (
    load_interpretation_schema,
)
from umbral.infrastructure.conversation.composition import (
    CopilotServices,
    build_conversation_turn_service,
)
from umbral.infrastructure.db.models.agent import AgentModelCall, AgentNodeRun
from umbral.infrastructure.db.models.chat import ChatMessage as ChatMessageModel
from umbral.infrastructure.db.repositories.agent import (
    SqlAlchemyGraphRunRepository,
    SqlAlchemyModelCallRepository,
    SqlAlchemyNodeRunRepository,
    SqlAlchemyProposalRepository,
)
from umbral.infrastructure.db.repositories.chat import (
    SqlAlchemyChatMessageRepository,
    SqlAlchemyChatSessionRepository,
    SqlAlchemySearchProfileStatusReader,
)
from umbral.infrastructure.db.repositories.criteria import (
    SqlAlchemyConceptRepository,
)
from umbral.infrastructure.db.repositories.preferences import (
    SqlAlchemyBindingRepository,
    SqlAlchemyExpressionRepository,
)
from umbral.infrastructure.db.repositories.radar import SqlAlchemyEventRepository
from umbral.infrastructure.radar.composition import build_radar_service

SessionFactory = Callable[[], Session]
Clock = Callable[[], datetime]

_NOW = datetime(2026, 8, 14, tzinfo=timezone.utc)
_tick = iter(range(1_000_000))


def _advancing_clock() -> datetime:
    return _NOW + timedelta(seconds=next(_tick))


_REPLY_SCHEMA: dict[str, object] = {
    "reply_text": {"kind": "string", "min_length": 1, "max_length": 2000},
    "effects": {
        "kind": "list",
        "item": {
            "act_id": "string",
            "status": {"enum": ["applied", "pending", "remembered", "rejected"]},
        },
    },
    "question": {"kind": "nullable_string"},
    "refs": {"kind": "list", "item": {"entity": "string", "id": "string"}},
}

_INTERPRETATION_PROMPT = "interpretation-v4"
_REPLY_PROMPT = "reply-v4"
_MATERIAL_KEYS = frozenset({"filter.set", "filter.cleared"})
_PREFERENCE_ACTS = frozenset(
    {
        "express_preference",
        "revise_preference",
        "withdraw_preference",
    }
)
_V4_TOPOLOGY_RELEASE = "chat-topology-v4"
_MISSING_GRAPH_STATE = "agent_evals_v3.missing_graph_state"


class EvalModelAdapter(Protocol):
    """Small local seam matching the application adapter planned for Task 6."""

    def gateway_for(
        self,
        *,
        case: EvalCase,
        release: EvalRelease,
        trial_index: int,
        attempt_index: int,
    ) -> ModelGateway: ...


class ScriptedV4Gateway:
    """Deterministic gateway: returns the scripted v4 acts for the current
    turn and a grounded v4 reply. Act payloads are derived deterministically
    from the user text (subject keys, filter keys/values) so the eval measures
    the copilot's deterministic machinery, not the model.
    """

    def __init__(
        self,
        *,
        turn_acts: Sequence[Sequence[str]],
        turn_texts: Sequence[str],
        reply_text: str = "Listo.",
        model_version: str = "provider-x-model-y",
        latency_ms: int = 1,
        input_tokens: int = 8,
        output_tokens: int = 16,
    ) -> None:
        self.turn_acts = [list(item) for item in turn_acts]
        self.turn_texts = [str(item) for item in turn_texts]
        self.reply_text = reply_text
        self.model_version = model_version
        self.latency_ms = latency_ms
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.calls: list[Mapping[str, object]] = []
        self._turn_index = 0

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
        del messages, schema, schema_version, model_version, tools
        self.calls.append({"prompt_version": prompt_version})
        if prompt_version == _INTERPRETATION_PROMPT:
            index = min(self._turn_index, len(self.turn_acts) - 1)
            kinds = self.turn_acts[index]
            text = self.turn_texts[index] if index < len(self.turn_texts) else ""
            self._turn_index += 1
            acts: list[Mapping[str, object]] = []
            preference_index = 0
            for i, kind in enumerate(kinds):
                if kind in _PREFERENCE_ACTS:
                    act_index = preference_index
                    preference_index += 1
                else:
                    act_index = 0
                acts.append(
                    {
                        "act_id": f"a{i}",
                        "kind": kind,
                        "target": {},
                        "payload": _act_payload(kind, text, act_index=act_index),
                        "confidence": 0.95,
                    }
                )
            content: Mapping[str, object] = {
                "acts": acts,
                "ambiguity": None,
            }
        else:
            content = {
                "reply_text": self.reply_text,
                "effects": [],
                "question": None,
                "refs": [],
            }
        return ModelResult(
            content=dict(content),
            model_version=self.model_version,
            status="success",
            latency_ms=self.latency_ms,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            total_tokens=self.input_tokens + self.output_tokens,
        )


def _act_payload(kind: str, text: str, act_index: int = 0) -> Mapping[str, object]:
    lowered = text.casefold()
    if kind == "create_radar":
        return {"name": "Mi búsqueda"}
    if kind == "express_preference":
        return {
            "subject_key": _subject_key(text, act_index),
            "text": text,
        }
    if kind == "revise_preference":
        return {"subject_key": _subject_key(text, act_index), "text": text}
    if kind == "withdraw_preference":
        return {"subject_key": _subject_key(text, act_index), "text": text}
    if kind == "set_filter":
        return {"key": _filter_key(lowered), "value": _filter_value(lowered)}
    if kind == "clear_filter":
        return {"key": _filter_key(lowered)}
    if kind == "resolve_pending":
        return {"decision": "approve"}
    if kind == "query":
        return {}
    return {}


_SUBJECT_MARKERS: tuple[tuple[str, str], ...] = (
    ("cocina grande", "cocina_grande"),
    ("cerca de cafe", "proximidad_cafes"),
    ("cafe", "cafes_home_office"),
    ("luminos", "luminosidad"),
    ("subte", "subte"),
    ("parque", "parque"),
    ("balcon", "balcon"),
    ("cocina", "cocina"),
    ("moderno", "moderno"),
    ("tranquilo", "tranquilo"),
)


def _subject_key(text: str, act_index: int = 0) -> str:
    """Derive distinct subject keys when one turn expresses several desires
    (FR-004); each act consumes the next matched marker from the text."""
    lowered = " ".join(text.casefold().split())
    matched: list[str] = []
    for marker, key in _SUBJECT_MARKERS:
        if marker in lowered and key not in matched:
            matched.append(key)
    if act_index < len(matched):
        return matched[act_index]
    return "deseo_personalizado"


def _filter_key(lowered: str) -> str:
    if "presupuesto" in lowered or "precio" in lowered or "plata" in lowered:
        return "budget_max"
    if "zona" in lowered or "barrio" in lowered:
        return "zones"
    if "ambiente" in lowered or "habitacion" in lowered:
        return "min_rooms"
    if "superficie" in lowered or "metro" in lowered:
        return "surface_min"
    return "budget_max"


def _filter_value(lowered: str) -> object:
    import re

    match = re.search(r"(\d+(?:[.,]\d+)?)", lowered.replace(",", "."))
    if match is None:
        return None
    raw = match.group(1)
    return float(raw) if "." in raw else int(raw)


@dataclass
class TrajectoryEvalStack:
    runtime: ChatRuntime
    chat: ChatService
    runs: SqlAlchemyGraphRunRepository
    factory: SessionFactory
    radar: RadarService
    preferences: PreferenceService
    proposals: object


class PostgresConversationTrialExecutor:
    """Execute one v3 trial through the product's topology-v4 graph."""

    def __init__(
        self,
        *,
        factory: SessionFactory,
        url: str,
        seed_user: Callable[[SessionFactory], UUID],
        seed_profile: Callable[[SessionFactory, UUID], object],
    ) -> None:
        self.factory = factory
        self.url = url
        self.seed_user = seed_user
        self.seed_profile = seed_profile

    def execute(
        self,
        case: EvalCase,
        release: EvalRelease,
        model_adapter: EvalModelAdapter,
        trial_index: int,
        attempt_index: int,
    ) -> TrialTrace:
        if release.components.topology_version != _V4_TOPOLOGY_RELEASE:
            raise ValueError(
                "agent_evals_v3.incompatible_topology:"
                f"{release.components.topology_version}"
            )

        gateway = model_adapter.gateway_for(
            case=case,
            release=release,
            trial_index=trial_index,
            attempt_index=attempt_index,
        )
        stack = self._build_stack(release=release, gateway=gateway)
        user_id = self.seed_user(self.factory)
        profile_id = self._seed_initial_state(stack, case, user_id)
        session = stack.chat.create_session(
            user_id=user_id,
            search_profile_id=profile_id,
            correlation_id=uuid4(),
        )
        self._seed_pending_state(
            stack=stack,
            case=case,
            user_id=user_id,
            session_id=session.session_id,
            profile_id=profile_id,
        )

        turn_traces: list[TurnTrace] = []
        verified_targets = _declared_verified_targets(case.initial_state)
        verified_targets.add(str(session.session_id))
        if profile_id is not None:
            verified_targets.add(str(profile_id))
        allowed_refs: set[tuple[str, str]] = set()
        run_ids: list[UUID] = []
        effect_offsets: dict[UUID, int] = {}
        total_latency_ms = 0
        previous_interrupted = False

        for index, turn in enumerate(case.turns):
            verified_targets.update(_declared_verified_targets(turn.context))
            resume = previous_interrupted
            outcome = stack.runtime.run_turn(
                user_id=user_id,
                session_id=session.session_id,
                text=turn.user,
                correlation_id=uuid4(),
                resume=resume,
                decision={"decision": "approve"} if resume else None,
                context=turn.context,
            )
            previous_interrupted = outcome.status == "interrupted"
            run_ids.append(outcome.run_id)
            total_latency_ms += outcome.latency_ms or 0
            values = _read_graph_state(stack.runtime.graph, outcome.run_id)
            if values is None:
                model_calls, provider_error = self._model_evidence(run_ids)
                return TrialTrace(
                    case_id=case.id,
                    release_id=release.id,
                    trial_index=trial_index,
                    attempt_index=attempt_index,
                    turns=tuple(turn_traces),
                    verified_target_ids=frozenset(verified_targets),
                    allowed_ref_ids=frozenset(allowed_refs),
                    model_calls=model_calls,
                    latency_ms=total_latency_ms,
                    provider_error_code=provider_error,
                    harness_error_code=_MISSING_GRAPH_STATE,
                )

            raw_effects = tuple(
                raw
                for raw in _as_sequence(values.get("effect_results"))
                if isinstance(raw, Mapping)
            )
            offset = effect_offsets.get(outcome.run_id, 0)
            new_effects = raw_effects[offset:]
            effect_offsets[outcome.run_id] = len(raw_effects)
            observed_effects = tuple(_observed_effect(raw) for raw in new_effects)

            bound = self._session_profile_id(stack, user_id, session.session_id)
            if bound is not None:
                profile_id = bound
                verified_targets.add(str(bound))
            for effect in observed_effects:
                if (
                    effect.status == "applied"
                    and effect.object_id is not None
                    and effect.object_type in {"radar", "preference", "proposal"}
                ):
                    verified_targets.add(effect.object_id)

            if any(
                effect.effect_key == "pending.resolved" for effect in observed_effects
            ):
                turn_traces = [_confirm_material_effects(item) for item in turn_traces]

            accepted_refs = self._accepted_refs(outcome.run_id)
            allowed_refs.update(accepted_refs)
            turn_traces.append(
                TurnTrace(
                    turn_index=index,
                    acts=_observed_acts(values),
                    tools=_observed_tools(values),
                    effects=observed_effects,
                    refs=_generated_refs(values),
                    durable_state=self._durable_state(stack, user_id, profile_id),
                    node_names=self._node_names(outcome.run_id),
                    outcome=outcome.status,
                )
            )

        model_calls, provider_error = self._model_evidence(run_ids)
        return TrialTrace(
            case_id=case.id,
            release_id=release.id,
            trial_index=trial_index,
            attempt_index=attempt_index,
            turns=tuple(turn_traces),
            verified_target_ids=frozenset(verified_targets),
            allowed_ref_ids=frozenset(allowed_refs),
            model_calls=model_calls,
            latency_ms=total_latency_ms,
            provider_error_code=provider_error,
        )

    @staticmethod
    def _session_profile_id(
        stack: TrajectoryEvalStack, user_id: UUID, session_id: UUID
    ) -> UUID | None:
        try:
            session = stack.chat.get_session(user_id=user_id, session_id=session_id)
        except Exception:  # noqa: BLE001 - session unreadable
            return None
        return session.search_profile_id

    def _durable_state(
        self,
        stack: TrajectoryEvalStack,
        user_id: UUID,
        profile_id: UUID | None,
    ) -> Mapping[str, object]:
        if profile_id is None:
            return {"profile_id": None}
        try:
            profile = stack.radar.get_profile(user_id, profile_id)
        except Exception:  # noqa: BLE001 - radar may be mid-creation
            return {"profile_id": None}
        subjects = [
            item.subject_key for item in stack.preferences.active_view(profile_id)
        ]
        return {
            "profile_id": str(profile_id),
            "zones": list(profile.zones),
            "budget_max": profile.budget_max,
            "min_rooms": profile.min_rooms,
            "active_subjects": subjects,
        }

    def _build_stack(
        self, *, release: EvalRelease, gateway: ModelGateway
    ) -> TrajectoryEvalStack:
        components = release.components
        interpretation_prompt, reply_prompt = components.prompt_versions[:2]
        radar = build_radar_service(
            session_factory=self.factory,
            job_runtime=None,
            clock=_advancing_clock,
        )
        chat = ChatService(
            sessions=SqlAlchemyChatSessionRepository(self.factory),
            messages=SqlAlchemyChatMessageRepository(self.factory),
            profile_status=SqlAlchemySearchProfileStatusReader(self.factory),
            events_out=SqlAlchemyEventRepository(self.factory),
            events_registry=_load_events_registry(),
            max_message_length=4000,
            clock=_advancing_clock,
        )
        expressions = SqlAlchemyExpressionRepository(self.factory)
        bindings = SqlAlchemyBindingRepository(self.factory)
        preferences = PreferenceService(
            expressions=expressions,
            bindings=bindings,
            mutations=expressions,
            concepts=_ConceptReader(self.factory),
            policy=PreferencePolicySpec.v1(),
            clock=_advancing_clock,
        )
        runs = SqlAlchemyGraphRunRepository(self.factory)
        recorder = RunRecorderService(
            graph_runs=runs,
            node_runs=SqlAlchemyNodeRunRepository(self.factory),
            model_calls=SqlAlchemyModelCallRepository(self.factory),
        )
        proposals = SearchProfileUpdateProposals(
            repository=SqlAlchemyProposalRepository(self.factory),
            radar=radar,
            events=SqlAlchemyEventRepository(self.factory),
            events_registry=_load_events_registry(),
            ttl_hours=24,
            clock=_advancing_clock,
        )
        interpretation_compiler = InterpretationCompiler(
            gateway=gateway,
            schema=load_interpretation_schema(),
            prompt_version=interpretation_prompt,
            model_version=components.model_version,
            interpretation_version=components.interpretation_schema_version,
        )
        turn_service = build_conversation_turn_service(
            services=CopilotServices(
                chat=chat,
                radar=radar,
                preferences=preferences,
            ),
            proposals=proposals,
            interpretation=interpretation_compiler,
            clock=_advancing_clock,
        )
        saver = create_postgres_saver(self.url, strict_msgpack=True)
        graph = cast(
            "GraphLike",
            build_topology_v4(
                gateway=gateway,
                conversation=chat,
                recorder=recorder,
                saver=saver,
                turn_service=turn_service,
                interpretation=interpretation_compiler,
                clock=_advancing_clock,
                model_version=components.model_version,
                prompt_version=reply_prompt,
                schema_version=components.reply_schema_version,
                reply_schema=_REPLY_SCHEMA,
            ),
        )
        runtime = ChatRuntime(
            graph=graph,
            conversation=chat,
            runs=runs,
            recorder=recorder,
            clock=_advancing_clock,
            state_schema_version=_release_number(
                components.state_schema_version, "chat-state-v"
            ),
            topology_version=_release_number(
                components.topology_version, "chat-topology-v"
            ),
            release_id=release.id,
        )
        return TrajectoryEvalStack(
            runtime=runtime,
            chat=chat,
            runs=runs,
            factory=self.factory,
            radar=radar,
            preferences=preferences,
            proposals=proposals,
        )

    def _seed_initial_state(
        self, stack: TrajectoryEvalStack, case: EvalCase, user_id: UUID
    ) -> UUID | None:
        profiles = _as_sequence(case.initial_state.get("profiles"))
        if not profiles:
            return None
        seeded = self.seed_profile(self.factory, user_id)
        profile_id = cast(UUID, getattr(seeded, "profile_id", None))
        first = profiles[0]
        if isinstance(first, Mapping):
            self._apply_initial_profile_state(stack.radar, user_id, profile_id, first)
            self._seed_initial_subjects(stack.preferences, profile_id, first)
        return profile_id

    def _seed_pending_state(
        self,
        *,
        stack: TrajectoryEvalStack,
        case: EvalCase,
        user_id: UUID,
        session_id: UUID,
        profile_id: UUID | None,
    ) -> None:
        pending = case.initial_state.get("pending_action")
        if isinstance(pending, Mapping) and profile_id is not None:
            self._seed_pending_proposal(
                stack,
                user_id=user_id,
                session_id=session_id,
                profile_id=profile_id,
                pending=pending,
            )

    def _node_names(self, run_id: UUID) -> tuple[str, ...]:
        with self.factory() as current:
            rows = current.scalars(
                select(AgentNodeRun)
                .where(AgentNodeRun.graph_run_id == run_id)
                .order_by(AgentNodeRun.started_at, AgentNodeRun.id)
            )
            return tuple(row.node_name for row in rows)

    def _accepted_refs(self, run_id: UUID) -> frozenset[tuple[str, str]]:
        accepted: set[tuple[str, str]] = set()
        with self.factory() as current:
            rows = current.scalars(
                select(ChatMessageModel)
                .where(
                    ChatMessageModel.graph_run_id == run_id,
                    ChatMessageModel.role == "assistant",
                )
                .order_by(ChatMessageModel.created_at, ChatMessageModel.id)
            )
            for row in rows:
                for raw in _as_sequence(row.content.get("refs")):
                    if not isinstance(raw, Mapping):
                        continue
                    entity = raw.get("entity")
                    ref_id = raw.get("id")
                    if isinstance(entity, str) and isinstance(ref_id, str):
                        accepted.add((entity, ref_id))
        return frozenset(accepted)

    def _model_evidence(
        self, run_ids: Sequence[UUID]
    ) -> tuple[tuple[ModelCallCostRecord, ...], str | None]:
        if not run_ids:
            return (), None
        unique_ids = tuple(dict.fromkeys(run_ids))
        with self.factory() as current:
            rows = tuple(
                current.scalars(
                    select(AgentModelCall)
                    .where(AgentModelCall.graph_run_id.in_(unique_ids))
                    .order_by(AgentModelCall.created_at, AgentModelCall.id)
                )
            )
        records = tuple(
            ModelCallCostRecord(
                model_version=row.model_version,
                input_tokens=row.input_tokens,
                output_tokens=row.output_tokens,
            )
            for row in rows
        )
        provider_error = next(
            (
                row.error_code or f"provider.{row.status}"
                for row in rows
                if row.status != "success"
            ),
            None,
        )
        return records, provider_error

    @staticmethod
    def _seed_initial_subjects(
        preferences: PreferenceService,
        profile_id: UUID,
        initial: Mapping[str, object],
    ) -> None:
        """Persist the active subjects declared in initial_state so revision
        and withdrawal turns have a durable predecessor (FR-014)."""
        from umbral.application.preferences.contracts import BindingDraft

        for subject in _as_sequence(initial.get("active_subjects")):
            if not isinstance(subject, str) or not subject:
                continue
            try:
                preferences.record_expression(
                    profile_id=profile_id,
                    source_message_id=None,
                    subject_key=subject,
                    raw_text=subject,
                    authority="explicit",
                    binding_drafts=(BindingDraft.unresolved("initial_state_seed"),),
                    correlation_id=uuid4(),
                )
            except Exception:  # noqa: BLE001 - duplicate seed degrades gracefully
                continue

    @staticmethod
    def _seed_pending_proposal(
        stack: TrajectoryEvalStack,
        *,
        user_id: UUID,
        session_id: UUID,
        profile_id: UUID,
        pending: Mapping[str, object],
    ) -> None:
        """Materialize the pending action declared in initial_state so the
        confirmation interrupt can resolve it (FR-013)."""
        propose = getattr(stack.proposals, "propose", None)
        if propose is None:
            return
        diff = pending.get("diff")
        change = dict(diff) if isinstance(diff, Mapping) else {"budget_max": 1.0}
        try:
            propose(
                user_id=user_id,
                session_id=session_id,
                search_profile_id=profile_id,
                change=change,
                correlation_id=uuid4(),
            )
        except Exception:  # noqa: BLE001 - invalid seed change degrades gracefully
            return

    @staticmethod
    def _apply_initial_profile_state(
        radar: RadarService,
        user_id: UUID,
        profile_id: UUID,
        initial: Mapping[str, object],
    ) -> None:
        changes: dict[str, object] = {}
        if "zones" in initial:
            changes["zones"] = [
                str(item) for item in _as_sequence(initial.get("zones"))
            ]
        if "budget_max" in initial:
            budget = initial.get("budget_max")
            changes["budget_max"] = (
                float(cast("int | float", budget)) if budget is not None else None
            )
        if "min_rooms" in initial:
            rooms = initial.get("min_rooms")
            changes["min_rooms"] = (
                int(cast("int", rooms)) if rooms is not None else None
            )
        if changes:
            profile = radar.get_profile(user_id, profile_id)
            radar.version_profile(
                owner_id=user_id,
                profile_id=profile_id,
                expected_version=profile.version,
                changes=changes,
                correlation_id=uuid4(),
            )


class PostgresTrajectoryExecutor:
    """Compatibility projection of the shared v3 executor into v2 evidence."""

    def __init__(
        self,
        *,
        factory: SessionFactory,
        url: str,
        seed_user: Callable[[SessionFactory], UUID],
        seed_profile: Callable[[SessionFactory, UUID], object],
        gateway_factory: Callable[[TrajectoryCase], ScriptedV4Gateway] | None = None,
    ) -> None:
        self.shared = PostgresConversationTrialExecutor(
            factory=factory,
            url=url,
            seed_user=seed_user,
            seed_profile=seed_profile,
        )
        self.gateway_factory = gateway_factory or _scripted_gateway_for

    def execute(self, *, case: TrajectoryCase) -> TrajectoryTrace:
        executable = _v3_case_from_v2(case)
        trace = self.shared.execute(
            executable,
            _V2_COMPAT_RELEASE,
            _V2ScriptedAdapter(case, self.gateway_factory),
            0,
            0,
        )
        target_ids = tuple(sorted(trace.verified_target_ids))
        return TrajectoryTrace(
            case_id=case.id,
            durable_states=tuple(
                DurableStateSnapshot(item.turn_index, item.durable_state)
                for item in trace.turns
            ),
            questions=(),
            turn_effects=tuple(
                TurnEffectRecord(
                    turn_index=turn.turn_index,
                    effect_key=effect.effect_key,
                    status=effect.status,
                    confirmed=effect.confirmed,
                    object_type=effect.object_type,
                    object_id=effect.object_id,
                    reason_code=effect.reason_code,
                    target_ids=target_ids,
                )
                for turn in trace.turns
                for effect in turn.effects
            ),
            bindings=(),
            verified_target_ids=target_ids,
        )


class _V2ScriptedAdapter:
    def __init__(
        self,
        case: TrajectoryCase,
        gateway_factory: Callable[[TrajectoryCase], ScriptedV4Gateway],
    ) -> None:
        self.case = case
        self.gateway_factory = gateway_factory

    def gateway_for(
        self,
        *,
        case: EvalCase,
        release: EvalRelease,
        trial_index: int,
        attempt_index: int,
    ) -> ModelGateway:
        del case, release, trial_index, attempt_index
        return cast(ModelGateway, self.gateway_factory(self.case))


_V2_COMPAT_RELEASE = EvalRelease(
    id="trajectory-v2-compat",
    components=EvalReleaseComponents(
        prompt_versions=(_INTERPRETATION_PROMPT, _REPLY_PROMPT),
        model_version="provider-x-model-y",
        state_schema_version=f"chat-state-v{COPILOT_STATE_SCHEMA_VERSION}",
        topology_version=f"chat-topology-v{COPILOT_TOPOLOGY_VERSION}",
        interpretation_schema_version="conversation-interpretation-v4",
        reply_schema_version="reply-v4",
        tool_contract_version=None,
        price_table_version="price-table-v1",
    ),
    owner="trajectory-v2",
    justification="Compatibility projection over the shared v4 executor.",
    activation={},
    date="2026-08-25",
)


def _v3_case_from_v2(case: TrajectoryCase) -> EvalCase:
    turns = tuple(
        EvalTurn(
            user=turn.user,
            context={},
            script=ScriptedTurn(interpretation={}, reply={}),
            expect=TurnExpectation(
                required_acts=turn.expected_acts,
                allowed_acts=turn.expected_acts,
                forbidden_acts=(),
                required_tools=(),
                allowed_tools=(),
                forbidden_tools=(),
                argument_predicates=(),
                required_effects=turn.expected_effects,
                forbidden_effects=(),
                outcomes=("completed", "failed", "interrupted"),
                require_grounding=False,
            ),
        )
        for turn in case.turns
    )
    return EvalCase(
        id=case.id,
        suite="regression",
        partition="development",
        family=case.family,
        risk="normal",
        initial_state=case.initial_state,
        turns=turns,
        final_state=case.final_state,
        invariants=case.invariants,
        tags=("v2-compat",),
        review=CaseReview(
            reviewed_by="trajectory-v2",
            reviewed_at="2026-08-25",
            rationale="Existing v2 contract projected through topology-v4.",
        ),
    )


def _read_graph_state(graph: GraphLike, run_id: UUID) -> Mapping[str, object] | None:
    try:
        snapshot = graph.compiled.get_state(
            {"configurable": {"thread_id": str(run_id)}}
        )
    except Exception:  # noqa: BLE001 - converted to typed harness evidence
        return None
    values = getattr(snapshot, "values", None)
    if not isinstance(values, Mapping) or not values:
        return None
    return values


def _observed_acts(values: Mapping[str, object]) -> tuple[ObservedAct, ...]:
    interpretation = values.get("interpretation")
    if not isinstance(interpretation, Mapping):
        return ()
    acts: list[ObservedAct] = []
    for raw in _as_sequence(interpretation.get("acts")):
        if not isinstance(raw, Mapping):
            continue
        target = raw.get("target")
        payload = raw.get("payload")
        acts.append(
            ObservedAct(
                kind=str(raw.get("kind", "")),
                target=dict(target) if isinstance(target, Mapping) else {},
                payload=dict(payload) if isinstance(payload, Mapping) else {},
            )
        )
    return tuple(acts)


def _observed_tools(values: Mapping[str, object]) -> tuple[ObservedToolCall, ...]:
    tools: list[ObservedToolCall] = []
    for raw in _as_sequence(values.get("tool_calls")):
        if not isinstance(raw, Mapping):
            continue
        args = raw.get("args")
        tools.append(
            ObservedToolCall(
                name=str(raw.get("name") or raw.get("tool") or ""),
                args=dict(args) if isinstance(args, Mapping) else {},
                status=str(raw.get("status", "completed")),
                error_code=(
                    str(raw["error_code"])
                    if isinstance(raw.get("error_code"), str)
                    else None
                ),
            )
        )
    return tuple(tools)


def _observed_effect(raw: Mapping[str, object]) -> ObservedEffect:
    detail = raw.get("detail")
    object_id = raw.get("object_id")
    return ObservedEffect(
        effect_key=str(raw.get("effect_key", "")),
        status=str(raw.get("status", "rejected")),
        object_type=(
            str(raw["object_type"]) if isinstance(raw.get("object_type"), str) else None
        ),
        object_id=str(object_id) if object_id is not None else None,
        reason_code=(
            str(raw["reason_code"]) if isinstance(raw.get("reason_code"), str) else None
        ),
        detail=dict(detail) if isinstance(detail, Mapping) else {},
        confirmed=bool(raw.get("confirmed", False)),
    )


def _confirm_material_effects(turn: TurnTrace) -> TurnTrace:
    effects = tuple(
        replace(effect, confirmed=True)
        if effect.effect_key in _MATERIAL_KEYS
        and effect.status in {"pending", "applied"}
        and not effect.confirmed
        else effect
        for effect in turn.effects
    )
    return replace(turn, effects=effects)


def _generated_refs(
    values: Mapping[str, object],
) -> tuple[Mapping[str, str], ...]:
    context = values.get("context")
    if not isinstance(context, Mapping):
        return ()
    reply = context.get("generated_reply")
    if not isinstance(reply, Mapping):
        return ()
    refs: list[Mapping[str, str]] = []
    for raw in _as_sequence(reply.get("refs")):
        if not isinstance(raw, Mapping):
            continue
        entity = raw.get("entity")
        ref_id = raw.get("id")
        if isinstance(entity, str) and isinstance(ref_id, str):
            refs.append({"entity": entity, "id": ref_id})
    return tuple(refs)


def _declared_verified_targets(source: Mapping[str, object]) -> set[str]:
    targets: set[str] = set()
    for key in ("verified_target_ids", "listing_ids"):
        for item in _as_sequence(source.get(key)):
            if isinstance(item, (str, UUID)):
                targets.add(str(item))
    entity = source.get("entity")
    entity_id = source.get("id")
    if isinstance(entity, str) and isinstance(entity_id, (str, UUID)):
        targets.add(str(entity_id))
    return targets


def _as_sequence(value: object) -> Sequence[object]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value
    return ()


def _release_number(value: str, prefix: str) -> int:
    if not value.startswith(prefix):
        raise ValueError(f"agent_evals_v3.incompatible_version:{value}")
    try:
        return int(value.removeprefix(prefix))
    except ValueError as exc:
        raise ValueError(f"agent_evals_v3.incompatible_version:{value}") from exc


class _ConceptReader:
    """Reads shared concepts as PreferenceConcept values."""

    def __init__(self, factory: SessionFactory) -> None:
        self.inner = SqlAlchemyConceptRepository(factory)

    def get(self, key: str) -> PreferenceConcept | None:
        concept = self.inner.get(key)
        if concept is None:
            return None
        return PreferenceConcept(
            key=concept.key,
            matcher_type=concept.matcher_type,
            computable=bool((concept.compute_policy or {}).get("computable", False)),
        )


def _load_events_registry() -> EventsRegistrySpec:
    from umbral.infrastructure.radar.contract_loader import load_events_registry

    return load_events_registry()


def _scripted_gateway_for(case: TrajectoryCase) -> ScriptedV4Gateway:
    return ScriptedV4Gateway(
        turn_acts=[turn.expected_acts for turn in case.turns],
        turn_texts=[turn.user for turn in case.turns],
    )

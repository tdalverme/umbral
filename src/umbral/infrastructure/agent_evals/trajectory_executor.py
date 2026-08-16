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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from umbral.agent.graph import COPILOT_TOPOLOGY_VERSION, build_topology_v4
from umbral.agent.intent.interpretation import InterpretationCompiler
from umbral.agent.runtime import ChatRuntime, GraphLike
from umbral.agent.state import COPILOT_STATE_SCHEMA_VERSION
from umbral.application.agent.contracts import ModelResult
from umbral.application.agent.ports import ModelGateway
from umbral.application.agent.service import RunRecorderService
from umbral.application.agent.tools.proposals import SearchProfileUpdateProposals
from umbral.application.agent_evals.trajectories.contracts import (
    BindingSnapshot,
    DurableStateSnapshot,
    QuestionSnapshot,
    TrajectoryCase,
    TrajectoryTrace,
    TurnEffectRecord,
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


class PostgresTrajectoryExecutor:
    """Executes one trajectory case through the real v4 copilot stack."""

    def __init__(
        self,
        *,
        factory: SessionFactory,
        url: str,
        seed_user: Callable[[SessionFactory], UUID],
        seed_profile: Callable[[SessionFactory, UUID], object],
        gateway_factory: Callable[[TrajectoryCase], ScriptedV4Gateway] | None = None,
    ) -> None:
        self.factory = factory
        self.url = url
        self.seed_user = seed_user
        self.seed_profile = seed_profile
        self.gateway_factory = gateway_factory or _scripted_gateway_for

    def execute(self, *, case: TrajectoryCase) -> TrajectoryTrace:
        stack = self._build_stack(case)
        user_id = self.seed_user(self.factory)
        initial = case.initial_state
        initial_profiles = initial.get("profiles")
        profile_id: UUID | None = None
        if isinstance(initial_profiles, list) and initial_profiles:
            seeded = self.seed_profile(self.factory, user_id)
            profile_id = cast(UUID, getattr(seeded, "profile_id", None))
            first = initial_profiles[0]
            if isinstance(first, Mapping):
                self._apply_initial_profile_state(
                    stack.radar, user_id, profile_id, first
                )
        session = stack.chat.create_session(
            user_id=user_id,
            search_profile_id=profile_id,
            correlation_id=uuid4(),
        )
        initial_pending = initial.get("pending_action")
        if isinstance(initial_pending, Mapping) and profile_id is not None:
            self._seed_pending_proposal(
                stack,
                user_id=user_id,
                session_id=session.session_id,
                profile_id=profile_id,
                pending=initial_pending,
            )
        if isinstance(initial_profiles, list) and initial_profiles and profile_id:
            first = initial_profiles[0]
            if isinstance(first, Mapping):
                self._seed_initial_subjects(
                    stack.preferences, profile_id, first
                )
        durable_states: list[DurableStateSnapshot] = []
        questions: list[QuestionSnapshot] = []
        effects: list[TurnEffectRecord] = []
        bindings: list[BindingSnapshot] = []
        verified_targets: list[str] = [str(session.session_id)]
        if profile_id is not None:
            verified_targets.append(str(profile_id))
        previous_interrupted = False

        for index, turn in enumerate(case.turns):
            resume = previous_interrupted
            decision = {"decision": "approve"} if resume else None
            outcome = stack.runtime.run_turn(
                user_id=user_id,
                session_id=session.session_id,
                text=turn.user,
                correlation_id=uuid4(),
                resume=resume,
                decision=decision,
            )
            previous_interrupted = outcome.status == "interrupted"
            values = stack.runtime.graph.compiled.get_state(
                {"configurable": {"thread_id": str(outcome.run_id)}}
            ).values
            context = values.get("context")
            ctx = context if isinstance(context, Mapping) else {}
            effect_results = values.get("effect_results") or []
            turn_resolved = any(
                isinstance(raw, Mapping) and raw.get("effect_key") == "pending.resolved"
                for raw in effect_results
            )
            # effect_results accumulates across turns of the same run: only
            # register the effects added by this turn.
            raw_effects = [
                raw for raw in effect_results if isinstance(raw, Mapping)
            ]
            new_effects = raw_effects[len(effects) :]
            for raw in new_effects:
                confirmed = bool(raw.get("confirmed", False))
                raw_key = str(raw.get("effect_key", ""))
                object_id = (
                    str(raw["object_id"])
                    if isinstance(raw.get("object_id"), str)
                    else None
                )
                # Objects created this turn (radar, preference expression) are
                # legitimate targets of the verified session (FR-003).
                if (
                    object_id is not None
                    and raw.get("status") == "applied"
                    and object_id not in verified_targets
                ):
                    verified_targets.append(object_id)
                effects.append(
                    TurnEffectRecord(
                        turn_index=index,
                        effect_key=raw_key,
                        status=str(raw.get("status", "rejected")),
                        confirmed=confirmed,
                        object_type=(
                            str(raw["object_type"])
                            if isinstance(raw.get("object_type"), str)
                            else None
                        ),
                        object_id=object_id,
                        reason_code=(
                            str(raw["reason_code"])
                            if isinstance(raw.get("reason_code"), str)
                            else None
                        ),
                        target_ids=tuple(verified_targets),
                    )
                )
            if turn_resolved:
                # A confirmation resolved the material change: mark every
                # pending material effect of the case as confirmed (FR-013).
                for record in effects:
                    if (
                        record.effect_key in _MATERIAL_KEYS
                        and record.status in {"pending", "applied"}
                        and not record.confirmed
                    ):
                        effects[effects.index(record)] = TurnEffectRecord(
                            turn_index=record.turn_index,
                            effect_key=record.effect_key,
                            status=record.status,
                            confirmed=True,
                            object_type=record.object_type,
                            object_id=record.object_id,
                            reason_code=record.reason_code,
                            target_ids=record.target_ids,
                        )
            question = ctx.get("turn_question")
            if isinstance(question, str) and question:
                questions.append(
                    QuestionSnapshot(
                        turn_index=index,
                        slot="clarification",
                        answered=False,
                    )
                )
            # After a turn the session may have bound a newly created radar
            # (FR-003); refresh the local identity and the verified targets
            # before capturing the durable snapshot.
            bound = self._session_profile_id(stack, user_id, session.session_id)
            if bound is not None and str(bound) not in verified_targets:
                verified_targets.append(str(bound))
            if bound is not None:
                profile_id = bound
            state = self._durable_state(stack, user_id, profile_id)
            durable_states.append(DurableStateSnapshot(turn_index=index, state=state))

        return TrajectoryTrace(
            case_id=case.id,
            durable_states=tuple(durable_states),
            questions=tuple(questions),
            turn_effects=tuple(effects),
            bindings=tuple(bindings),
            verified_target_ids=tuple(verified_targets),
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

    def _build_stack(self, case: TrajectoryCase) -> TrajectoryEvalStack:
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
        gateway = self.gateway_factory(case)
        gateway_typed = cast(ModelGateway, gateway)
        interpretation_compiler = InterpretationCompiler(
            gateway=gateway_typed,
            schema=load_interpretation_schema(),
            prompt_version=_INTERPRETATION_PROMPT,
            model_version="provider-x-model-y",
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
                gateway=gateway_typed,
                conversation=chat,
                recorder=recorder,
                saver=saver,
                turn_service=turn_service,
                interpretation=interpretation_compiler,
                clock=_advancing_clock,
                model_version="provider-x-model-y",
                prompt_version=_REPLY_PROMPT,
                schema_version="reply-v4",
                reply_schema=_REPLY_SCHEMA,
            ),
        )
        runtime = ChatRuntime(
            graph=graph,
            conversation=chat,
            runs=runs,
            recorder=recorder,
            clock=_advancing_clock,
            state_schema_version=COPILOT_STATE_SCHEMA_VERSION,
            topology_version=COPILOT_TOPOLOGY_VERSION,
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

    @staticmethod
    def _seed_initial_subjects(
        preferences: PreferenceService,
        profile_id: UUID,
        initial: Mapping[str, object],
    ) -> None:
        """Persist the active subjects declared in initial_state so revision
        and withdrawal turns have a durable predecessor (FR-014)."""
        from umbral.application.preferences.contracts import BindingDraft

        raw_subjects = initial.get("active_subjects")
        if not isinstance(raw_subjects, list):
            return
        for subject in raw_subjects:
            if not isinstance(subject, str) or not subject:
                continue
            try:
                preferences.record_expression(
                    profile_id=profile_id,
                    source_message_id=None,
                    subject_key=subject,
                    raw_text=subject,
                    authority="explicit",
                    binding_drafts=(
                        BindingDraft.unresolved("initial_state_seed"),
                    ),
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
            zones = initial.get("zones")
            changes["zones"] = (
                [str(item) for item in zones] if isinstance(zones, list) else []
            )
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
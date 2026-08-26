# mypy: disable-error-code="no-untyped-def,no-untyped-call,arg-type"
"""Normalized v3 traces over the shared topology-v4 Postgres executor."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import cast
from uuid import uuid4

import pytest
from tests.integration.chat.conftest import seed_profile
from tests.integration.radar.conftest import seed_user

from umbral.application.agent.contracts import ModelResult
from umbral.application.agent.ports import ModelGateway
from umbral.application.agent_evals.v3.contracts import (
    CaseReview,
    EvalCase,
    EvalRelease,
    EvalReleaseComponents,
    EvalTurn,
    ScriptedTurn,
    TurnExpectation,
)
from umbral.infrastructure.agent_evals import trajectory_executor as executor_module
from umbral.infrastructure.agent_evals.trajectory_executor import ScriptedV4Gateway

_EXPECTATION = TurnExpectation(
    required_acts=(),
    allowed_acts=(),
    forbidden_acts=(),
    required_tools=(),
    allowed_tools=(),
    forbidden_tools=(),
    argument_predicates=(),
    required_effects=(),
    forbidden_effects=(),
    outcomes=("completed", "failed", "interrupted"),
    require_grounding=False,
)


class _ScriptedAdapter:
    def __init__(self, gateway_factory: Callable[[], ModelGateway]) -> None:
        self.gateway_factory = gateway_factory
        self.calls: list[tuple[str, str, int, int]] = []

    def gateway_for(
        self,
        *,
        case: EvalCase,
        release: EvalRelease,
        trial_index: int,
        attempt_index: int,
    ) -> ModelGateway:
        self.calls.append((case.id, release.id, trial_index, attempt_index))
        return self.gateway_factory()


class _ForeignListingGateway(ScriptedV4Gateway):
    def __init__(self, foreign_listing_id: str) -> None:
        super().__init__(
            turn_acts=(("record_feedback",),),
            turn_texts=("No me gusta este aviso",),
        )
        self.foreign_listing_id = foreign_listing_id

    def generate_structured(self, **kwargs) -> ModelResult:
        result = super().generate_structured(**kwargs)
        if kwargs["prompt_version"] == "interpretation-v4":
            return replace(
                result,
                content={
                    "acts": [
                        {
                            "act_id": "a0",
                            "kind": "record_feedback",
                            "target": {},
                            "payload": {"listing_id": self.foreign_listing_id},
                            "confidence": 0.95,
                        }
                    ],
                    "ambiguity": None,
                },
            )
        return replace(
            result,
            content={
                "reply_text": "Encontré una opción.",
                "effects": [],
                "question": None,
                "refs": [
                    {"entity": "listing", "id": self.foreign_listing_id},
                ],
            },
        )


class _FailedReplyGateway(ScriptedV4Gateway):
    def __init__(self) -> None:
        super().__init__(turn_acts=(("query",),), turn_texts=("¿Qué tengo?",))

    def generate_structured(self, **kwargs) -> ModelResult:
        if kwargs["prompt_version"] != "reply-v4":
            return super().generate_structured(**kwargs)
        return ModelResult(
            content=None,
            model_version=str(kwargs["model_version"]),
            status="timeout",
            latency_ms=17,
            input_tokens=5,
            output_tokens=0,
            total_tokens=5,
            error_code="provider.timeout",
        )


def _release(*, topology_version: str = "chat-topology-v4") -> EvalRelease:
    return EvalRelease(
        id="graph-release-003",
        components=EvalReleaseComponents(
            prompt_versions=("interpretation-v4", "reply-v4"),
            model_version="provider-x-model-y",
            state_schema_version="chat-state-v4",
            topology_version=topology_version,
            interpretation_schema_version="interpretation-schema-v4",
            reply_schema_version="reply-v4",
            tool_contract_version=None,
            price_table_version="price-table-v1",
        ),
        owner="test",
        justification="executor integration",
        activation={},
        date="2026-08-25",
    )


def _case(
    *,
    case_id: str,
    user: str,
    act: str,
    initial_state: dict[str, object] | None = None,
) -> EvalCase:
    return EvalCase(
        id=case_id,
        suite="regression",
        partition="development",
        family="executor",
        risk="normal",
        initial_state=initial_state
        or {"profiles": [{"zones": [], "active_subjects": []}]},
        turns=(
            EvalTurn(
                user=user,
                context={},
                script=ScriptedTurn(
                    interpretation={
                        "acts": [
                            {
                                "act_id": "a0",
                                "kind": act,
                                "target": {},
                                "payload": {},
                                "confidence": 0.95,
                            }
                        ],
                        "ambiguity": None,
                    },
                    reply={
                        "reply_text": "Listo.",
                        "effects": [],
                        "question": None,
                        "refs": [],
                    },
                ),
                expect=_EXPECTATION,
            ),
        ),
        final_state={},
        invariants=(),
        tags=(),
        review=CaseReview("test", "2026-08-25", "executor integration"),
    )


def _executor(eval_backend):
    factory, url = eval_backend
    return executor_module.PostgresConversationTrialExecutor(
        factory=factory,
        url=url,
        seed_user=seed_user,
        seed_profile=seed_profile,
    )


def test_single_turn_collects_normalized_trace(eval_backend) -> None:
    case = _case(
        case_id="set-budget",
        user="Quiero un presupuesto máximo de 900",
        act="set_filter",
        initial_state={
            "profiles": [{"zones": [], "budget_max": None, "active_subjects": []}]
        },
    )
    release = _release()
    adapter = _ScriptedAdapter(
        lambda: ScriptedV4Gateway(
            turn_acts=(("set_filter",),),
            turn_texts=(case.turns[0].user,),
            model_version=release.components.model_version,
        )
    )

    trace = _executor(eval_backend).execute(
        case=case,
        release=release,
        model_adapter=adapter,
        trial_index=0,
        attempt_index=0,
    )

    assert trace.case_id == case.id
    assert trace.release_id == release.id
    assert trace.turns[0].acts[0].kind == "set_filter"
    assert trace.turns[0].effects[0].effect_key == "filter.set"
    assert trace.turns[0].durable_state["budget_max"] == 900.0
    assert trace.model_calls
    assert "interpret_turn" in trace.turns[0].node_names
    assert adapter.calls == [(case.id, release.id, 0, 0)]


def test_new_radar_becomes_a_verified_target(eval_backend) -> None:
    case = _case(
        case_id="create-radar",
        user="Creá mi radar",
        act="create_radar",
        initial_state={"profiles": []},
    )
    adapter = _ScriptedAdapter(
        lambda: ScriptedV4Gateway(
            turn_acts=(("create_radar",),),
            turn_texts=(case.turns[0].user,),
        )
    )

    trace = _executor(eval_backend).execute(case, _release(), adapter, 0, 0)

    radar_id = trace.turns[0].effects[0].object_id
    assert radar_id is not None
    assert radar_id in trace.verified_target_ids
    assert trace.turns[0].durable_state["profile_id"] == radar_id


def test_foreign_listing_remains_foreign(eval_backend) -> None:
    foreign_listing_id = str(uuid4())
    case = _case(
        case_id="foreign-listing",
        user="No me gusta este aviso",
        act="record_feedback",
    )
    adapter = _ScriptedAdapter(lambda: _ForeignListingGateway(foreign_listing_id))

    trace = _executor(eval_backend).execute(case, _release(), adapter, 0, 0)

    assert trace.turns[0].effects[0].object_id == foreign_listing_id
    assert trace.turns[0].refs == ({"entity": "listing", "id": foreign_listing_id},)
    assert ("listing", foreign_listing_id) not in trace.allowed_ref_ids
    assert foreign_listing_id not in trace.verified_target_ids


def test_failed_model_call_is_provider_evidence(eval_backend) -> None:
    case = _case(case_id="provider-timeout", user="¿Qué tengo?", act="query")
    adapter = _ScriptedAdapter(_FailedReplyGateway)

    trace = _executor(eval_backend).execute(case, _release(), adapter, 0, 0)

    assert trace.turns[0].outcome == "failed"
    assert trace.model_calls == (
        type(trace.model_calls[0])("provider-x-model-y", 5, 0),
    )
    assert trace.provider_error_code == "provider.timeout"
    assert trace.harness_error_code is None


def test_missing_graph_state_is_a_typed_harness_failure(
    eval_backend, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = _case(case_id="missing-state", user="¿Qué tengo?", act="query")
    adapter = _ScriptedAdapter(
        lambda: ScriptedV4Gateway(
            turn_acts=(("query",),), turn_texts=(case.turns[0].user,)
        )
    )
    monkeypatch.setattr(executor_module, "_read_graph_state", lambda *_args: None)

    trace = _executor(eval_backend).execute(case, _release(), adapter, 0, 0)

    assert trace.turns == ()
    assert trace.harness_error_code == "agent_evals_v3.missing_graph_state"


def test_incompatible_topology_is_rejected_before_seeding() -> None:
    seeded = False

    def forbidden_seed(_factory: executor_module.SessionFactory) -> object:
        nonlocal seeded
        seeded = True
        raise AssertionError("must reject before seeding")

    adapter = _ScriptedAdapter(
        lambda: cast(
            ModelGateway,
            ScriptedV4Gateway(turn_acts=(("query",),), turn_texts=("hola",)),
        )
    )
    executor = executor_module.PostgresConversationTrialExecutor(
        factory=cast(object, lambda: None),
        url="postgresql://unused",
        seed_user=forbidden_seed,
        seed_profile=forbidden_seed,
    )

    with pytest.raises(ValueError, match="agent_evals_v3.incompatible_topology"):
        executor.execute(
            _case(case_id="bad-topology", user="hola", act="query"),
            _release(topology_version="chat-topology-v3"),
            adapter,
            0,
            0,
        )

    assert seeded is False
    assert adapter.calls == []

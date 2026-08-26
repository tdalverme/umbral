# mypy: disable-error-code="no-untyped-def,no-untyped-call,arg-type"
"""Both v3 adapters must traverse the same topology-v4 graph path (Task 4).

The scripted adapter and a managed adapter backed by a fake HTTP client
returning identical payloads must produce equal node names, acts, effects
and final durable state; only latency/token usage may differ.
"""

from __future__ import annotations

from collections.abc import Mapping

from tests.integration.chat.conftest import seed_profile
from tests.integration.radar.conftest import seed_user

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
from umbral.infrastructure.agent_evals.v3_adapters import (
    ManagedEvalModelAdapter,
    ScriptedEvalModelAdapter,
    _user_text,
    select_scripted_content,
)


class _FakeResponse:
    def __init__(self, body: Mapping[str, object]) -> None:
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self._body


class _FakeHttpClient:
    def __init__(self, case: EvalCase) -> None:
        self.case = case
        self.served_interpretations: set[int] = set()

    def post(self, url: str, headers: Mapping[str, str], json: Mapping[str, object]):
        del url, headers
        payload = json
        content = select_scripted_content(
            self.case,
            str(payload["prompt_version"]),
            _user_text(tuple(payload["messages"])),
            served_interpretations=self.served_interpretations,
        )
        return _FakeResponse(
            {
                "content": dict(content),
                "usage": {
                    "input_tokens": 3,
                    "output_tokens": 9,
                    "total_tokens": 12,
                },
            }
        )


def _case() -> EvalCase:
    user = "Quiero un depto luminoso y cerca del subte"
    interpretation = {
        "acts": [
            {
                "act_id": "a0",
                "kind": "create_radar",
                "target": {},
                "payload": {"name": "Mi búsqueda"},
                "confidence": 0.95,
            },
            {
                "act_id": "a1",
                "kind": "express_preference",
                "target": {},
                "payload": {"subject_key": "luminosidad", "text": user},
                "confidence": 0.95,
            },
            {
                "act_id": "a2",
                "kind": "express_preference",
                "target": {},
                "payload": {"subject_key": "subte", "text": user},
                "confidence": 0.95,
            },
        ],
        "ambiguity": None,
    }
    reply: dict[str, object] = {
        "reply_text": "Listo.",
        "effects": [],
        "question": None,
        "refs": [],
    }
    expectation = TurnExpectation(
        ("create_radar", "express_preference"),
        ("create_radar", "express_preference"),
        (),
        (),
        (),
        (),
        (),
        ("radar.created", "preference.remembered"),
        (),
        ("completed",),
        False,
    )
    return EvalCase(
        id="same-path-radar",
        suite="regression",
        partition="development",
        family="radar_creation",
        risk="normal",
        initial_state={"profiles": []},
        turns=(
            EvalTurn(
                user,
                {},
                ScriptedTurn(interpretation=interpretation, reply=reply),
                expectation,
            ),
        ),
        final_state={"active_subjects": ["luminosidad", "subte"]},
        invariants=(
            "final_state_matches_expected",
            "no_unconfirmed_material_effect",
            "no_wrong_target_mutation",
        ),
        tags=(),
        review=CaseReview("reviewer", "2026-08-25", "test"),
    )


def _release() -> EvalRelease:
    return EvalRelease(
        id="graph-release-003",
        components=EvalReleaseComponents(
            prompt_versions=("interpretation-v4", "reply-v4"),
            model_version="gpt-4.1-mini",
            state_schema_version="chat-state-v4",
            topology_version="chat-topology-v4",
            interpretation_schema_version="interpretation-schema-v4",
            reply_schema_version="reply-v4",
            tool_contract_version=None,
            price_table_version="price-table-v1",
        ),
        owner="test",
        justification="same-path",
        activation={},
        date="2026-08-25",
    )


def test_scripted_and_managed_traverse_the_same_graph_path(eval_backend) -> None:
    factory, url = eval_backend
    executor = executor_module.PostgresConversationTrialExecutor(
        factory=factory,
        url=url,
        seed_user=seed_user,
        seed_profile=seed_profile,
    )
    case = _case()
    release = _release()

    scripted = executor.execute(
        case=case,
        release=release,
        model_adapter=ScriptedEvalModelAdapter(),
        trial_index=0,
        attempt_index=0,
    )
    managed_settings = type(
        "T",
        (),
        {
            "agent_model_provider": "managed",
            "agent_managed_endpoint": "http://fake:1/",
            "agent_managed_api_key": "x",
            "agent_model_name": "provider-model-7",
            "agent_model_timeout_seconds": 30.0,
        },
    )
    managed = executor.execute(
        case=case,
        release=release,
        model_adapter=_ManagedAdapterFromSettings(managed_settings, case),
        trial_index=0,
        attempt_index=0,
    )

    assert scripted.release_id == managed.release_id == release.id
    assert scripted.turns[0].node_names == managed.turns[0].node_names
    assert scripted.turns[0].acts == managed.turns[0].acts
    # Effects differ only in per-run object ids (new radar/expression uuids);
    # every behavior field must match exactly.
    assert _normalized(scripted.turns[0].effects) == _normalized(
        managed.turns[0].effects
    )
    # Durable state matches except the per-run radar profile id.
    assert _normalized_state(scripted.turns[0].durable_state) == _normalized_state(
        managed.turns[0].durable_state
    )
    assert scripted.turns[0].outcome == managed.turns[0].outcome == "completed"
    assert scripted.turns[0].refs == managed.turns[0].refs == ()
    assert scripted.model_calls and managed.model_calls


def _normalized_state(state) -> dict[str, object]:
    return {
        key: ("<profile>" if key == "profile_id" else value)
        for key, value in state.items()
    }


def _normalized(effects) -> tuple[object, ...]:
    return tuple(
        (
            effect.effect_key,
            effect.status,
            effect.object_type,
            "<object>" if effect.object_id is not None else None,
            effect.reason_code,
            tuple(sorted((key, value) for key, value in effect.detail.items())),
            effect.confirmed,
        )
        for effect in effects
    )


def test_managed_adapter_rejects_unmanaged_configuration() -> None:
    import pytest

    settings = type(
        "T",
        (),
        {"agent_model_provider": "fake", "agent_managed_endpoint": None},
    )()
    with pytest.raises(ValueError, match="agent_evals_v3.managed_config_required"):
        ManagedEvalModelAdapter(settings=settings)


class _ManagedAdapterFromSettings:
    """Managed-shaped adapter backed by the fake HTTP client; the unit-tested
    real adapter is covered in test_v3_adapters.py."""

    fidelity = "managed"

    def __init__(self, settings, case: EvalCase) -> None:
        self.settings = settings
        self.case = case

    def gateway_for(self, *, case, release, trial_index, attempt_index):
        del case, release, trial_index, attempt_index
        from umbral.infrastructure.agent.model_gateway.managed import (
            ManagedModelGateway,
        )

        return ManagedModelGateway(
            endpoint=self.settings.agent_managed_endpoint,
            api_key=self.settings.agent_managed_api_key,
            model=self.settings.agent_model_name,
            timeout_seconds=self.settings.agent_model_timeout_seconds,
            max_retries=0,
            http_client=_FakeHttpClient(self.case),
        )
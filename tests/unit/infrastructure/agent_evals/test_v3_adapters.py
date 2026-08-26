# mypy: disable-error-code="no-untyped-def,no-untyped-call,arg-type"
"""Unit tests for the v3 scripted and managed model adapters (Task 4)."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

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
from umbral.infrastructure.agent.model_gateway.managed import ManagedModelGateway
from umbral.infrastructure.agent_evals.v3_adapters import (
    ManagedEvalModelAdapter,
    ScriptedEvalModelAdapter,
)
from umbral.infrastructure.config.settings import Settings

_INTERPRETATION: dict[str, object] = {
    "acts": [
        {
            "act_id": "a0",
            "kind": "set_filter",
            "target": {},
            "payload": {"key": "budget_max", "value": 900.0},
            "confidence": 0.95,
        }
    ],
    "ambiguity": None,
}
_REPLY: dict[str, object] = {
    "reply_text": "Listo.",
    "effects": [],
    "question": None,
    "refs": [],
}


_USER_TEXT = "Quiero un presupuesto de 900"


def _turn(user: str) -> EvalTurn:
    return EvalTurn(
        user,
        {},
        ScriptedTurn(interpretation=_INTERPRETATION, reply=_REPLY),
        TurnExpectation((), (), (), (), (), (), (), (), (), ("completed",), False),
    )


def _case() -> EvalCase:
    return EvalCase(
        id="case-unit",
        suite="regression",
        partition="development",
        family="executor",
        risk="normal",
        initial_state={},
        turns=(_turn(_USER_TEXT),),
        final_state={},
        invariants=(),
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
        justification="unit",
        activation={},
        date="2026-08-25",
    )


def _gateway(adapter: ScriptedEvalModelAdapter, prompts: tuple[tuple[str, str], ...]):
    return adapter.gateway_for(
        case=_case(), release=_release(), trial_index=0, attempt_index=0
    )


def _gateway_for_case(
    adapter: ScriptedEvalModelAdapter, case: EvalCase, release: EvalRelease
):
    return adapter.gateway_for(
        case=case, release=release, trial_index=0, attempt_index=0
    )


def _call(
    gateway: ModelGateway,
    *,
    prompt_version: str,
    user_text: str,
    schema_version: str = "interpretation-schema-v4",
) -> ModelResult:
    return gateway.generate_structured(
        messages=(
            {"role": "system", "content": "system"},
            {"role": "user", "content": user_text},
        ),
        schema={},
        schema_version=schema_version,
        prompt_version=prompt_version,
        model_version="gpt-4.1-mini",
    )


def test_scripted_selects_interpretation_then_reply_for_same_turn() -> None:
    adapter = ScriptedEvalModelAdapter()
    gateway = _gateway(adapter, ())

    interpreted = _call(
        gateway, prompt_version="interpretation-v4", user_text=_USER_TEXT
    )
    replied = _call(gateway, prompt_version="reply-v4", user_text=_USER_TEXT)

    assert interpreted.content == _INTERPRETATION
    assert replied.content == _REPLY
    assert [call["prompt_version"] for call in adapter.calls] == [
        "interpretation-v4",
        "reply-v4",
    ]


def test_scripted_records_usage_on_every_result() -> None:
    adapter = ScriptedEvalModelAdapter(input_tokens=3, output_tokens=7)
    gateway = _gateway(adapter, ())

    result = _call(gateway, prompt_version="reply-v4", user_text=_USER_TEXT)

    assert result.input_tokens == 3
    assert result.output_tokens == 7
    assert result.total_tokens == 10
    assert result.model_version == "gpt-4.1-mini"
    assert result.status == "success"


def test_scripted_returns_declared_payload_verbatim() -> None:
    adapter = ScriptedEvalModelAdapter()
    gateway = _gateway_for_case(adapter, _case(), _release())
    interpretation = _call(
        gateway, prompt_version="interpretation-v4", user_text=_USER_TEXT
    )

    assert interpretation.content is not None
    assert _first_act_payload(interpretation.content) == {
        "key": "budget_max",
        "value": 900.0,
    }


def _first_act_payload(content: Mapping[str, object]) -> object:
    acts = content["acts"]
    assert isinstance(acts, list) and acts
    first = acts[0]
    assert isinstance(first, Mapping)
    return first["payload"]


def test_scripted_reply_matches_resumed_turn_text() -> None:
    """A confirmation resume composes its reply with the decision turn text
    even though the interpreter never ran for it (topology-v4 resume)."""
    case = _case()
    release = _release()
    adapter = ScriptedEvalModelAdapter()
    gateway = _gateway_for_case(adapter, case, release)

    _call(gateway, prompt_version="interpretation-v4", user_text=_USER_TEXT)
    reply = gateway.generate_structured(
        messages=(
            {"role": "system", "content": "system"},
            {"role": "user", "content": _USER_TEXT},
            {
                "role": "user",
                "content": (
                    'Efectos de este turno: [{"effect_key": "pending.resolved"}]'
                ),
            },
        ),
        schema={},
        schema_version="reply-v4",
        prompt_version="reply-v4",
        model_version="gpt-4.1-mini",
    )

    assert reply.content == _REPLY


def test_scripted_exhausts_instead_of_reusing_last_response() -> None:
    adapter = ScriptedEvalModelAdapter()
    gateway = _gateway(adapter, ())

    result = _call(gateway, prompt_version="reply-v4", user_text="texto no declarado")

    assert result.status == "error"
    assert result.content is None
    assert "evals_v3.script_exhausted" in (result.error_code or "")


def test_scripted_advances_through_repeated_texts() -> None:
    case = _case()
    second = _turn(_USER_TEXT)
    case = EvalCase(
        id=case.id,
        suite=case.suite,
        partition=case.partition,
        family=case.family,
        risk=case.risk,
        initial_state=case.initial_state,
        turns=(case.turns[0], second),
        final_state=case.final_state,
        invariants=case.invariants,
        tags=case.tags,
        review=case.review,
    )
    adapter = ScriptedEvalModelAdapter()
    gateway = _gateway_for_case(adapter, case, _release())

    first = _call(gateway, prompt_version="interpretation-v4", user_text=_USER_TEXT)
    second_result = _call(
        gateway, prompt_version="interpretation-v4", user_text=_USER_TEXT
    )

    assert first.status == "success"
    assert second_result.status == "success"


def test_managed_adapter_requires_managed_settings() -> None:
    settings = _settings(provider="fake", endpoint=None)

    with pytest.raises(ValueError, match="agent_evals_v3.managed_config_required"):
        ManagedEvalModelAdapter(settings=settings)


def test_managed_adapter_builds_fresh_pinned_gateway_per_trial() -> None:
    settings = _settings(provider="managed", endpoint="http://gateway:8080/v1")
    adapter = ManagedEvalModelAdapter(settings=settings)

    first = _managed_gateway(adapter, attempt=0)
    second = _managed_gateway(adapter, attempt=1)

    assert first != second
    assert first.max_retries == 0
    assert second.endpoint == "http://gateway:8080/v1"
    assert first.model == "provider-model-7"
    assert first.timeout_seconds == 12.5
    assert first.api_key == "secret-key"


def _managed_gateway(
    adapter: ManagedEvalModelAdapter, *, attempt: int
) -> ManagedModelGateway:
    return adapter.gateway_for(  # type: ignore[return-value]
        case=_case(), release=_release(), trial_index=0, attempt_index=attempt
    )


def _settings(*, provider: str, endpoint: str | None) -> Settings:
    base: dict[str, str] = {
        "UMBRAL_ENV": "local",
        "UMBRAL_RELEASE_ID": "test",
        "UMBRAL_RELEASE_MANIFEST": "<local>",
        "DATABASE_URL": "postgresql://u:p@127.0.0.1/db",
        "REDIS_URL": "redis://127.0.0.1:6379/0",
        "OBJECT_STORE_BACKEND": "filesystem",
        "OBJECT_STORE_ROOT": ".umbral-local",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:4318",
        "UMBRAL_API_BASE_URL": "http://127.0.0.1:8000",
    }
    values: dict[str, object] = {
        "AGENT_MODEL_PROVIDER": provider,
        "AGENT_MODEL_NAME": "provider-model-7",
        "AGENT_MODEL_TIMEOUT_SECONDS": 12.5,
        "AGENT_MODEL_MAX_RETRIES": 3,
        "AGENT_MANAGED_API_KEY": "secret-key",
    }
    if endpoint is not None:
        values["AGENT_MANAGED_ENDPOINT"] = endpoint
    merged = {**base, **values}
    return Settings.from_environment(
        {str(key): str(value) for key, value in merged.items()}
    )
# mypy: disable-error-code="no-untyped-def,no-untyped-call"
"""propose_search_preference_update tool tests (014-soft-preferences-chat)."""

from __future__ import annotations

from uuid import UUID

from tests.support.agent import RecordingRunRecorder
from tests.support.tools import (
    FakeCriteria,
    FakeFeedback,
    FakeRadar,
    FakeScopeReader,
    FakeScoring,
    build_executor,
    call_tool,
    payload,
)

from umbral.agent.tools.executor import ToolExecutor
from umbral.agent.tools.registry import ToolRegistry
from umbral.agent.tools.tools import ToolServices, build_tool_implementations
from umbral.application.agent.tools.ports import SessionScope
from umbral.application.agent.tools.preference_interpreter import (
    PreferenceInterpretation,
)
from umbral.application.preferences.contracts import PreferenceValidationError
from umbral.infrastructure.agent.tools.contract_loader import load_tool_contract
from umbral.infrastructure.agent.tools.preferences_loader import (
    load_preference_vocabulary,
)

USER_PROFILE_ID = UUID(int=5)


def test_preference_tool_creates_pending_proposal_from_natural_phrase() -> None:
    executor, services = build_executor()
    result = call_tool(
        executor,
        "propose_search_preference_update",
        {"preference": "luminoso"},
    )
    assert result.status == "ok"
    data = payload(result)
    assert data["state"] == "pending"
    assert data["proposal_id"]
    assert data["diff"]["concept_key"] == "luminosidad"
    assert data["diff"]["polarity"] == "positive"
    assert data["impact"]["will_recompute"] is True
    assert data["impact"]["contradicts"] is False
    assert services.feedback.preference_calls == [
        {
            "profile_id": str(USER_PROFILE_ID),
            "concept_key": "luminosidad",
            "polarity": "positive",
            "value": None,
            "correlation_id": str(UUID(int=9)),
        }
    ]


def test_preference_tool_keeps_categorical_value() -> None:
    executor, _ = build_executor()
    result = call_tool(
        executor,
        "propose_search_preference_update",
        {"preference": "cocina separada"},
    )
    assert result.status == "ok"
    data = payload(result)
    assert data["diff"]["concept_key"] == "tipo_cocina"
    assert data["diff"]["concept_value"] == "separada"


def test_preference_tool_rejects_unknown_phrase_with_actionable_code() -> None:
    executor, _ = build_executor()
    result = call_tool(
        executor,
        "propose_search_preference_update",
        {"preference": "cerca del subte"},
    )
    assert result.status == "error"
    assert result.error_code == "preference.unknown_concept"


def test_preference_tool_requires_non_empty_phrase() -> None:
    executor, _ = build_executor()
    result = call_tool(
        executor,
        "propose_search_preference_update",
        {"preference": "   "},
    )
    assert result.status == "error"
    assert result.error_code == "tool.args_invalid"


def test_preference_removal_tool_creates_pending_removal_proposal() -> None:
    executor, services = build_executor()
    result = call_tool(
        executor,
        "propose_search_preference_removal",
        {"preference": "luminosidad"},
    )
    assert result.status == "ok"
    data = payload(result)
    assert data["state"] == "pending"
    assert data["diff"]["concept_key"] == "luminosidad"
    assert data["diff"]["operation"] == "remove"
    assert data["impact"]["operation"] == "remove"
    assert services.feedback.preference_calls[-1]["operation"] == "remove"


def test_preference_list_returns_active_facts() -> None:
    executor, _ = build_executor()
    result = call_tool(executor, "list_search_preferences", {})
    assert result.status == "ok"
    assert payload(result)["preferences"] == []


def test_learning_confirmation_tool_creates_pending_decision() -> None:
    executor, _ = build_executor()
    result = call_tool(
        executor,
        "propose_learning_confirmation",
        {"learning_proposal_id": str(UUID(int=95))},
    )
    assert result.status == "ok"
    data = payload(result)
    assert data["state"] == "pending"
    assert data["diff"]["concept_key"] == "luminosidad"
    assert data["diff"]["operation"] == "learning"
    assert data["impact"]["source"] == "feedback"


def test_learning_confirmation_tool_requires_valid_uuid() -> None:
    executor, _ = build_executor()
    result = call_tool(
        executor,
        "propose_learning_confirmation",
        {"learning_proposal_id": "no-uuid"},
    )
    assert result.status == "error"
    assert result.error_code == "tool.args_invalid"


def _structured_interpretation() -> PreferenceInterpretation:
    return PreferenceInterpretation(
        kind="structured",
        concept_key="luminosidad",
        polarity="positive",
        confidence=0.9,
        matcher_type="semantic_feature",
        params={"concept": "luminosidad"},
    )


class _RecordingPreferences:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[str, object]] = []

    def record_expression(
        self,
        *,
        profile_id: UUID,
        source_message_id: object,
        subject_key: str,
        raw_text: str,
        authority: str,
        binding_drafts: tuple[object, ...],
        correlation_id: UUID,
    ) -> object:
        if self.error is not None and any(
            getattr(draft, "kind", None) == "structured" for draft in binding_drafts
        ):
            raise self.error
        self.calls.append((raw_text, binding_drafts))
        return None


def _llm_executor(
    *, preferences: _RecordingPreferences, interpret: object
) -> ToolExecutor:
    services = ToolServices(
        radar=FakeRadar(),
        scoring=FakeScoring(),
        feedback=FakeFeedback(),
        criteria=FakeCriteria(),
        proposals=object(),
        vocabulary=load_preference_vocabulary(),
        preferences=preferences,
        interpret_preference=interpret,
    )
    return ToolExecutor(
        registry=ToolRegistry(load_tool_contract),
        implementations=build_tool_implementations(services),
        recorder=RecordingRunRecorder(),
        scope_reader=FakeScopeReader(
            SessionScope(
                session_id=UUID(int=2),
                search_profile_id=USER_PROFILE_ID,
                status="active",
            )
        ),
        timeout_seconds=1.0,
    )


def test_llm_preference_flow_proposes_structured_binding() -> None:
    preferences = _RecordingPreferences()

    class _Interpret:
        def __call__(self, _phrase: str) -> PreferenceInterpretation:
            return _structured_interpretation()

    result = call_tool(
        _llm_executor(preferences=preferences, interpret=_Interpret()),
        "propose_search_preference_update",
        {"preference": "quiero un depto luminoso"},
    )
    assert result.status == "ok"
    data = payload(result)
    assert data["outcome"] == "proposed"
    assert data["kind"] == "structured"
    assert data["concept_key"] == "luminosidad"
    assert data["proposal_id"] is None
    assert len(preferences.calls) == 1
    text, drafts = preferences.calls[0]
    assert text == "quiero un depto luminoso"
    assert len(drafts) == 1 and getattr(drafts[0], "kind") == "structured"


def test_llm_preference_flow_preserves_phrase_when_persist_rejected() -> None:
    preferences = _RecordingPreferences(
        error=PreferenceValidationError(("preferences.structured_concept_not_found",))
    )

    class _Interpret:
        def __call__(self, _phrase: str) -> PreferenceInterpretation:
            return _structured_interpretation()

    result = call_tool(
        _llm_executor(preferences=preferences, interpret=_Interpret()),
        "propose_search_preference_update",
        {"preference": "quiero un depto luminoso"},
    )
    assert result.status == "ok"
    data = payload(result)
    assert data["outcome"] == "preserved"
    assert data["preserved"] is True
    assert data["kind"] == "unresolved"
    assert "structured_concept_not_found" in data["reason"]
    # the structured attempt was rejected; only the unresolved fallback landed
    assert len(preferences.calls) == 1
    _, drafts = preferences.calls[0]
    assert len(drafts) == 1 and getattr(drafts[0], "kind") == "unresolved"


def test_llm_preference_flow_never_crashes_when_interpreter_raises() -> None:
    preferences = _RecordingPreferences()

    class _Booming:
        def __call__(self, _phrase: str) -> PreferenceInterpretation:
            raise RuntimeError("provider boom")

    result = call_tool(
        _llm_executor(preferences=preferences, interpret=_Booming()),
        "propose_search_preference_update",
        {"preference": "quiero un depto luminoso"},
    )
    assert result.status == "ok"
    data = payload(result)
    assert data["outcome"] == "preserved"
    assert data["kind"] == "unresolved"
    assert data["reason"] == "interpretation_failed"
    assert len(preferences.calls) == 1

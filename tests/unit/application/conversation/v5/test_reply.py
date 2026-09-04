"""Unit tests for V5 effect-grounded reply composition."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal, cast

import pytest

from umbral.application.agent.contracts import ModelResult
from umbral.application.agent.ports import ModelGateway
from umbral.application.conversation.v5.contracts import (
    ActOutcomeV5,
    ConceptLinkV5,
    ConversationTurnResultV5,
    ExecutedActV5,
    PendingActionV5,
    RecordDesireCommand,
    TurnContextV5,
    TurnPlanV5,
)
from umbral.application.conversation.v5.reply import ReplyComposerV5

ROOT = Path(__file__).resolve().parents[5]
REPLY_SCHEMA = json.loads(
    (ROOT / "contracts" / "agent" / "v5" / "reply-schema-v5.json").read_text(
        encoding="utf-8"
    )
)


class _FakeGateway:
    def __init__(
        self,
        reply: Mapping[str, object] | None = None,
        status: Literal["success", "error"] = "success",
    ) -> None:
        self._reply = reply or {}
        self._status = status
        self.calls = 0

    def generate_structured(
        self,
        *,
        messages: tuple[Mapping[str, object], ...],
        schema: Mapping[str, object],
        schema_version: str,
        prompt_version: str,
        model_version: str,
        tools: Any = None,
    ) -> ModelResult:
        self.calls += 1
        return ModelResult(
            content=dict(self._reply) if self._status == "success" else None,
            model_version=model_version,
            status=self._status,
            latency_ms=1,
        )


def _context() -> TurnContextV5:
    return TurnContextV5(
        user_id="user:1",
        session_id="session:1",
        active_radar_ref="radar:1",
        active_radar_version=1,
        current_filters=(),
        active_desires=(),
        pending_action=None,
        focused_entity=None,
        verified_listing_refs=(),
        allowed_capabilities=("query",),
        untrusted_content=(),
        context_schema_version="5",
        correlation_id="correlation:1",
    )


def _result(
    *,
    outcomes: tuple[ActOutcomeV5, ...] = (),
    context: TurnContextV5 | None = None,
    plan: TurnPlanV5 | None = None,
    executed: tuple[ExecutedActV5, ...] = (),
    failure_stage: str | None = None,
) -> ConversationTurnResultV5:
    return ConversationTurnResultV5(
        context=context or _context(),
        interpretation=None,
        plan=plan,
        executed=executed,
        outcomes=outcomes,
        failure_stage=cast(Any, failure_stage),
    )


def _composer(gateway: ModelGateway) -> ReplyComposerV5:
    return ReplyComposerV5(
        gateway=gateway,
        schema=REPLY_SCHEMA,
        prompt_version="reply-v5",
        model_version="gpt-4.1-mini",
    )


def test_reply_never_claims_rejected_effect() -> None:
    gateway = _FakeGateway(
        {
            "contract_version": "5",
            "text": "No pude actualizar el filtro.",
            "outcomes": [],
            "verified_refs": [],
            "source": "managed",
        }
    )
    composer = _composer(gateway)

    reply = composer.compose(
        _result(
            outcomes=(
                ActOutcomeV5(
                    "a1", "rejected", reason_code="filter.not_active"
                ),
            )
        )
    )

    assert "actualicé" not in reply.text.casefold()
    assert reply.outcomes[0].status == "rejected"
    assert reply.source == "managed"


def test_provider_failure_uses_deterministic_fallback() -> None:
    gateway = _FakeGateway(reply={}, status="error")
    composer = _composer(gateway)

    reply = composer.compose(_result(failure_stage="provider_failure"))

    assert reply.source == "deterministic_fallback"
    assert reply.outcomes == ()
    assert reply.text


def test_invalid_model_output_falls_back_deterministically() -> None:
    gateway = _FakeGateway(
        {
            "contract_version": "5",
            "text": 123,
            "outcomes": [],
            "verified_refs": [],
            "source": "managed",
        }
    )
    composer = _composer(gateway)

    reply = composer.compose(
        _result(outcomes=(ActOutcomeV5("a1", "applied"),))
    )

    assert reply.source == "deterministic_fallback"
    assert reply.outcomes[0].status == "applied"


def test_verified_refs_only_from_applied_outcomes() -> None:
    gateway = _FakeGateway(
        {
            "contract_version": "5",
            "text": "Listo.",
            "outcomes": [],
            "verified_refs": [],
            "source": "managed",
        }
    )
    composer = _composer(gateway)

    reply = composer.compose(
        _result(
            outcomes=(
                ActOutcomeV5(
                    "a1", "applied", object_ref="radar:1"
                ),
                ActOutcomeV5(
                    "a2", "pending", object_ref="proposal:p"
                ),
            )
        )
    )

    assert reply.verified_refs == ("radar:1",)


def test_fallback_text_reflects_pending_status() -> None:
    composer = _composer(_FakeGateway(reply={}, status="error"))

    reply = composer.compose(
        _result(
            outcomes=(
                ActOutcomeV5(
                    "a1", "pending", reason_code="filter.changes_existing_hard_filter"
                ),
            )
        )
    )

    assert "confirmación" in reply.text.casefold()


def _desire_command(
    *, concept: str, intensity: str
) -> RecordDesireCommand:
    return RecordDesireCommand(
        act_id="a1",
        raw_text="prefiero buen acceso al transporte",
        subject_ref=concept,
        concept_links=(
            ConceptLinkV5(
                concept_ref=concept,
                confidence=0.9,
                polarity="positive",
                intensity=cast(Any, intensity),
            ),
        ),
    )


def _managed_reply(text: str) -> dict[str, object]:
    return {
        "contract_version": "5",
        "text": text,
        "outcomes": [],
        "verified_refs": [],
        "source": "managed",
    }


def test_applied_transport_preference_is_acknowledged_without_question() -> None:
    composer = _composer(_FakeGateway(reply=_managed_reply("Listo.")))
    command = _desire_command(concept="acceso_transporte", intensity="high")

    reply = composer.compose(
        _result(
            plan=TurnPlanV5(decisions=(), commands=(command,)),
            executed=(ExecutedActV5("a1", "desire.remembered"),),
            outcomes=(ActOutcomeV5("a1", "applied"),),
        )
    )

    assert "transporte" in reply.text.casefold()
    assert "alta" in reply.text.casefold()
    assert "?" not in reply.text
    assert reply.source == "deterministic_fallback"


def test_unresolved_desire_is_remembered_without_false_refusal() -> None:
    composer = _composer(
        _FakeGateway(reply=_managed_reply("No puedo ayudarte con eso."))
    )
    command = RecordDesireCommand(
        act_id="a1",
        raw_text="que el edificio tenga buena onda",
        subject_ref="edificio_buena_onda",
    )

    reply = composer.compose(
        _result(
            plan=TurnPlanV5(decisions=(), commands=(command,)),
            executed=(ExecutedActV5("a1", "desire.remembered"),),
            outcomes=(ActOutcomeV5("a1", "applied"),),
        )
    )

    assert "registr" in reply.text.casefold()
    assert "no cambia el orden" in reply.text.casefold()
    assert "no puedo ayudarte" not in reply.text.casefold()
    assert reply.source == "deterministic_fallback"


def test_pending_hard_step_asks_one_question_with_ordinal() -> None:
    composer = _composer(_FakeGateway(reply=_managed_reply("Listo.")))
    context = _context()
    context = replace(
        context,
        pending_action=PendingActionV5("pending:zones", "zones", 1, 2),
    )

    reply = composer.compose(
        _result(
            context=context,
            outcomes=(
                ActOutcomeV5(
                    "zones", "pending", "filter.requires_confirmation"
                ),
            ),
        )
    )

    assert "1 de 2" in reply.text
    assert reply.text.count("?") == 1
    assert reply.source == "deterministic_fallback"


@pytest.mark.parametrize(
    ("status", "reason_code", "expected"),
    [("applied", None, "confirmado"), ("rejected", "user", "rechazado")],
)
def test_resolution_describes_outcome_then_asks_next_hard_step(
    status: str, reason_code: str | None, expected: str
) -> None:
    composer = _composer(_FakeGateway(reply={}, status="error"))
    context = _context()
    context = replace(
        context,
        pending_action=PendingActionV5("pending:budget", "budget", 2, 2),
    )

    reply = composer.compose(
        _result(
            context=context,
            executed=(
                ExecutedActV5(
                    "resolve:zones:1",
                    "pending.resolved",
                    status=cast(Any, status),
                    reason_code=reason_code,
                ),
            ),
            outcomes=(
                ActOutcomeV5("zones", "pending", "filter.requires_confirmation"),
                ActOutcomeV5(
                    "resolve:zones:1",
                    cast(Any, status),
                    reason_code,
                ),
            ),
        )
    )

    assert expected in reply.text.casefold()
    assert "2 de 2" in reply.text
    assert reply.text.count("?") == 1

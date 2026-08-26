"""Scripted and managed model adapters for the v3 eval trial seam.

Both adapters traverse the same topology-v4 graph and differ only at the
model seam. ``ScriptedEvalModelAdapter`` replays the exact per-turn payloads
declared in the case contract; ``ManagedEvalModelAdapter`` pins the release
model and returns a fresh HTTP gateway per trial so attempts never share
response or client state (retry orchestration belongs to the pure runner).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from umbral.application.agent.contracts import ModelResult
from umbral.application.agent.ports import ModelGateway
from umbral.application.agent_evals.v3.contracts import (
    EvalCase,
    EvalRelease,
    Fidelity,
)
from umbral.infrastructure.agent.model_gateway.managed import ManagedModelGateway
from umbral.infrastructure.config.settings import Settings

_REPLY_MARKER = "Efectos de este turno:"


def select_scripted_content(
    case: EvalCase,
    prompt_version: str,
    user_text: str,
    *,
    served_interpretations: set[int],
) -> Mapping[str, object]:
    """Return the declared interpretation or reply payload for the turn whose
    user text matches, raising ``ScriptExhausted`` when nothing matches.

    Called with the interpretation prompt for ``prompt_version`` kinds and
    the reply prompt otherwise; prompts are release version strings, so a
    reply call on a resumed turn still returns the reply declared for the
    matching turn text (the decision turn is the one the graph composes for).
    """
    is_interpretation = prompt_version.lower().startswith("interpretation")
    for index, turn in enumerate(case.turns):
        if turn.user != user_text:
            continue
        if is_interpretation:
            if index in served_interpretations:
                continue
            served_interpretations.add(index)
            return turn.script.interpretation
        return turn.script.reply
    raise ScriptExhausted(user_text)


class ScriptExhausted(ValueError):
    """The scripted adapter was called for an undeclared turn payload."""


class ScriptedEvalModelAdapter:
    """Replays the declared per-turn payloads, failing when scripts run out."""

    fidelity: Fidelity = "scripted"

    def __init__(self, input_tokens: int = 8, output_tokens: int = 16) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.calls: list[dict[str, object]] = []
        self._served_interpretations: set[int] = set()

    def gateway_for(
        self,
        *,
        case: EvalCase,
        release: EvalRelease,
        trial_index: int,
        attempt_index: int,
    ) -> ModelGateway:
        del trial_index, attempt_index
        return _ScriptedCaseGateway(self, case, release)


class _ScriptedCaseGateway:
    def __init__(
        self,
        adapter: ScriptedEvalModelAdapter,
        case: EvalCase,
        release: EvalRelease,
    ) -> None:
        self.adapter = adapter
        self.case = case
        self.release = release

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
        user_text = _user_text(messages)
        self.adapter.calls.append(
            {"prompt_version": prompt_version, "user_text": user_text}
        )
        try:
            content = select_scripted_content(
                self.case,
                prompt_version,
                user_text,
                served_interpretations=self.adapter._served_interpretations,
            )
        except ScriptExhausted as exc:
            return ModelResult(
                content=None,
                model_version=model_version,
                status="error",
                latency_ms=0,
                input_tokens=0,
                output_tokens=0,
                total_tokens=0,
                error_code=f"evals_v3.script_exhausted:{exc.args[0][:80]}",
            )
        return ModelResult(
            content=dict(content),
            model_version=model_version,
            status="success",
            latency_ms=1,
            input_tokens=self.adapter.input_tokens,
            output_tokens=self.adapter.output_tokens,
            total_tokens=self.adapter.input_tokens + self.adapter.output_tokens,
        )


class ManagedEvalModelAdapter:
    """Fresh managed-provider gateway per trial with the release model pinned."""

    fidelity: Fidelity = "managed"

    def __init__(self, *, settings: Settings) -> None:
        if (
            settings.agent_model_provider != "managed"
            or not settings.agent_managed_endpoint
        ):
            raise ValueError(
                "agent_evals_v3.managed_config_required:"
                "AGENT_MODEL_PROVIDER=managed and AGENT_MANAGED_ENDPOINT"
            )
        self.endpoint = settings.agent_managed_endpoint
        self.api_key = settings.agent_managed_api_key or ""
        self.model = settings.agent_model_name
        self.timeout_seconds = settings.agent_model_timeout_seconds

    def gateway_for(
        self,
        *,
        case: EvalCase,
        release: EvalRelease,
        trial_index: int,
        attempt_index: int,
    ) -> ModelGateway:
        del case, release, trial_index, attempt_index
        return cast(
            ModelGateway,
            ManagedModelGateway(
                endpoint=self.endpoint,
                api_key=self.api_key,
                model=self.model,
                timeout_seconds=self.timeout_seconds,
                max_retries=0,
            ),
        )


def _user_text(messages: Sequence[Mapping[str, object]]) -> str:
    for message in messages:
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if not isinstance(content, str) or content.startswith(_REPLY_MARKER):
            continue
        return content
    return ""
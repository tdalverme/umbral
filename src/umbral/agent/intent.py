"""Managed structured interpretation compiler v5 (UM-H4-022, R-01).

The model only fills the structured ``conversation-interpretation`` payload.
This compiler decodes each closed ``oneOf`` branch into its matching typed act,
derives evidence positions from literal model-selected text, requires
authorized refs, and rejects malformed output. It never synthesizes an act.
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path
from typing import Literal, cast

from umbral.application.agent.ports import ModelGateway
from umbral.application.conversation.contracts import (
    ClearFilter,
    ConceptLink,
    ConversationAct,
    CreateRadar,
    EvidenceSpan,
    ExpressDesire,
    FeedbackType,
    FilterKey,
    Query,
    RecordFeedback,
    ResolvePending,
    ReviseDesire,
    SetFilter,
    TurnContext,
    TurnInterpretation,
    UnsupportedRequest,
    WithdrawDesire,
)

logger = logging.getLogger(__name__)

_FILTER_KEYS = ("budget_max", "zones", "min_rooms")
_FEEDBACK_TYPES = ("like", "dislike", "save", "dismiss", "contacted")
_PREFERENCE_POLARITIES = ("positive", "negative")
_PREFERENCE_INTENSITIES = ("low", "medium", "high", "essential")
_PENDING_REJECT = re.compile(
    r"\b(?:rechazo|desapruebo|cancelo|cancelar)\b"
    r"|^\s*no(?:\s*[,!.?]|$)"
    r"|\bno\s+(?:acepto|apruebo|confirmo)\b"
)
_PENDING_APPROVE = re.compile(
    r"\b(?:confirmo|apruebo|acepto)\b"
    r"|^\s*(?:si|ok|dale|yes)(?:\s*[,!.?]|$)"
)


class InterpretationContractFailed(Exception):
    """The model output violates the published V5 interpretation contract."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"interpretation_contract_failed: {reason}")


class InterpretationCompiler:
    """Compiles one message into ordered typed acts over the model gateway."""

    def __init__(
        self,
        *,
        gateway: ModelGateway,
        schema: Mapping[str, object],
        prompt_version: str,
        model_version: str,
        interpretation_version: str = "conversation-interpretation",
        max_acts: int = 6,
        concept_catalog: tuple[Mapping[str, object], ...] = (),
    ) -> None:
        self.gateway = gateway
        self.schema = schema
        self.prompt_version = prompt_version
        self.model_version = model_version
        self.interpretation_version = interpretation_version
        self.max_acts = max_acts
        self.concept_catalog = _catalog_snapshot(concept_catalog)
        self._concept_refs = frozenset(
            _required_string(item, "key") for item in self.concept_catalog
        )

    def interpret(
        self,
        *,
        message_text: str,
        context: TurnContext,
        correlation_id: object | None = None,
    ) -> TurnInterpretation:
        logger.warning(
            "v5.interpret.request phrase=%r active_desires=%d has_pending=%s",
            message_text[:150],
            len(context.active_desires),
            context.pending_action is not None,
        )
        result = self.gateway.generate_structured(
            messages=(
                {
                    "role": "system",
                    "content": _system_message(context, self.concept_catalog),
                },
                {"role": "user", "content": message_text},
            ),
            schema=_schema_with_catalog_refs(self.schema, self._concept_refs),
            schema_version=self.interpretation_version,
            prompt_version=self.prompt_version,
            model_version=self.model_version,
        )
        if result.status != "success" or result.content is None:
            logger.warning(
                "v5.interpret.gateway_failed phrase=%r status=%s error=%s",
                message_text[:120],
                result.status,
                result.error_code,
            )
            raise InterpretationContractFailed(
                result.error_code or "provider_failure"
            )
        try:
            compiled = self._compile(result.content, message_text, context)
        except InterpretationContractFailed as exc:
            logger.warning(
                "v5.interpret.compile_failed phrase=%r reason=%s raw=%s",
                message_text[:120],
                exc.reason,
                str(result.content)[:500],
            )
            raise
        logger.warning(
            "v5.interpret.success phrase=%r acts=%s concept_links=%s",
            message_text[:120],
            [a.kind for a in compiled.acts],
            [
                getattr(a, "concept_links", ())
                for a in compiled.acts
                if hasattr(a, "concept_links")
            ],
        )
        return compiled

    def _compile(
        self,
        data: Mapping[str, object],
        message_text: str,
        context: TurnContext,
    ) -> TurnInterpretation:
        raw_acts = data.get("acts")
        if not isinstance(raw_acts, list):
            raise InterpretationContractFailed("missing acts")
        if len(raw_acts) > self.max_acts:
            raise InterpretationContractFailed("too many acts")
        pending_act = _pending_confirmation_act(message_text, context)
        acts: list[ConversationAct] = []
        seen: set[str] = {pending_act.act_id} if pending_act else set()
        for item in raw_acts:
            if not isinstance(item, Mapping):
                raise InterpretationContractFailed("invalid act shape")
            # Pending confirmation is control flow owned by the runtime. Do not
            # let the model duplicate or override the deterministic decision.
            if pending_act is not None and item.get("kind") == "resolve_pending":
                continue
            act = _compile_act(
                item, message_text, context, allowed_concept_refs=self._concept_refs
            )
            if act.act_id in seen:
                raise InterpretationContractFailed("duplicate act_id")
            seen.add(act.act_id)
            acts.append(act)
        if pending_act is not None:
            acts.insert(0, pending_act)
        if len(acts) > self.max_acts:
            raise InterpretationContractFailed("too many acts")
        return TurnInterpretation(
            model_version=self.model_version,
            prompt_version=self.prompt_version,
            acts=tuple(acts),
        )


def _system_message(
    context: TurnContext, concept_catalog: tuple[dict[str, object], ...]
) -> str:
    prompt = _interpretation_prompt()
    authorized_context = json.dumps(
        _authorized_context(context), ensure_ascii=False, sort_keys=True
    )
    untrusted_content = json.dumps(
        _untrusted_content(context), ensure_ascii=False, sort_keys=True
    )
    return (
        f"{prompt}\n\n"
        "CONCEPT_CATALOG\n"
        f"{json.dumps(concept_catalog, ensure_ascii=False, sort_keys=True)}"
        "\n\nAUTHORIZED_CONTEXT\n"
        f"{authorized_context}"
        "\n\nUNTRUSTED_CONTENT\n"
        f"{untrusted_content}"
    )


def _interpretation_prompt() -> str:
    path = Path(__file__).resolve().parent / "prompts" / "interpretation.md"
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise InterpretationContractFailed(
            "interpretation prompt unavailable"
        ) from error


def _authorized_context(context: TurnContext) -> dict[str, object]:
    data = asdict(context)
    data["untrusted_content"] = []
    return data


def _untrusted_content(context: TurnContext) -> list[dict[str, object]]:
    return [
        {"source": item.source, "text": item.text}
        for item in context.untrusted_content
    ]


def _pending_confirmation_act(
    message_text: str, context: TurnContext
) -> ResolvePending | None:
    pending_action = context.pending_action
    if pending_action is None or not message_text.strip():
        return None
    normalized = _normalize_for_matching(message_text)
    if _PENDING_REJECT.search(normalized):
        decision: Literal["approve", "reject"] = "reject"
    elif _PENDING_APPROVE.search(normalized):
        decision = "approve"
    else:
        return None
    return ResolvePending(
        act_id="pending-resolution",
        confidence=1.0,
        evidence_spans=(
            EvidenceSpan(start=0, end=len(message_text), text=message_text),
        ),
        pending_ref=pending_action.pending_ref,
        decision=decision,
    )


def _normalize_for_matching(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", value.lower())
        if not unicodedata.combining(character)
    )


def _compile_act(
    item: Mapping[str, object], message_text: str, context: TurnContext,
    *, allowed_concept_refs: frozenset[str]
) -> ConversationAct:
    act_id = _required_string(item, "act_id")
    kind = item.get("kind")
    confidence = _confidence(item.get("confidence"))
    spans = _evidence_spans(item.get("evidence_text"), message_text)
    if not spans:
        raise InterpretationContractFailed("act missing evidence")
    if kind == "create_radar":
        return CreateRadar(
            act_id=act_id,
            confidence=confidence,
            evidence_spans=spans,
            name=_optional_string(item, "name"),
        )
    if kind == "set_filter":
        filter_key = _filter_key(item)
        try:
            value = _filter_value(filter_key, item.get("value"))
            return SetFilter(
                act_id=act_id,
                confidence=confidence,
                evidence_spans=spans,
                filter_key=cast(FilterKey, filter_key),
                value=value,
            )
        except ValueError as error:
            raise InterpretationContractFailed(str(error)) from error
    if kind == "clear_filter":
        return ClearFilter(
            act_id=act_id,
            confidence=confidence,
            evidence_spans=spans,
            filter_key=cast(FilterKey, _filter_key(item)),
        )
    if kind == "express_desire":
        concept_links = _concept_links(
            item.get("concept_links"), allowed_concept_refs
        )
        if len(concept_links) > 1:
            raise InterpretationContractFailed(
                "express desire must link one concept"
            )
        return ExpressDesire(
            act_id=act_id,
            confidence=confidence,
            evidence_spans=spans,
            raw_text=_required_string(item, "raw_text"),
            subject_ref=_required_string(item, "subject_ref"),
            concept_links=tuple(
                replace(link, evidence_spans=spans) for link in concept_links
            ),
        )
    if kind == "revise_desire":
        desire_ref = _optional_string(item, "desire_ref")
        if desire_ref is not None:
            _require_authorized(context, desire_ref)
        return ReviseDesire(
            act_id=act_id,
            confidence=confidence,
            evidence_spans=spans,
            desire_ref=desire_ref,
            raw_text=_required_string(item, "raw_text"),
            concept_links=_concept_links(
                item.get("concept_links"), allowed_concept_refs
            ),
        )
    if kind == "withdraw_desire":
        desire_ref = _optional_string(item, "desire_ref")
        if desire_ref is not None:
            _require_authorized(context, desire_ref)
        return WithdrawDesire(
            act_id=act_id,
            confidence=confidence,
            evidence_spans=spans,
            desire_ref=desire_ref,
        )
    if kind == "record_feedback":
        listing_ref = _required_string(item, "listing_ref")
        _require_authorized(context, listing_ref)
        feedback_type = _required_string(item, "feedback_type")
        if feedback_type not in _FEEDBACK_TYPES:
            raise InterpretationContractFailed("unknown feedback_type")
        return RecordFeedback(
            act_id=act_id,
            confidence=confidence,
            evidence_spans=spans,
            listing_ref=listing_ref,
            feedback_type=cast(FeedbackType, feedback_type),
            raw_text=_optional_string(item, "raw_text"),
        )
    if kind == "query":
        return Query(
            act_id=act_id,
            confidence=confidence,
            evidence_spans=spans,
            query_text=_required_string(item, "query_text"),
        )
    if kind == "unsupported_request":
        return UnsupportedRequest(
            act_id=act_id,
            confidence=confidence,
            evidence_spans=spans,
            request_text=_required_string(item, "request_text"),
        )
    raise InterpretationContractFailed(f"unknown kind: {kind}")


def _filter_key(item: Mapping[str, object]) -> str:
    key = _required_string(item, "filter_key")
    if key not in _FILTER_KEYS:
        raise InterpretationContractFailed("filter key is not published")
    return key


def _filter_value(filter_key: str, value: object) -> float | int | tuple[str, ...]:
    if filter_key == "zones":
        if not isinstance(value, list) or not all(
            isinstance(zone, str) and zone for zone in value
        ):
            raise InterpretationContractFailed("zones must be a list of strings")
        return tuple(value)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InterpretationContractFailed("filter value must be numeric")
    return value


def _concept_links(
    value: object, allowed_concept_refs: frozenset[str]
) -> tuple[ConceptLink, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise InterpretationContractFailed("concept_links must be a list")
    links: list[ConceptLink] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise InterpretationContractFailed("invalid concept link shape")
        concept_ref = _required_string(item, "concept_ref")
        if concept_ref not in allowed_concept_refs:
            raise InterpretationContractFailed("concept ref is not published")
        polarity = _required_string(item, "polarity")
        if polarity not in _PREFERENCE_POLARITIES:
            raise InterpretationContractFailed("unknown concept link polarity")
        intensity = _required_string(item, "intensity")
        if intensity not in _PREFERENCE_INTENSITIES:
            raise InterpretationContractFailed("unknown concept link intensity")
        force = item.get("force", "soft")
        if force != "soft":
            raise InterpretationContractFailed("concept links must be soft")
        links.append(
            ConceptLink(
                concept_ref=concept_ref,
                confidence=_confidence(item.get("confidence")),
                polarity=cast(Literal["positive", "negative"], polarity),
                intensity=cast(
                    Literal["low", "medium", "high", "essential"], intensity
                ),
                force="soft",
            )
        )
    return tuple(links)


def _catalog_snapshot(
    catalog: tuple[Mapping[str, object], ...]
) -> tuple[dict[str, object], ...]:
    snapshot: list[dict[str, object]] = []
    keys: set[str] = set()
    for item in catalog:
        key = _required_string(item, "key")
        if key in keys:
            raise InterpretationContractFailed("duplicate catalog key")
        keys.add(key)
        snapshot.append(
            {
                "key": key,
                "description": _required_string(item, "description"),
                "matcher_type": _required_string(item, "matcher_type"),
                "computable": bool(item.get("computable")),
                "aliases": _catalog_aliases(item.get("aliases")),
            }
        )
    return tuple(snapshot)


def _catalog_aliases(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)) or not all(
        isinstance(alias, str) and alias for alias in value
    ):
        raise InterpretationContractFailed("catalog aliases invalid")
    return list(value)


def _schema_with_catalog_refs(
    schema: Mapping[str, object], concept_refs: frozenset[str]
) -> dict[str, object]:
    """Publish the snapshot as an enum when the supplied JSON schema supports it."""
    copied = deepcopy(dict(schema))
    defs = copied.get("$defs")
    if not isinstance(defs, dict):
        return copied
    concept_link = defs.get("concept_link")
    if not isinstance(concept_link, dict):
        return copied
    properties = concept_link.get("properties")
    if not isinstance(properties, dict):
        return copied
    concept_ref = properties.get("concept_ref")
    if not isinstance(concept_ref, dict):
        return copied
    concept_ref["enum"] = sorted(concept_refs)
    return copied


def _evidence_spans(value: object, message_text: str) -> tuple[EvidenceSpan, ...]:
    if not isinstance(value, str) or not value:
        raise InterpretationContractFailed("evidence_text required")
    start = message_text.find(value)
    if start < 0:
        raise InterpretationContractFailed("evidence text not found in message")
    if message_text.find(value, start + 1) >= 0:
        raise InterpretationContractFailed("evidence text is ambiguous")
    return (EvidenceSpan(start=start, end=start + len(value), text=value),)


def _require_authorized(context: TurnContext, ref: str) -> None:
    if not context.authorizes(ref):
        raise InterpretationContractFailed(f"ref not authorized: {ref}")


def _required_string(mapping: Mapping[str, object], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise InterpretationContractFailed(f"{key} required")
    return value


def _optional_string(mapping: Mapping[str, object], key: str) -> str | None:
    value = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise InterpretationContractFailed(f"{key} must be a string")
    return value


def _confidence(value: object) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return max(0.0, min(1.0, float(value)))
    raise InterpretationContractFailed("confidence required")

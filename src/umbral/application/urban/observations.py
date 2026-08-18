"""Extract ListingObservations from computed urban signals."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

from umbral.application.criteria.contracts import ListingObservation


@dataclass(frozen=True, slots=True)
class UrbanSignalObservationInput:
    concept_key: str
    signal_ref: str
    value: object
    score: float
    confidence: float
    missing: bool
    contributors: Sequence[Mapping[str, object]]
    extraction_version_id: UUID
    created_at: datetime
    correlation_id: UUID


def build_observation(
    *,
    listing_id: UUID,
    input_: UrbanSignalObservationInput,
    contract_version_id: UUID,
    snapshot_id: UUID,
) -> ListingObservation:
    """Build a ListingObservation for a concept with a signal ref.

    The score and confidence flow from the normalized urban signal; the
    evidence cites the contributors and both the contract and snapshot for
    lineage.
    """
    return ListingObservation(
        observation_id=uuid4(),
        listing_id=listing_id,
        concept_key=input_.concept_key,
        matcher_type="signal_score",
        value=input_.value,
        score=input_.score,
        confidence=input_.confidence if not input_.missing else 0.0,
        evidence={
            "signal_ref": input_.signal_ref,
            "contributors": [dict(item) for item in input_.contributors],
            "contract_version_id": str(contract_version_id),
            "snapshot_id": str(snapshot_id),
        },
        source="urban",
        extraction_version_id=input_.extraction_version_id,
        state="failed" if input_.missing else "active",
        failure_code="criteria.urban_unavailable" if input_.missing else None,
        recomputation_run_id=None,
        created_at=input_.created_at,
        correlation_id=input_.correlation_id,
        actor_kind="service",
        actor_id=None,
    )


def observations_for_signal(
    *,
    listing_id: UUID,
    signals: Sequence[Mapping[str, object]],
    concepts: Mapping[str, str],
    contract_version_id: UUID,
    extraction_version_id: UUID,
    snapshot_id: UUID,
    created_at: datetime,
    correlation_id: UUID,
) -> tuple[ListingObservation, ...]:
    """Build observations for every concept that references an available signal.

    ``concepts`` maps concept_key -> signal_ref. Only signals that exist in the
    computed set produce observations; concepts whose signal is missing keep an
    explicit unknown observation.
    """
    by_signal: dict[str, Mapping[str, object]] = {
        cast(str, signal["signal"]): signal for signal in signals
    }
    observations: list[ListingObservation] = []
    for concept_key, signal_ref in concepts.items():
        signal = by_signal.get(signal_ref)
        if signal is None:
            observations.append(
                build_observation(
                    listing_id=listing_id,
                    input_=UrbanSignalObservationInput(
                        concept_key=concept_key,
                        signal_ref=signal_ref,
                        value=None,
                        score=0.0,
                        confidence=0.0,
                        missing=True,
                        contributors=[],
                        extraction_version_id=extraction_version_id,
                        created_at=created_at,
                        correlation_id=correlation_id,
                    ),
                    contract_version_id=contract_version_id,
                    snapshot_id=snapshot_id,
                )
            )
            continue
        missing = bool(signal.get("missing", False))
        observations.append(
            build_observation(
                listing_id=listing_id,
                input_=UrbanSignalObservationInput(
                    concept_key=concept_key,
                    signal_ref=signal_ref,
                    value=None if missing else signal.get(
                        "normalized_value", signal.get("value")
                    ),
                    score=0.0 if missing else _signal_score(signal),
                    confidence=_signal_confidence(signal),
                    missing=missing,
                    contributors=[dict(item) for item in _signal_contributors(signal)],
                    extraction_version_id=extraction_version_id,
                    created_at=created_at,
                    correlation_id=correlation_id,
                ),
                contract_version_id=contract_version_id,
                snapshot_id=snapshot_id,
            )
        )
    return tuple(observations)


def _signal_score(signal: Mapping[str, object]) -> float:
    raw = signal.get("normalized_value", signal.get("value"))
    if isinstance(raw, bool):
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    return 0.0


def _signal_confidence(signal: Mapping[str, object]) -> float:
    raw = signal.get("confidence")
    if isinstance(raw, bool):
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    return 0.0


def _signal_contributors(
    signal: Mapping[str, object],
) -> Sequence[Mapping[str, object]]:
    raw = signal.get("contributors")
    if isinstance(raw, list) and all(isinstance(item, Mapping) for item in raw):
        return [dict(item) for item in raw]
    return []

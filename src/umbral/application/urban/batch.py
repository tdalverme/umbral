"""Batch orchestration: primitives -> raw signals -> stats -> normalized signals.

The batch service is a pure orchestration layer over the application ports; it
performs no I/O itself and is fully testable against fakes. It computes raw
signals for every listing with precise coordinates, derives per-barrio stats,
normalizes with a stable caba fallback, persists signals for the active
contract, and produces the urban ListingObservations for signal_ref concepts.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import cast
from uuid import UUID

from umbral.application.urban.calculator import UrbanSignalCalculator, UrbanSignalResult
from umbral.application.urban.contract import SignalSpec, UrbanContract
from umbral.application.urban.normalization import (
    BarrioStat,
    apply_confidence_penalty,
    compute_barrio_stats,
    normalize,
)
from umbral.application.urban.observations import observations_for_signal
from umbral.application.urban.ports import (
    DistanceCalculator,
    ListingsCoordinatesReader,
    NeighborhoodStatsRepository,
    UrbanContractRepository,
    UrbanPrimitiveRepository,
    UrbanSignalRepositoryPort,
    UrbanSnapshotRepository,
)
from umbral.application.urban.primitives import buckets_to_primitives

_FALLBACK_BARRIO = "__caba__"


@dataclass(frozen=True, slots=True)
class UrbanBatchOutcome:
    listings_processed: int
    primitive_rows: int
    signal_rows: int
    stats_rows: int
    observations: tuple[object, ...]

    @property
    def observation_count(self) -> int:
        return len(self.observations)


@dataclass(frozen=True, slots=True)
class _EffectiveSignal:
    """Final stored representation of one normalized signal for a listing."""

    raw: float
    normalized_value: float
    normalization_scope: str
    confidence: float
    missing: bool
    contributors: tuple[Mapping[str, object], ...]


class UrbanBatchService:
    """Execute the full urban signals batch for the active contract/snapshot."""

    def __init__(
        self,
        *,
        contract: UrbanContract,
        distances: DistanceCalculator,
        primitives: UrbanPrimitiveRepository,
        signals: UrbanSignalRepositoryPort,
        stats: NeighborhoodStatsRepository,
        contracts: UrbanContractRepository,
        snapshots: UrbanSnapshotRepository,
        listings: ListingsCoordinatesReader,
        extraction_version_id: UUID,
        concepts: Mapping[str, str],
        created_at: datetime | None = None,
    ) -> None:
        self.contract = contract
        self.calculator = UrbanSignalCalculator(contract)
        self.distances = distances
        self.primitives = primitives
        self.signals = signals
        self.stats = stats
        self.contracts = contracts
        self.snapshots = snapshots
        self.listings = listings
        self.extraction_version_id = extraction_version_id
        self.concepts = concepts
        self.created_at = created_at or datetime.utcnow()

    def run(self, *, correlation_id: UUID) -> UrbanBatchOutcome:
        active_contract = self.contracts.active()
        if active_contract is None:
            raise RuntimeError("urban_contract_missing")
        contract_version_id = cast(UUID, getattr(active_contract, "id"))
        snapshot = self.snapshots.active()
        if snapshot is None:
            raise RuntimeError("urban_snapshot_missing")
        snapshot_id = cast(UUID, getattr(snapshot, "id"))

        listing_ids = self.listings.listing_ids_with_precise_coordinates()
        raw_by_listing: dict[UUID, UrbanSignalResult] = {}
        barrio_values: dict[tuple[str, str], list[float]] = {}
        primitive_count = 0

        for listing_id in listing_ids:
            buckets = self.distances.for_listing(
                listing_id, snapshot_id, radius_m=self.contract.distance_radius_m
            )
            primitive_rows = buckets_to_primitives(
                listing_id=listing_id,
                snapshot_id=snapshot_id,
                buckets=buckets,
                contract=self.contract,
            )
            if primitive_rows:
                self.primitives.upsert_many(
                    primitive_rows, correlation_id=correlation_id
                )
                primitive_count += len(primitive_rows)
            result = self.calculator.calculate(
                poi_distances=buckets,
                linear_distances=buckets,
            )
            raw_by_listing[listing_id] = result
            barrio = self.listings.neighborhood_of(listing_id) or _FALLBACK_BARRIO
            for name, value in result.signals.items():
                if value.missing:
                    continue
                key = (barrio, name)
                barrio_values.setdefault(key, []).append(value.value)

        stats_rows, caba_values = self._compute_stats(barrio_values)
        effective: dict[UUID, dict[str, _EffectiveSignal]] = {}
        for listing_id, result in raw_by_listing.items():
            barrio = self.listings.neighborhood_of(listing_id) or _FALLBACK_BARRIO
            per_listing: dict[str, _EffectiveSignal] = {}
            for name in self._all_signal_names():
                signal_value = result.for_signal(name)
                if signal_value is None:
                    continue
                per_listing[name] = self._effective_signal(
                    name=name,
                    value=signal_value,
                    barrio=barrio,
                    barrio_values=barrio_values,
                    caba_values=caba_values,
                )
            effective[listing_id] = per_listing

        signal_rows: list[Mapping[str, object]] = []
        for listing_id, per_listing in effective.items():
            for name, signal in per_listing.items():
                signal_rows.append(
                    {
                        "listing_id": listing_id,
                        "snapshot_id": snapshot_id,
                        "signal": name,
                        "value": signal.raw,
                        "normalized_value": signal.normalized_value,
                        "normalization_scope": signal.normalization_scope,
                        "confidence": signal.confidence,
                        "missing": signal.missing,
                        "contributors": [dict(item) for item in signal.contributors],
                        "correlation_id": correlation_id,
                    }
                )
        self.signals.replace_for_snapshot_contract(
            snapshot_id, contract_version_id, signal_rows
        )
        self.stats.replace_for_snapshot(snapshot_id, stats_rows)

        observations = self._build_observations(
            listing_ids=listing_ids,
            effective=effective,
            contract_version_id=contract_version_id,
            snapshot_id=snapshot_id,
            correlation_id=correlation_id,
        )

        return UrbanBatchOutcome(
            listings_processed=len(listing_ids),
            primitive_rows=primitive_count,
            signal_rows=len(signal_rows),
            stats_rows=len(stats_rows),
            observations=observations,
        )

    def _effective_signal(
        self,
        *,
        name: str,
        value: object,
        barrio: str,
        barrio_values: Mapping[tuple[str, str], list[float]],
        caba_values: Mapping[str, list[float]],
    ) -> _EffectiveSignal:
        raw = float(getattr(value, "value"))
        confidence = float(getattr(value, "confidence"))
        missing = bool(getattr(value, "missing"))
        contributors = tuple(dict(i) for i in getattr(value, "contributors"))
        spec = self._signal_spec(name)
        normalized_by = spec.normalized_by if spec else "barrio"
        caba = list(caba_values.get(name) or [])
        if normalized_by == "absolute":
            normalized = normalize(raw_value=raw, signal_values=caba, scope="caba")
            final_confidence = confidence
        else:
            if barrio == _FALLBACK_BARRIO:
                scope, ref = "caba", caba
                final_confidence = apply_confidence_penalty(
                    confidence, self.contract.normalization.confidence_penalty
                )
            else:
                barrio_ref = list(barrio_values.get((barrio, name)) or [])
                if len(barrio_ref) < self.contract.normalization.min_sample_per_barrio:
                    scope, ref = (
                        self.contract.normalization.fallback_scope,
                        caba,
                    )
                    final_confidence = apply_confidence_penalty(
                        confidence, self.contract.normalization.confidence_penalty
                    )
                else:
                    scope, ref = "barrio", barrio_ref
                    final_confidence = confidence
            normalized = normalize(raw_value=raw, signal_values=ref, scope=scope)
        return _EffectiveSignal(
            raw=raw,
            normalized_value=normalized.normalized_value,
            normalization_scope=normalized.normalization_scope,
            confidence=final_confidence,
            missing=missing,
            contributors=contributors,
        )

    def _compute_stats(
        self, barrio_values: Mapping[tuple[str, str], list[float]]
    ) -> tuple[list[Mapping[str, object]], dict[str, list[float]]]:
        caba_values: dict[str, list[float]] = {}
        for (_, signal), values in barrio_values.items():
            caba_values.setdefault(signal, []).extend(values)
        rows: list[Mapping[str, object]] = []
        seen: set[tuple[str, str]] = set()
        for (barrio, signal), values in barrio_values.items():
            if barrio == _FALLBACK_BARRIO or (barrio, signal) in seen:
                continue
            seen.add((barrio, signal))
            stat = compute_barrio_stats(
                barrio=barrio,
                signal=signal,
                values=values,
                spec=self.contract.normalization,
            )
            rows.append(_stat_row(stat))
        for signal in self._all_signal_names():
            values = caba_values.get(signal) or []
            if not values:
                continue
            rows.append(
                _stat_row(
                    BarrioStat(
                        barrio=_FALLBACK_BARRIO,
                        signal=signal,
                        sample_size=len(values),
                        normalization_scope=self.contract.normalization.fallback_scope,
                        p50=0.5,
                        p75=0.5,
                        p90=0.5,
                    )
                )
            )
        return rows, caba_values

    def _build_observations(
        self,
        *,
        listing_ids: Sequence[UUID],
        effective: Mapping[UUID, Mapping[str, _EffectiveSignal]],
        contract_version_id: UUID,
        snapshot_id: UUID,
        correlation_id: UUID,
    ) -> tuple[object, ...]:
        observations: list[object] = []
        for listing_id in listing_ids:
            per_listing = effective[listing_id]
            signal_dicts: list[Mapping[str, object]] = [
                {
                    "signal": name,
                    "value": signal.raw,
                    "normalized_value": signal.normalized_value,
                    "normalization_scope": signal.normalization_scope,
                    "confidence": signal.confidence,
                    "missing": signal.missing,
                    "contributors": [dict(i) for i in signal.contributors],
                }
                for name, signal in per_listing.items()
            ]
            built = observations_for_signal(
                listing_id=listing_id,
                signals=signal_dicts,
                concepts=self.concepts,
                contract_version_id=contract_version_id,
                extraction_version_id=self.extraction_version_id,
                snapshot_id=snapshot_id,
                created_at=self.created_at,
                correlation_id=correlation_id,
            )
            observations.extend(built)
        return tuple(observations)

    def _all_signal_names(self) -> tuple[str, ...]:
        return tuple(
            {signal.name for signal in self.contract.signals}
            | {composite.name for composite in self.contract.composite_signals}
        )

    def _signal_spec(self, name: str) -> SignalSpec | None:
        return self.contract.signal_by_name(name)


def _stat_row(stat: BarrioStat) -> Mapping[str, object]:
    return {
        "barrio": stat.barrio,
        "signal": stat.signal,
        "sample_size": stat.sample_size,
        "normalization_scope": stat.normalization_scope,
        "p50": stat.p50,
        "p75": stat.p75,
        "p90": stat.p90,
    }

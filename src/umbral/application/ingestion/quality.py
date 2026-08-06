"""Deterministic quality summary derived from committed rows."""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from uuid import UUID

from umbral.application.ingestion.contracts import (
    AbnormalDistribution,
    QualityReport,
    RunCounts,
)
from umbral.application.ingestion.import_contract import (
    ContractSpec,
    count_missing_by_name,
)

_NUMERIC_FIELDS = ("price", "surface_m2", "rooms")


def build_quality_report(
    *,
    run_id: UUID,
    counts: RunCounts,
    snapshot_payloads: Sequence[Mapping[str, object]],
    contract: ContractSpec,
) -> QualityReport:
    missing_by_name = dict(count_missing_by_name(list(snapshot_payloads), contract))
    abnormal = _detect_abnormal(snapshot_payloads)
    return QualityReport(
        run_id=run_id,
        counts=counts,
        missing_fields_by_name=missing_by_name,
        abnormal_distributions=abnormal,
    )


def _detect_abnormal(
    payloads: Sequence[Mapping[str, object]],
) -> tuple[AbnormalDistribution, ...]:
    signals: list[AbnormalDistribution] = []
    for field in _NUMERIC_FIELDS:
        values: list[float] = []
        for payload in payloads:
            value = _as_float(payload.get(field))
            if value is not None:
                values.append(value)
        if len(values) < 5:
            continue
        try:
            lower, upper = _iqr_bounds(values)
        except statistics.StatisticsError:
            continue
        outliers = [value for value in values if value < lower or value > upper]
        if outliers:
            signals.append(
                AbnormalDistribution(
                    field=field,
                    signal="outlier",
                    detail=f"{len(outliers)} values outside the IQR bounds",
                )
            )
    return tuple(signals)


def _iqr_bounds(values: list[float]) -> tuple[float, float]:
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    lower_half = ordered[:midpoint]
    upper_half = (
        ordered[midpoint:] if len(ordered) % 2 == 0 else ordered[midpoint + 1 :]
    )
    q1 = statistics.median(lower_half)
    q3 = statistics.median(upper_half)
    iqr = q3 - q1
    return q1 - 1.5 * iqr, q3 + 1.5 * iqr


def _as_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None

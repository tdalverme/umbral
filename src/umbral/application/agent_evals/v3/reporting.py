"""Deterministic JSON and Markdown rendering of a v3 comparison report.

The renderer is a pure projection of the structured report: it never
re-ranks cases or inspects model prose. Only the review queue's cases get
detailed traces; every other case is summarized by family/suite/risk.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

from umbral.application.agent_evals.v3.contracts import (
    CaseAggregate,
    CaseDelta,
    ComparisonReport,
    ReviewItem,
    SuiteRun,
    TrialResult,
)

_REDACTED_KEYS = frozenset(
    {
        "api_key",
        "authorization",
        "access_token",
        "refresh_token",
        "secret",
        "cookie",
        "password",
    }
)


def report_to_dict(report: ComparisonReport) -> dict[str, object]:
    """Deterministic JSON-safe projection with rounding and redaction."""
    candidate = report.candidate
    baseline = report.baseline
    summary = _summary_buckets(report)
    payload: dict[str, object] = {
        "verdict": {
            "approvable": report.approvable,
            "blocked": report.blocked,
            "reasons": list(report.reasons),
            "compatible": True,
        },
        "baseline": {
            "release_id": baseline.release_id,
            "fidelity": baseline.fidelity,
            "complete": baseline.complete,
            "include_holdout": baseline.include_holdout,
            "cases": len(baseline.case_aggregates),
            "trials": len(baseline.trial_results),
            "total_cost_usd": _currency(baseline.total_cost_usd),
            "total_latency_ms": int(baseline.total_latency_ms),
            "failures": list(baseline.failures),
        },
        "candidate": {
            "release_id": candidate.release_id,
            "fidelity": candidate.fidelity,
            "complete": candidate.complete,
            "include_holdout": candidate.include_holdout,
            "cases": len(candidate.case_aggregates),
            "trials": len(candidate.trial_results),
            "total_cost_usd": _currency(candidate.total_cost_usd),
            "total_latency_ms": int(candidate.total_latency_ms),
            "failures": list(candidate.failures),
        },
        "deltas": [_delta_dict(delta) for delta in report.deltas],
        "review_items": [_review_item_dict(item) for item in report.review_items],
        "summaries": {
            "family": summary["family"],
            "suite": summary["suite"],
            "risk": summary["risk"],
            "overall": summary["overall"],
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return cast(dict[str, object], _redact(payload))


def render_markdown(report: ComparisonReport) -> str:
    """Markdown report; detailed traces only for the bounded review queue."""
    verdict = (
        "APPROVABLE"
        if report.approvable
        else "BLOCKED"
        if report.blocked
        else "NOT APPROVABLE"
    )
    lines = [
        f"# Agent Evals v3 — {verdict}",
        "",
        f"- Baseline: `{report.baseline.release_id}` "
        f"({_fidelity_label(report.baseline.fidelity)}, "
        f"{len(report.baseline.case_aggregates)} cases)"
        f"{_incomplete_suffix(report.baseline)}",
        f"- Candidate: `{report.candidate.release_id}` "
        f"({_fidelity_label(report.candidate.fidelity)}, "
        f"{len(report.candidate.case_aggregates)} cases)"
        f"{_incomplete_suffix(report.candidate)}",
        f"- Reasons: {', '.join(report.reasons) or 'none'}",
        "",
    ]
    lines.append("## Review queue")
    lines.append("")
    if not report.review_items:
        lines.append("No case requires owner review.")
        lines.append("")
    for item in report.review_items:
        lines.append(f"### {item.case_id} ({item.reason})")
        lines.append("")
        for result in _detailed_trials(report.candidate, item):
            lines.extend(_trial_lines(result))
            lines.append("")
    lines.append("## Summaries by family / suite / risk")
    lines.append("")
    buckets = _summary_buckets(report)
    family_buckets = cast(dict[str, dict[str, object]], buckets["family"])
    for label, entries in family_buckets.items():
        lines.append(f"- family `{label}`: {entries}")
    lines.append("")
    return "\n".join(lines)


def write_evidence(report: ComparisonReport, output_dir: Path) -> EvidencePaths:
    """Atomically publish `<candidate>-vs-<baseline>-<timestamp>/` contents."""
    name = (
        f"{report.candidate.release_id}-vs-{report.baseline.release_id}-"
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    )
    final_dir = Path(output_dir) / name
    temp_dir = Path(output_dir) / f".{name}.tmp"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)
    json_path = temp_dir / "report.json"
    md_path = temp_dir / "report.md"
    try:
        json_path.write_text(
            json.dumps(report_to_dict(report), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        md_path.write_text(render_markdown(report), encoding="utf-8")
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    if final_dir.exists():
        shutil.rmtree(final_dir)
    os.rename(temp_dir, final_dir)
    return EvidencePaths(
        final_dir=final_dir,
        json_path=final_dir / "report.json",
        md_path=final_dir / "report.md",
    )


@dataclass(frozen=True)
class EvidencePaths:
    """Published run-directory paths (JSON + Markdown)."""

    final_dir: Path
    json_path: Path
    md_path: Path


def _delta_dict(delta: CaseDelta) -> dict[str, object]:
    return {
        "case_id": delta.case_id,
        "baseline": {
            "successes": delta.baseline_successes,
            "trials": delta.baseline_trials,
        },
        "candidate": {
            "successes": delta.candidate_successes,
            "trials": delta.candidate_trials,
        },
        "success_rate_delta": _rate(delta.success_rate_delta),
        "consistency_changed": delta.consistency_changed,
        "cost_delta_usd": _currency(delta.cost_delta_usd),
        "latency_delta_ms": int(delta.latency_delta_ms),
        "regressed": delta.regressed,
    }


def _review_item_dict(item: ReviewItem) -> dict[str, object]:
    return {
        "case_id": item.case_id,
        "reason": item.reason,
        "trial_indexes": list(item.trial_indexes),
    }


def _summary_buckets(report: ComparisonReport) -> dict[str, object]:
    aggregates = report.candidate.case_aggregates
    family: dict[str, tuple[int, int, int]] = {}
    suite: dict[str, tuple[int, int, int]] = {}
    risk: dict[str, tuple[int, int, int]] = {}
    for aggregate in aggregates:
        _accumulate(family, aggregate.family, aggregate)
        _accumulate(suite, aggregate.suite, aggregate)
        _accumulate(risk, aggregate.risk, aggregate)
    total_cases = len(aggregates)
    total_trials = sum(aggregate.trials for aggregate in aggregates)
    total_successes = sum(aggregate.successes for aggregate in aggregates)

    def rendered(
        dimension: dict[str, tuple[int, int, int]],
    ) -> dict[str, dict[str, object]]:
        return {
            key: _bucket_dict(cases, trials, successes)
            for key, (cases, trials, successes) in sorted(dimension.items())
        }

    return {
        "family": rendered(family),
        "suite": rendered(suite),
        "risk": rendered(risk),
        "overall": _bucket_dict(total_cases, total_trials, total_successes),
    }


def _accumulate(
    dimension: dict[str, tuple[int, int, int]],
    key: str,
    aggregate: CaseAggregate,
) -> None:
    cases, trials, successes = dimension.get(key, (0, 0, 0))
    dimension[key] = (
        cases + 1,
        trials + aggregate.trials,
        successes + aggregate.successes,
    )


def _bucket_dict(cases: int, trials: int, successes: int) -> dict[str, object]:
    return {
        "cases": cases,
        "trials": trials,
        "successes": successes,
        "success_rate": _rate(successes / trials if trials else 0.0),
    }


def _detailed_trials(candidate: SuiteRun, item: ReviewItem) -> list[TrialResult]:
    return [
        result
        for result in candidate.trial_results
        if result.case_id == item.case_id
    ]


def _trial_lines(result: TrialResult) -> list[str]:
    trace = result.trace
    effects = [
        f"{effect.effect_key}:{effect.status}"
        for turn in trace.turns
        for effect in turn.effects
    ]
    node_names = ", ".join(
        name for turn in trace.turns for name in turn.node_names
    )
    return [
        f"- trial {result.trial_index} attempt {result.attempt_index}: "
        f"{result.failure_kind or 'success'} "
        f"(safety_ok={result.safety_ok}, quality_ok={result.quality_ok})",
        f"  - outcome(s): {', '.join(turn.outcome for turn in trace.turns)}",
        f"  - effects: {', '.join(effects) or 'none'}",
        f"  - nodes: {node_names or 'none'}",
        f"  - cost: {_currency(result.cost_usd)} USD; "
        f"latency: {trace.latency_ms} ms",
    ]


def _incomplete_suffix(run: SuiteRun) -> str:
    if run.complete:
        return ""
    return " — INCOMPLETE"


def _fidelity_label(fidelity: str) -> str:
    return "scripted" if fidelity == "scripted" else "managed"


def _currency(value: float) -> float:
    return round(value, 4)


def _rate(value: float) -> float:
    return round(value, 3)


def _redact(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            key: _redact_entry(value, key)
            for key in value
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _redact_entry(value: Mapping[object, object], key: object) -> object:
    if isinstance(key, str) and key.casefold() in _REDACTED_KEYS:
        return "[REDACTED]"
    return _redact(value[key])
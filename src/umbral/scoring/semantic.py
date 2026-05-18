"""Semantic similarity calibration for candidate pools."""

from __future__ import annotations

import statistics
from dataclasses import dataclass


def _clamp(value: float, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, int(round(value))))


def _absolute_similarity_score(similarity: float) -> int:
    """Map raw cosine similarity to a conservative absolute score."""

    if similarity <= 0.0:
        return 40
    if similarity < 0.35:
        return _clamp(45 + (similarity / 0.35) * 15)
    if similarity < 0.55:
        return _clamp(60 + ((similarity - 0.35) / 0.20) * 12)
    if similarity < 0.75:
        return _clamp(72 + ((similarity - 0.55) / 0.20) * 16)
    return _clamp(88 + min(1.0, (similarity - 0.75) / 0.20) * 8)


@dataclass(frozen=True)
class SemanticCalibrator:
    """Convert raw semantic similarities into calibrated scoring criteria."""

    min_candidates: int = 25
    flat_std_threshold: float = 0.015
    low_pool_max_similarity: float = 0.35
    low_pool_score_cap: int = 74

    def calibrate(self, similarities: dict[str, float]) -> dict[str, dict]:
        clean = {
            key: float(value)
            for key, value in similarities.items()
            if value is not None
        }
        if not clean:
            return {}

        values = list(clean.values())
        candidate_count = len(values)
        if candidate_count < self.min_candidates:
            return {
                key: self._entry(
                    score=_absolute_similarity_score(value),
                    raw_similarity=value,
                    candidate_count=candidate_count,
                    calibration="small_pool_absolute_v1",
                )
                for key, value in clean.items()
            }

        if len(values) > 1 and statistics.pstdev(values) <= self.flat_std_threshold:
            mean = statistics.fmean(values)
            return {
                key: self._entry(
                    score=_clamp(_absolute_similarity_score(mean)),
                    raw_similarity=value,
                    candidate_count=candidate_count,
                    calibration="flat_distribution_v1",
                    extra={"distribution_std": round(statistics.pstdev(values), 6)},
                )
                for key, value in clean.items()
            }

        sorted_values = sorted(values)
        max_similarity = sorted_values[-1]
        calibrated: dict[str, dict] = {}
        for key, value in clean.items():
            percentile = self._percentile(value, sorted_values)
            percentile_score = 45 + percentile * 50
            absolute_score = _absolute_similarity_score(value)
            score = _clamp(0.70 * percentile_score + 0.30 * absolute_score)
            if max_similarity < self.low_pool_max_similarity:
                score = min(score, self.low_pool_score_cap)
            calibrated[key] = self._entry(
                score=score,
                raw_similarity=value,
                candidate_count=candidate_count,
                calibration="pool_percentile_v1",
                extra={
                    "percentile": round(percentile, 4),
                    "absolute_score": absolute_score,
                    "max_similarity": round(max_similarity, 6),
                },
            )
        return calibrated

    def _entry(
        self,
        *,
        score: int,
        raw_similarity: float,
        candidate_count: int,
        calibration: str,
        extra: dict | None = None,
    ) -> dict:
        metadata = {
            "raw_similarity": round(raw_similarity, 6),
            "candidate_count": candidate_count,
            "calibration": calibration,
        }
        if extra:
            metadata.update(extra)
        return {"score": _clamp(score), "metadata": metadata}

    @staticmethod
    def _percentile(value: float, sorted_values: list[float]) -> float:
        if len(sorted_values) <= 1:
            return 1.0
        less_or_equal = sum(1 for item in sorted_values if item <= value)
        return (less_or_equal - 1) / (len(sorted_values) - 1)

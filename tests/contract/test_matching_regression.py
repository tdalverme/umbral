"""Conformance of the regression runner against the published golden dataset.

End-to-end: the published dataset declares ``scoring-policy-v1`` as its
baseline. Running the runner with that same policy as both baseline and
candidate must produce zero order changes (the reviewed order is stable) and a
passing gate.
"""

from __future__ import annotations

from pathlib import Path

from umbral.application.matching.golden import load_golden_dataset
from umbral.application.matching.regression import run_regression
from umbral.application.matching.releases import parse_releases
from umbral.application.scoring.policy import parse_policy_document
from umbral.infrastructure.criteria.contract_loader import load_matcher_types
from umbral.infrastructure.scoring.contract_loader import load_scoring_policy_seed

ROOT = Path(__file__).resolve().parents[2]
GOLDEN_PATH = ROOT / "contracts" / "matching" / "v1" / "golden-dataset-v1.json"
RELEASES_PATH = ROOT / "contracts" / "matching" / "v1" / "releases-v1.json"


def _published_policy() -> object:
    return parse_policy_document(load_scoring_policy_seed(), load_matcher_types())


def test_published_dataset_is_stable_under_its_baseline_policy() -> None:
    dataset = load_golden_dataset(GOLDEN_PATH)
    policy = _published_policy()
    releases = parse_releases(
        {
            "contract_version": "1",
            "registry_version": "matching-releases-v1",
            "releases": [],
        }
    )
    report = run_regression(
        dataset=dataset,
        baseline_policy=policy,  # type: ignore[arg-type]
        candidate_policy=policy,  # type: ignore[arg-type]
        releases=releases,
    )
    assert not report.blocked
    assert report.baseline_policy == dataset.baseline_score_policy_version
    assert all(
        verdict.verdict in {"ok", "score_delta_informational"}
        for verdict in report.case_verdicts
    )


def test_published_releases_parse_with_the_published_dataset() -> None:
    dataset = load_golden_dataset(GOLDEN_PATH)
    known = frozenset(case.id for case in dataset.cases)
    releases = parse_releases(
        __import__("json").loads(RELEASES_PATH.read_text(encoding="utf-8")),
        known_case_ids=known,
    )
    assert releases.registry_version == "matching-releases-v1"
    assert len(releases.releases) >= 1

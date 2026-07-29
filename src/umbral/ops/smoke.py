"""Provider-neutral smoke checks for a release candidate."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

REQUIRED_SURFACES = ("web", "api", "worker", "scheduler")


@dataclass(frozen=True, slots=True)
class SmokeCheck:
    name: str
    passed: bool
    code: str


@dataclass(frozen=True, slots=True)
class SmokeReport:
    checks: tuple[SmokeCheck, ...]
    product_data_used: bool = False

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)


def run_smoke(checks: Mapping[str, Callable[[], bool]]) -> SmokeReport:
    """Run a closed set of local checks and normalize failures to stable codes."""

    required = (*REQUIRED_SURFACES, "extensions", "reference_job", "synthetic_object")
    results: list[SmokeCheck] = []
    for name in required:
        check = checks.get(name)
        if check is None:
            results.append(SmokeCheck(name, False, "smoke.missing_check"))
            continue
        try:
            passed = bool(check())
        except Exception:
            passed = False
        results.append(
            SmokeCheck(name, passed, "smoke.ok" if passed else "smoke.failed")
        )
    return SmokeReport(tuple(results))

"""Provider-neutral release and identity smoke checks."""
# ruff: noqa: E501

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from umbral.application.identity.access import IdentityAccess
from umbral.application.identity.administration import AccessAdministration
from umbral.infrastructure.db.repositories.identity import InMemoryIdentityStore
from umbral.infrastructure.email.recording import RecordingEmailAdapter
from umbral.infrastructure.identity.fake import FakeIdentityProvider

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
    """Run a closed set of local checks and normalize failures."""

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
        results.append(SmokeCheck(name, passed, "smoke.ok" if passed else "smoke.failed"))
    return SmokeReport(tuple(results))


def run_identity_smoke() -> dict[str, str]:
    store = InMemoryIdentityStore()
    AccessAdministration(store).preload_invitation("smoke@example.test")
    access = IdentityAccess(store, FakeIdentityProvider(), RecordingEmailAdapter())
    now = datetime.now(timezone.utc)
    access.request_magic_link(email="smoke@example.test", origin_fingerprint="smoke", correlation_id=uuid4(), now=now)
    return {"result": "accepted", "sessions": str(len(store.sessions)), "synthetic": "true"}

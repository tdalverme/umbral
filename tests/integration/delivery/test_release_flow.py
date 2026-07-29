"""Local release promotion flow contracts (T086)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from umbral.ops.release import ReleaseManifest
from umbral.ops.release_lock import ReleaseLock, ReleaseLockBusy


def test_environment_lock_is_create_if_absent_and_expires() -> None:
    now = datetime(2026, 7, 29, tzinfo=timezone.utc)
    lock = ReleaseLock()

    lock.acquire(
        "preview",
        owner="ci-1",
        release_id="r1",
        now=now,
        ttl=timedelta(minutes=15),
    )
    with pytest.raises(ReleaseLockBusy):
        lock.acquire("preview", owner="ci-2", release_id="r2", now=now)

    lock.acquire(
        "preview",
        owner="ci-2",
        release_id="r2",
        now=now + timedelta(minutes=16),
    )
    assert lock.owner("preview", now=now + timedelta(minutes=16)) == "ci-2"


def test_promotion_requires_same_manifest_and_ordered_gates() -> None:
    from umbral.ops.release import PromotionPlan, PromotionRejected

    manifest = ReleaseManifest.from_mapping(
        {
            "schema_version": 1,
            "release_id": "r1",
            "git_sha": "a" * 40,
            "built_at": "2026-07-29T00:00:00+00:00",
            "contract_major": 1,
            "database_revision": "0001_foundation_runtime",
            "config_schema_version": 1,
            "artifacts": {
                "web": {
                    "image": "web",
                    "digest": "sha256:" + "1" * 64,
                    "platform": "linux/amd64",
                },
                "runtime": {
                    "image": "runtime",
                    "digest": "sha256:" + "2" * 64,
                    "platform": "linux/amd64",
                },
            },
        }
    )
    plan = PromotionPlan(manifest=manifest, environment="preview")

    assert plan.run_gates(access=True, backup=True, migration=True, smoke=True)
    with pytest.raises(PromotionRejected):
        plan.run_gates(access=True, backup=True, migration=True, smoke=False)

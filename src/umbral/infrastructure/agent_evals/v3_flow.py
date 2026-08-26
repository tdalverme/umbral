"""Compose contracts, adapters, executor, runner and comparison for the
opt-in real-provider v3 eval flow, and write reviewable evidence.

Exit codes: 0 complete/advisory, 2 safety-blocked, 3 incomplete,
4 invalid configuration. Evidence is written for every outcome, including
blocked and incomplete runs.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from umbral.application.agent_evals.contracts import PriceTable
from umbral.application.agent_evals.v3.comparison import compare_runs
from umbral.application.agent_evals.v3.contracts import (
    EvalBudget,
    EvalV3ValidationError,
)
from umbral.application.agent_evals.v3.loader import load_dataset as load_v3_dataset
from umbral.application.agent_evals.v3.loader import load_policy as load_v3_policy
from umbral.application.agent_evals.v3.releases import load_releases as load_v3_releases
from umbral.application.agent_evals.v3.reporting import write_evidence
from umbral.application.agent_evals.v3.runner import run_suite
from umbral.infrastructure.agent_evals.trajectory_executor import (
    PostgresConversationTrialExecutor,
    SessionFactory,
)
from umbral.infrastructure.agent_evals.v3_adapters import ManagedEvalModelAdapter
from umbral.infrastructure.config.settings import Settings

CONTRACTS = Path(__file__).parents[4] / "contracts" / "agent-evals"
EVIDENCE_DIR = (
    Path(__file__).parents[4] / "docs" / "runbooks" / "evidence" / "agent-evals"
)

EXIT_OK = 0
EXIT_BLOCKED = 2
EXIT_INCOMPLETE = 3
EXIT_CONFIG = 4


def run_v3_eval(
    *,
    settings: Settings,
    baseline_id: str,
    candidate_id: str,
    cost_cap_usd: float,
    include_holdout: bool = True,
    contracts_dir: Path = CONTRACTS,
    evidence_dir: Path = EVIDENCE_DIR,
    seed_user: Callable[[SessionFactory], UUID] | None = None,
    seed_profile: Callable[[SessionFactory, UUID], object] | None = None,
) -> int:
    """Run baseline then candidate and write evidence; return the exit code."""
    if (
        settings.agent_model_provider != "managed"
        or not settings.agent_managed_endpoint
    ):
        return _fail_config("AGENT_MODEL_PROVIDER=managed and AGENT_MANAGED_ENDPOINT")
    adapter = ManagedEvalModelAdapter(settings=settings)
    try:
        dataset = load_v3_dataset(
            contracts_dir / "v3" / "conversation-trajectories-v3.json"
        )
        policy = load_v3_policy(contracts_dir / "v3" / "eval-policy-v3.json")
        releases = load_v3_releases(contracts_dir / "v3" / "graph-releases-v2.json")
        price_table = _load_price_table(contracts_dir)
    except (EvalV3ValidationError, OSError, ValueError) as exc:
        return _fail_config(str(exc))
    by_id = {release.id: release for release in releases.releases}
    baseline_release = by_id.get(baseline_id)
    candidate_release = by_id.get(candidate_id)
    if baseline_release is None or candidate_release is None:
        return _fail_config(f"unknown release ids: {baseline_id}, {candidate_id}")

    factory, executor = _build_executor(settings, seed_user, seed_profile)
    budget = EvalBudget(cost_cap_usd)
    baseline = run_suite(
        dataset=dataset,
        release=baseline_release,
        model_adapter=adapter,
        executor=executor,
        policy=policy,
        budget=budget,
        include_holdout=include_holdout,
        price_table=price_table,
    )
    candidate = run_suite(
        dataset=dataset,
        release=candidate_release,
        model_adapter=adapter,
        executor=executor,
        policy=policy,
        budget=budget,
        include_holdout=include_holdout,
        price_table=price_table,
    )
    report = compare_runs(
        baseline=baseline,
        candidate=candidate,
        baseline_release=baseline_release,
        candidate_release=candidate_release,
        dataset=dataset,
        policy=policy,
    )
    paths = write_evidence(report, evidence_dir)
    print(f"evidence: {paths.final_dir}")
    if report.blocked:
        return EXIT_BLOCKED
    if not baseline.complete or not candidate.complete:
        return EXIT_INCOMPLETE
    return EXIT_OK


def _fail_config(reason: str) -> int:
    print(f"invalid configuration: {reason}", file=sys.stderr)
    return EXIT_CONFIG


def _load_price_table(contracts_dir: Path) -> PriceTable:
    from umbral.application.agent_evals.price import load_price_table

    return load_price_table(contracts_dir / "v1" / "price-table-v1.json")


def _build_executor(
    settings: Settings,
    seed_user: Callable[[SessionFactory], UUID] | None,
    seed_profile: Callable[[SessionFactory, UUID], object] | None,
) -> tuple[SessionFactory, PostgresConversationTrialExecutor]:
    from umbral.infrastructure.db.session import SessionProvider

    factory = SessionProvider(settings.database_url).session_factory
    if seed_user is None:
        seed_user = _seed_user_for()
    if seed_profile is None:
        seed_profile = _seed_profile_for()
    assert seed_user is not None and seed_profile is not None
    return factory, PostgresConversationTrialExecutor(
        factory=factory,
        url=settings.database_url,
        seed_user=seed_user,
        seed_profile=seed_profile,
    )


def _seed_user_for() -> Callable[[SessionFactory], UUID]:
    from umbral.domain.identity.models import ProductUser, RoleAssignment
    from umbral.infrastructure.db.repositories.identity import SqlAlchemyIdentityStore

    def seed(factory: SessionFactory) -> UUID:
        store = SqlAlchemyIdentityStore(
            factory, fingerprint_key=b"evals-v3", environment="local"
        )
        user_id = uuid4()
        with store.transaction():
            store.save_user(
                ProductUser(
                    id=user_id,
                    normalized_email=f"evals-v3-{user_id}@example.invalid",
                    status="active",
                )
            )
            store.save_role(
                RoleAssignment(
                    id=uuid4(),
                    product_user_id=user_id,
                    role="user",
                    granted_at=datetime.now(timezone.utc),
                )
            )
        return user_id

    return seed


def _seed_profile_for() -> Callable[[SessionFactory, UUID], object]:
    from umbral.application.radar.contracts import ProfileVersion, SearchProfile
    from umbral.infrastructure.db.repositories.radar import (
        SqlAlchemyProfileVersionRepository,
        SqlAlchemySearchProfileRepository,
    )

    def seed(_factory: SessionFactory, owner_id: UUID) -> SearchProfile:
        profile = SearchProfile(
            profile_id=uuid4(),
            owner_id=owner_id,
            name="eval-radar-v3",
            operation="rental",
            zones=("palermo",),
            budget_max=1000.0,
            budget_min=None,
            min_rooms=2,
            surface_min=None,
            surface_max=None,
            status="active",
            unknown_strategy={
                "price": "exclude",
                "location": "exclude",
                "rooms": "include",
                "surface": "include",
            },
            version=1,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            current_version_id=None,
            latest_run_id=None,
            correlation_id=uuid4(),
        )
        SqlAlchemySearchProfileRepository(_factory).insert(profile)
        SqlAlchemyProfileVersionRepository(_factory).insert(
            ProfileVersion(
                version_id=uuid4(),
                profile_id=profile.profile_id,
                profile_version=1,
                payload={},
                created_at=datetime.now(timezone.utc),
                correlation_id=uuid4(),
            )
        )
        return profile

    return seed


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the v3 managed eval flow (opt-in, real provider)."
    )
    parser.add_argument("--baseline", required=True, help="Baseline release id")
    parser.add_argument("--candidate", required=True, help="Candidate release id")
    parser.add_argument("--cost-cap-usd", type=float, default=5.0)
    parser.add_argument(
        "--include-holdout", action="store_true", default=True,
        help="Include holdout cases (default true)",
    )
    parser.add_argument(
        "--no-holdout", action="store_false", dest="include_holdout",
        help="Run development cases only (local iteration)",
    )
    parsed = parser.parse_args()
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in Settings._known_fields
    }
    settings = Settings.from_environment(environment)
    code = run_v3_eval(
        settings=settings,
        baseline_id=parsed.baseline,
        candidate_id=parsed.candidate,
        cost_cap_usd=parsed.cost_cap_usd,
        include_holdout=parsed.include_holdout,
    )
    sys.exit(code)


if __name__ == "__main__":
    main()
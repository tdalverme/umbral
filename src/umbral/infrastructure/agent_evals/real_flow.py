"""Opt-in real-provider eval flow (clarification Q4, R-12).

Runs the golden suite against the real managed gateway with a bounded eval
budget, outside CI. The gate itself always runs the deterministic adapter;
this flow validates behavior with the production provider chosen by the ADR.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from umbral.application.agent_evals.contracts import (
    GoldenConversationCase,
    GoldenDataset,
)
from umbral.application.agent_evals.golden import load_golden_dataset
from umbral.application.agent_evals.price import load_price_table
from umbral.application.agent_evals.releases import load_releases
from umbral.application.agent_evals.runner import run_suite
from umbral.application.radar.contracts import ProfileVersion, SearchProfile
from umbral.domain.identity.models import ProductUser, RoleAssignment
from umbral.infrastructure.agent.budgets import policy_from_settings
from umbral.infrastructure.agent.model_gateway.managed import ManagedModelGateway
from umbral.infrastructure.agent_evals.composition import (
    PostgresEvalCaseExecutor,
    SessionFactory,
)
from umbral.infrastructure.config.settings import Settings
from umbral.infrastructure.db.repositories.identity import SqlAlchemyIdentityStore
from umbral.infrastructure.db.repositories.radar import (
    SqlAlchemyProfileVersionRepository,
    SqlAlchemySearchProfileRepository,
)
from umbral.infrastructure.db.session import SessionProvider

CONTRACTS = Path(__file__).parents[4] / "contracts" / "agent-evals" / "v1"


def run_real_evals(
    *,
    settings: Settings,
    case_limit: int | None = None,
    cost_cap_usd: float | None = None,
) -> dict[str, object]:
    """Run the golden suite against the real gateway and return a summary."""
    if (
        settings.agent_model_provider != "managed"
        or not settings.agent_managed_endpoint
    ):
        raise RuntimeError(
            "real-provider evals require AGENT_MODEL_PROVIDER=managed and "
            "AGENT_MANAGED_ENDPOINT"
        )
    dataset = load_golden_dataset(CONTRACTS / "conversations-golden-v1.json")
    releases = load_releases(
        CONTRACTS / "graph-releases-v1.json",
        known_case_ids=frozenset(case.id for case in dataset.cases),
    )
    price_table = load_price_table(CONTRACTS / "price-table-v1.json")
    release = releases.active_release()
    if release is None:
        raise RuntimeError("no active graph release")

    budget_policy = policy_from_settings(settings)
    eval_budget = (
        cost_cap_usd if cost_cap_usd is not None else budget_policy.user_cost_cap_usd
    )
    factory = SessionProvider(settings.database_url).session_factory
    managed_endpoint = settings.agent_managed_endpoint or ""

    def seed_user(_factory: SessionFactory) -> UUID:
        store = SqlAlchemyIdentityStore(
            factory, fingerprint_key=b"eval", environment="local"
        )
        user_id = uuid4()
        with store.transaction():
            store.save_user(
                ProductUser(
                    id=user_id,
                    normalized_email=f"eval-{user_id}@example.invalid",
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

    def seed_profile(_factory: SessionFactory, owner_id: UUID) -> SearchProfile:
        profile = SearchProfile(
            profile_id=uuid4(),
            owner_id=owner_id,
            name="eval-radar",
            operation="rental",
            zones=("palermo",),
            budget_max=900000.0,
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
        SqlAlchemySearchProfileRepository(factory).insert(profile)
        SqlAlchemyProfileVersionRepository(factory).insert(
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

    def real_gateway(_case: GoldenConversationCase) -> object:
        return ManagedModelGateway(
            endpoint=managed_endpoint,
            api_key=settings.agent_managed_api_key or "",
            model=settings.agent_model_name,
            timeout_seconds=settings.agent_model_timeout_seconds,
            max_retries=settings.agent_model_max_retries,
        )

    executor = PostgresEvalCaseExecutor(
        factory=factory,
        url=settings.database_url,
        seed_user=seed_user,
        seed_profile=seed_profile,
        gateway_factory=real_gateway,
    )
    cases = dataset.cases[:case_limit] if case_limit else dataset.cases
    subset = _subset(dataset, cases)
    results = run_suite(
        executor=executor,
        dataset=subset,
        release=release,
        price_table=price_table,
        gateway_fidelity="real",
    )
    total_cost = sum(item.cost_usd for item in results)
    return {
        "fidelity": "real",
        "cases_run": len(results),
        "total_cost_usd": round(total_cost, 4),
        "cost_cap_usd": eval_budget,
        "over_cap": total_cost > eval_budget,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }


def _subset(
    dataset: GoldenDataset, cases: tuple[GoldenConversationCase, ...]
) -> GoldenDataset:
    return GoldenDataset(
        contract_version=dataset.contract_version,
        registry_version=dataset.registry_version,
        reviewed_by=dataset.reviewed_by,
        reviewed_at=dataset.reviewed_at,
        min_cases_per_family=dataset.min_cases_per_family,
        cases=cases,
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Real-provider agent eval flow (opt-in)."
    )
    parser.add_argument(
        "--case-limit", type=int, default=0, help="Max cases to evaluate (0 = all)."
    )
    parser.add_argument(
        "--cost-cap-usd", type=float, default=0.0, help="Eval budget cap in USD."
    )
    parsed = parser.parse_args()
    settings = Settings.from_environment(dict(os.environ))
    summary = run_real_evals(
        settings=settings,
        case_limit=parsed.case_limit or None,
        cost_cap_usd=parsed.cost_cap_usd or None,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

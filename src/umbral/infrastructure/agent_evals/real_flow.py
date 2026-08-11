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

from umbral.application.agent_evals.allowances import load_allowances
from umbral.application.agent_evals.context import load_conversation_contexts
from umbral.application.agent_evals.contracts import (
    CaseEvalResult,
    GoldenConversationCase,
    GoldenDataset,
)
from umbral.application.agent_evals.golden import load_golden_dataset
from umbral.application.agent_evals.metrics import (
    CaseScore,
    evaluate_case,
    score_case,
)
from umbral.application.agent_evals.price import load_price_table
from umbral.application.agent_evals.releases import load_releases
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
    repeat: int = 3,
) -> dict[str, object]:
    """Run the golden suite against the real gateway and return the scorecard.

    Each case runs ``repeat`` times: safety signals stay strict (0 invented
    refs, 0 unconfirmed mutations) while quality signals are reported as
    rates and averages per case and per family.
    """
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
    contexts = load_conversation_contexts(
        CONTRACTS / "conversation-context-v1.json",
        known_case_ids=frozenset(case.id for case in dataset.cases),
    )
    allowances = load_allowances(
        CONTRACTS / "ambiguity-allowances-v1.json",
        known_case_ids=frozenset(case.id for case in dataset.cases),
    )
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
        contexts={
            case_id: {
                "entity": context.entity,
                "id": context.id,
                "listing_ids": list(context.listing_ids),
            }
            for case_id, context in contexts.items()
        },
    )
    cases = dataset.cases[:case_limit] if case_limit else dataset.cases
    subset = _subset(dataset, cases)
    all_results: list[CaseEvalResult] = []
    all_scores: list[CaseScore] = []
    for _ in range(max(1, repeat)):
        for case in subset.cases:
            trace = executor.execute(case=case, release=release)
            all_results.append(
                evaluate_case(case=case, trace=trace, price_table=price_table)
            )
            all_scores.append(
                score_case(case=case, trace=trace, allowance=allowances.get(case.id))
            )
    total_cost = sum(item.cost_usd for item in all_results)
    safety_violations: list[dict[str, object]] = []
    per_case: list[dict[str, object]] = []
    case_ids = [case.id for case in subset.cases]
    for case in subset.cases:
        runs = [
            score for score in all_scores if score.case_id == case.id
        ]
        outcome_rate = (
            sum(1 for score in runs if score.outcome_ok) / len(runs)
            if runs
            else 0.0
        )
        safety_ok = all(score.safety_ok for score in runs)
        if not safety_ok:
            for score in runs:
                if not score.safety_ok:
                    safety_violations.append(
                        {
                            "case_id": case.id,
                            "invented_refs": score.invented_refs,
                            "unconfirmed_mutation": score.unconfirmed_mutation,
                        }
                    )
        per_case.append(
            {
                "case_id": case.id,
                "family": case.family,
                "runs": len(runs),
                "outcome_rate": round(outcome_rate, 3),
                "outcome_acceptable_rate": round(
                    sum(1 for score in runs if score.outcome_acceptable)
                    / len(runs),
                    3,
                )
                if runs
                else 0.0,
                "tools_acceptable_rate": round(
                    sum(1 for score in runs if score.tools_acceptable)
                    / len(runs),
                    3,
                )
                if runs
                else 0.0,
                "safety_ok": safety_ok,
                "avg_quality": round(
                    sum(score.quality_score for score in runs) / len(runs), 3
                ),
                "avg_tool_jaccard": round(
                    sum(score.tool_jaccard for score in runs) / len(runs), 3
                ),
                "avg_grounding": round(
                    sum(score.grounding_coverage for score in runs) / len(runs), 3
                ),
                "args_rate": round(
                    sum(1 for score in runs if score.args_ok) / len(runs), 3
                ),
            }
        )
    families: list[dict[str, object]] = []
    family_names = sorted({case.family for case in subset.cases})
    for family in family_names:
        family_cases = [case.id for case in subset.cases if case.family == family]
        family_scores = [score for score in all_scores if score.case_id in family_cases]
        families.append(
            {
                "family": family,
                "cases": len(family_cases),
                "runs": len(family_scores),
                "outcome_rate": round(
                    sum(1 for score in family_scores if score.outcome_ok)
                    / len(family_scores),
                    3,
                )
                if family_scores
                else 0.0,
                "outcome_acceptable_rate": round(
                    sum(1 for score in family_scores if score.outcome_acceptable)
                    / len(family_scores),
                    3,
                )
                if family_scores
                else 0.0,
                "avg_quality": round(
                    sum(score.quality_score for score in family_scores)
                    / len(family_scores),
                    3,
                )
                if family_scores
                else 0.0,
            }
        )
    overall_outcome = (
        sum(1 for score in all_scores if score.outcome_ok) / len(all_scores)
        if all_scores
        else 0.0
    )
    overall_acceptable = (
        sum(1 for score in all_scores if score.outcome_acceptable)
        / len(all_scores)
        if all_scores
        else 0.0
    )
    overall_quality = (
        sum(score.quality_score for score in all_scores) / len(all_scores)
        if all_scores
        else 0.0
    )
    summary: dict[str, object] = {
        "fidelity": "real",
        "release_id": release.id,
        "model_version": release.components.model_version,
        "repeat": max(1, repeat),
        "cases": len(case_ids),
        "case_runs": len(all_scores),
        "outcome_rate": round(overall_outcome, 3),
        "outcome_acceptable_rate": round(overall_acceptable, 3),
        "avg_quality": round(overall_quality, 3),
        "safety_ok": not safety_violations,
        "total_cost_usd": round(total_cost, 4),
        "cost_cap_usd": eval_budget,
        "over_cap": total_cost > eval_budget,
        "families": families,
        "per_case": per_case,
        "safety_violations": safety_violations,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if safety_violations:
        raise RuntimeError(
            "real-provider evals SAFETY violations: "
            + ", ".join(str(item["case_id"]) for item in safety_violations)
        )
    return summary


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
    parser.add_argument(
        "--repeat", type=int, default=3, help="Runs per case (default 3)."
    )
    parsed = parser.parse_args()
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in Settings._known_fields
    }
    settings = Settings.from_environment(environment)
    summary = run_real_evals(
        settings=settings,
        case_limit=parsed.case_limit or None,
        cost_cap_usd=parsed.cost_cap_usd or None,
        repeat=parsed.repeat,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

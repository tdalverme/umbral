"""Finite deny-by-default authorization matrix."""
# ruff: noqa: E501

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

Role = Literal["user", "operator", "administrator"]


@dataclass(frozen=True, slots=True)
class ActionRule:
    action: str
    allowed_roles: frozenset[Role]
    owner_required: bool = False


ACTION_RULES: dict[str, ActionRule] = {
    "auth.session.read": ActionRule(
        "auth.session.read", frozenset({"user", "operator", "administrator"})
    ),
    "auth.session.logout": ActionRule(
        "auth.session.logout", frozenset({"user", "operator", "administrator"})
    ),
    "product.resource.create": ActionRule(
        "product.resource.create", frozenset({"user", "operator", "administrator"})
    ),
    "product.resource.read": ActionRule(
        "product.resource.read", frozenset({"user", "operator", "administrator"}), True
    ),
    "product.resource.update": ActionRule(
        "product.resource.update",
        frozenset({"user", "operator", "administrator"}),
        True,
    ),
    "product.resource.delete": ActionRule(
        "product.resource.delete",
        frozenset({"user", "operator", "administrator"}),
        True,
    ),
    "product.search_profile.create": ActionRule(
        "product.search_profile.create",
        frozenset({"user", "operator", "administrator"}),
    ),
    "product.search_profile.read": ActionRule(
        "product.search_profile.read",
        frozenset({"user", "operator", "administrator"}),
        True,
    ),
    "product.search_profile.update": ActionRule(
        "product.search_profile.update",
        frozenset({"user", "operator", "administrator"}),
        True,
    ),
    "product.search_profile.status": ActionRule(
        "product.search_profile.status",
        frozenset({"user", "operator", "administrator"}),
        True,
    ),
    "product.matches.read": ActionRule(
        "product.matches.read",
        frozenset({"user", "operator", "administrator"}),
        True,
    ),
    "product.explanation.read": ActionRule(
        "product.explanation.read",
        frozenset({"user", "operator", "administrator"}),
        True,
    ),
    "product.comparison.read": ActionRule(
        "product.comparison.read",
        frozenset({"user", "operator", "administrator"}),
        True,
    ),
    "product.comparison.write": ActionRule(
        "product.comparison.write",
        frozenset({"user", "operator", "administrator"}),
        True,
    ),
    "product.listing.read": ActionRule(
        "product.listing.read",
        frozenset({"user", "operator", "administrator"}),
        True,
    ),
    "product.feedback.write": ActionRule(
        "product.feedback.write",
        frozenset({"user", "operator", "administrator"}),
        True,
    ),
    "product.feedback.read": ActionRule(
        "product.feedback.read",
        frozenset({"user", "operator", "administrator"}),
        True,
    ),
    "product.learning.write": ActionRule(
        "product.learning.write",
        frozenset({"user", "operator", "administrator"}),
        True,
    ),
    "product.learning.read": ActionRule(
        "product.learning.read",
        frozenset({"user", "operator", "administrator"}),
        True,
    ),
    "product.events.emit": ActionRule(
        "product.events.emit", frozenset({"user", "operator", "administrator"})
    ),
    "ops.identity.conflict.review": ActionRule(
        "ops.identity.conflict.review", frozenset({"operator", "administrator"})
    ),
    "ops.identity.invitation.preload": ActionRule(
        "ops.identity.invitation.preload", frozenset({"operator", "administrator"})
    ),
    "ops.ingestion.batch.submit": ActionRule(
        "ops.ingestion.batch.submit", frozenset({"operator", "administrator"})
    ),
    "ops.ingestion.run.read": ActionRule(
        "ops.ingestion.run.read", frozenset({"operator", "administrator"})
    ),
    "ops.ingestion.quality.read": ActionRule(
        "ops.ingestion.quality.read", frozenset({"operator", "administrator"})
    ),
    "admin.identity.user.status.change": ActionRule(
        "admin.identity.user.status.change", frozenset({"administrator"})
    ),
    "admin.identity.role.change": ActionRule(
        "admin.identity.role.change", frozenset({"administrator"})
    ),
    "admin.identity.bootstrap": ActionRule("admin.identity.bootstrap", frozenset()),
}


@dataclass(frozen=True, slots=True)
class AuthorizationDecision:
    allowed: bool
    reason: str
    policy_version: str = "identity-policy.v1"


def authorize_roles(
    *,
    roles: set[str] | frozenset[str],
    action: str,
    actor_id: UUID,
    owner_id: UUID | None,
) -> AuthorizationDecision:
    rule = ACTION_RULES.get(action)
    if rule is None:
        return AuthorizationDecision(False, "action_unknown")
    if any(role not in {"user", "operator", "administrator"} for role in roles):
        return AuthorizationDecision(False, "role_unknown")
    if rule.owner_required and owner_id is None:
        return AuthorizationDecision(False, "owner_missing")
    if rule.owner_required and owner_id != actor_id:
        return AuthorizationDecision(False, "owner_mismatch")
    if not roles.intersection(rule.allowed_roles):
        return AuthorizationDecision(False, "role_not_allowed")
    return AuthorizationDecision(True, "eligible")

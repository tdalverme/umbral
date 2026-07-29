 # ruff: noqa: E501
from __future__ import annotations

from uuid import uuid4

from umbral.domain.identity.policy import authorize_roles


def test_policy_is_deny_by_default_and_owner_scoped() -> None:
    owner = uuid4()
    assert authorize_roles(roles={"user"}, action="product.resource.read", actor_id=owner, owner_id=owner).allowed
    assert not authorize_roles(roles={"user"}, action="product.resource.read", actor_id=owner, owner_id=uuid4()).allowed
    assert not authorize_roles(roles={"administrator"}, action="admin.identity.bootstrap", actor_id=owner, owner_id=None).allowed
    assert not authorize_roles(roles={"unknown"}, action="auth.session.read", actor_id=owner, owner_id=None).allowed

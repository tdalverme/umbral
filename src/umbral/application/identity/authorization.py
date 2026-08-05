"""Current-session authorization with deny-by-default policy."""
# ruff: noqa: E501

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from uuid import UUID, uuid4

from umbral.application.identity.contracts import CurrentPrincipal, IdentityError
from umbral.application.identity.ports import IdentityStore
from umbral.domain.identity.models import AccessAuditEvent
from umbral.domain.identity.policy import authorize_roles


class AccessControl:
    def __init__(self, store: IdentityStore) -> None:
        self.store = store

    def authorize(
        self,
        token: str,
        *,
        action: str,
        resource_owner_id: UUID | None,
        now: datetime,
        correlation_id: UUID | None = None,
    ) -> CurrentPrincipal:
        now = now.astimezone(timezone.utc)
        digest = hashlib.sha256(token.encode()).digest()
        with self.store.transaction():
            session = self.store.session_by_digest(digest)
            if session is None:
                raise IdentityError("auth.session_required", status=401, recovery="sign_in")
            user = self.store.user(session.product_user_id)
            if session.revoked_at is not None:
                self._audit(False, "session_revoked", action, user.id if user else None, session.id, correlation_id=correlation_id)
                raise IdentityError("auth.session_required", status=401, recovery="sign_in")
            if session.is_idle_expired(now):
                session.revoked_at = now
                session.revocation_reason = "idle_timeout"
                self.store.save_session(session)
                self._audit(False, "session_idle_expired", action, user.id if user else None, session.id, correlation_id=correlation_id)
                raise IdentityError("auth.session_required", status=401, recovery="sign_in")
            if user is None or user.status != "active":
                self._audit(False, "user_inactive", action, user.id if user else None, session.id, correlation_id=correlation_id)
                raise IdentityError("auth.access_denied", status=403, recovery="contact_support")
            roles = self.store.active_roles(user.id)
            decision = authorize_roles(roles=roles, action=action, actor_id=user.id, owner_id=resource_owner_id)
            if not decision.allowed:
                self._audit(False, decision.reason, action, user.id, session.id, correlation_id=correlation_id)
                raise IdentityError("auth.access_denied", status=403, recovery="contact_support")
            session.last_activity_at = now
            self.store.save_session(session)
            self._audit(True, "eligible", action, user.id, session.id, correlation_id=correlation_id)
            return CurrentPrincipal(user.id, tuple(sorted(roles)), session.last_activity_at)

    def _audit(
        self,
        allowed: bool,
        reason: str,
        action: str,
        user_id: UUID | None,
        session_id: UUID,
        *,
        correlation_id: UUID | None,
    ) -> None:
        event = AccessAuditEvent(
            uuid4(),
            "authorization.allowed.v1" if allowed else "authorization.denied.v1",
            "allowed" if allowed else "denied",
            reason,
            correlation_id or uuid4(),
            datetime.now(timezone.utc),
            actor_user_id=user_id,
            subject_user_id=user_id,
            session_id=session_id,
            action=action,
            policy_version="identity-policy.v1",
        )
        self.store.append_audit(event)

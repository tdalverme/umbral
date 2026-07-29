"""Controlled invitation, status and role administration."""
# ruff: noqa: E501

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, cast
from uuid import UUID, uuid4

from umbral.application.identity.contracts import IdentityError
from umbral.application.identity.ports import IdentityStore
from umbral.domain.identity.email import normalize_email
from umbral.domain.identity.events import validate_event
from umbral.domain.identity.models import AccessAuditEvent, Invitation, RoleAssignment


class AccessAdministration:
    def __init__(self, store: IdentityStore) -> None:
        self.store = store

    def preload_invitation(self, email: str, *, source: str = "controlled_preload") -> Invitation:
        normalized = normalize_email(email).value
        with self.store.lock:
            existing = self.store.invitation_for_email(normalized)
            if existing:
                return existing
            invitation = Invitation.new(normalized, source=source)
            self.store.invitations[invitation.id] = invitation
            self._audit(
                "invitation.preloaded.v1",
                "accepted",
                "eligible",
                invitation_id=invitation.id,
            )
            return invitation

    def set_user_status(self, user_id: UUID, *, status: str, reason: str = "administrator_change", now: datetime | None = None, actor_user_id: UUID | None = None) -> None:
        with self.store.lock:
            self._require_administrator(actor_user_id)
            user = self.store.users[user_id]
            moment = now or datetime.now(timezone.utc)
            if status == "disabled":
                user.disable(reason, now=moment)
            elif status == "active":
                user.enable(now=moment)
            else:
                raise ValueError("unknown user status")
            self._audit(
                "user.status_changed.v1",
                "accepted",
                "administrator_change",
                actor_user_id=actor_user_id,
                subject_user_id=user_id,
            )

    def change_role(self, user_id: UUID, role: str, *, grant: bool, reason: str = "administrator_change", now: datetime | None = None, actor_user_id: UUID | None = None) -> UUID:
        if role not in {"user", "operator", "administrator"}:
            raise ValueError("unknown role")
        moment = now or datetime.now(timezone.utc)
        with self.store.lock:
            self._require_administrator(actor_user_id)
            current = next((item for item in self.store.roles.values() if item.product_user_id == user_id and item.role == role and item.active), None)
            if grant:
                if current:
                    return current.id
                assignment = RoleAssignment(uuid4(), user_id, cast(Literal["user", "operator", "administrator"], role), moment, reason=reason)
                self.store.roles[assignment.id] = assignment
                self._audit(
                    "role.granted.v1",
                    "accepted",
                    "administrator_change",
                    actor_user_id=actor_user_id,
                    subject_user_id=user_id,
                    role_assignment_id=assignment.id,
                )
                return assignment.id
            if current:
                current.revoked_at = moment
                self._audit(
                    "role.revoked.v1",
                    "accepted",
                    "administrator_change",
                    actor_user_id=actor_user_id,
                    subject_user_id=user_id,
                    role_assignment_id=current.id,
                )
            return current.id if current else uuid4()

    def _require_administrator(self, actor_user_id: UUID | None) -> None:
        if actor_user_id is None:
            return
        actor = self.store.users.get(actor_user_id)
        if actor is None or actor.status != "active" or "administrator" not in self.store.active_roles(actor_user_id):
            raise IdentityError("auth.access_denied", status=403, recovery="contact_support")

    def bootstrap_administrator(self, user_id: UUID, *, now: datetime | None = None) -> UUID:
        with self.store.lock:
            if any(item.role == "administrator" and item.active for item in self.store.roles.values()):
                raise IdentityError("auth.access_denied", status=403, recovery="contact_support")
            user = self.store.users.get(user_id)
            if user is None or user.status != "active":
                raise IdentityError("auth.access_denied", status=403, recovery="contact_support")
            assignment = RoleAssignment(uuid4(), user_id, "administrator", now or datetime.now(timezone.utc), reason="zero_admin_bootstrap")
            self.store.roles[assignment.id] = assignment
            self._audit(
                "role.granted.v1",
                "accepted",
                "zero_admin_bootstrap",
                subject_user_id=user_id,
                role_assignment_id=assignment.id,
            )
            return assignment.id

    def _audit(
        self,
        event_type: str,
        result: str,
        reason: str,
        *,
        actor_user_id: UUID | None = None,
        subject_user_id: UUID | None = None,
        invitation_id: UUID | None = None,
        role_assignment_id: UUID | None = None,
    ) -> None:
        correlation_id = uuid4()
        validate_event(
            event_type=event_type,
            result=result,
            reason=reason,
            fields={
                "actor_user_id": actor_user_id,
                "subject_user_id": subject_user_id,
                "invitation_id": invitation_id,
                "role_assignment_id": role_assignment_id,
            },
        )
        self.store.audits.append(
            AccessAuditEvent(
                uuid4(),
                event_type,
                result,
                reason,
                correlation_id,
                datetime.now(timezone.utc),
                actor_user_id=actor_user_id,
                subject_user_id=subject_user_id,
                invitation_id=invitation_id,
                role_assignment_id=role_assignment_id,
            )
        )

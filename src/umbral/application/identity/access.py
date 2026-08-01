"""Magic-link request, issue, confirmation and session orchestration."""
# ruff: noqa: E501

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from urllib.parse import urlparse
from uuid import UUID, uuid4

from umbral.application.identity.contracts import (
    CurrentPrincipal,
    IdentityError,
    MagicLinkRequestResult,
    SessionResult,
    access_denied,
    link_unavailable,
)
from umbral.application.identity.ports import (
    EmailPort,
    IdentityProofPort,
    IdentityStore,
)
from umbral.application.jobs.contracts import SubmitJob
from umbral.application.jobs.ports import JobRuntime
from umbral.application.transactions import TransactionManager, transaction_scope
from umbral.domain.audit import AuditContext
from umbral.domain.identity.email import normalize_email
from umbral.domain.identity.events import validate_event
from umbral.domain.identity.models import (
    AccessAuditEvent,
    ExternalIdentityLink,
    MagicLinkAttempt,
    MagicLinkRequest,
    ProductSession,
    ProductUser,
    RoleAssignment,
    utc,
)


class IdentityAccess:
    """Deep module hiding provider, limiter and session state transitions."""

    def __init__(self, store: IdentityStore, provider: IdentityProofPort, email: EmailPort, *, environment: str = "local", capture_origin: str = "http://localhost:3000", job_runtime: JobRuntime | None = None, transaction_manager: TransactionManager[Any] | None = None) -> None:
        self.store = store
        self.provider = provider
        self.email = email
        self.environment = environment
        self.capture_origin = capture_origin.rstrip("/")
        self.job_runtime = job_runtime
        self.transaction_manager = transaction_manager

    def process_email_webhook(
        self, *, raw_body: bytes, headers: Mapping[str, str], now: datetime
    ) -> bool:
        event = self.email.verify_webhook(
            raw_body=raw_body, headers=headers, received_at=utc(now)
        )
        if not event:
            return False
        event_id = event.get("id")
        if not event_id:
            raise IdentityError("auth.webhook_invalid", status=400, recovery="none")
        with self._transaction():
            message_id = event.get("email_id")
            event_type = event.get("type")
            reason_by_type = {
                "email.delivered": "email_delivered",
                "email.delivery_delayed": "email_delayed",
                "email.bounced": "email_bounced",
                "email.complained": "email_complained",
                "email.failed": "email_rejected",
            }
            reason = reason_by_type.get(event_type or "")
            if reason is None:
                return self.store.append_provider_audit_once(
                    self.email.provider, event_id, None
                )
            attempt = (
                self.store.attempt_for_provider_message(message_id)
                if message_id is not None
                else None
            )
            if attempt:
                request = self.store.request(attempt.request_id)
                if request is None:
                    return self.store.append_provider_audit_once(
                        self.email.provider, event_id, None
                    )
                audit = self._new_audit(
                    "magic_link.delivery_observed.v1",
                    "observed",
                    reason,
                    request.correlation_id,
                    attempt_id=attempt.id,
                    provider=self.email.provider,
                    provider_event_id=event_id,
                )
                return self.store.append_provider_audit_once(
                    self.email.provider, event_id, audit
                )
            return self.store.append_provider_audit_once(
                self.email.provider, event_id, None
            )

    def request_magic_link(self, *, email: str, origin_fingerprint: str, correlation_id: UUID, now: datetime) -> MagicLinkRequestResult:
        now = utc(now)
        try:
            normalized = normalize_email(email).value
        except ValueError:
            normalized = email.strip().lower()[:320]
        email_fingerprint = self.store.fingerprint(normalized)
        origin_digest = self.store.fingerprint(origin_fingerprint)
        with self._transaction():
            email_count = self.store.recent_requests(email_fingerprint, now=now, field="email_fingerprint")
            origin_count = self.store.recent_requests(origin_digest, now=now, field="origin_fingerprint")
            invitation = self.store.invitation_for_email(normalized)
            user = self.store.user_for_email(normalized)
            eligible = (invitation is not None and invitation.status == "active") or (user is not None and user.status == "active")
            email_limited = email_count >= 3
            origin_limited = origin_count >= 20
            if email_limited and origin_limited:
                decision = "both_limited"
            elif email_limited:
                decision = "email_limited"
            elif origin_limited:
                decision = "origin_limited"
            else:
                decision = "eligible" if eligible else "not_eligible"
            request_id = uuid4()
            self.store.save_request(MagicLinkRequest(request_id, email_fingerprint, origin_digest, decision, now, now + timedelta(hours=24), correlation_id))
            self._audit("magic_link.requested.v1", "accepted" if decision == "eligible" else "denied", "eligible" if decision == "eligible" else ({"email_limited": "email_rate_limited", "origin_limited": "origin_rate_limited", "both_limited": "both_rate_limited"}.get(decision, "not_eligible")), correlation_id, request_id=request_id)
            if decision != "eligible":
                return MagicLinkRequestResult()
            subject_kind: Literal["invitation", "product_user"] = "invitation" if invitation is not None and invitation.status == "active" else "product_user"
            attempt = MagicLinkAttempt(uuid4(), request_id, subject_kind, invitation.id if subject_kind == "invitation" and invitation else None, user.id if subject_kind == "product_user" and user else None)
            self.store.save_attempt(attempt)
            if self.job_runtime is not None:
                try:
                    submission = self.job_runtime.submit(
                        SubmitJob.create(
                            job_type="identity.magic_link.issue",
                            logical_target=str(attempt.id),
                            idempotency_key=f"identity.magic-link/{attempt.id}",
                            correlation_id=correlation_id,
                        )
                    )
                    attempt.job_execution_id = submission.execution_id
                except Exception:
                    attempt.state = "failed"
                    attempt.failure_reason = "job_submission_failed"
                    self._audit(
                        "magic_link.issue_failed.v1",
                        "failed",
                        "provider_unavailable",
                        correlation_id,
                        attempt_id=attempt.id,
                    )
            return MagicLinkRequestResult()

    def issue_attempt(
        self,
        attempt_id: UUID,
        *,
        now: datetime,
        correlation_id: UUID | None = None,
    ) -> None:
        now = utc(now)
        with self._transaction():
            attempt = self.store.attempt(attempt_id)
            if attempt is None or attempt.state != "pending":
                return
            request = self.store.request(attempt.request_id)
            if request is None:
                return
            if correlation_id is not None and request.correlation_id != correlation_id:
                raise IdentityError("auth.request_invalid", status=400, recovery="none")
            invitation = self.store.invitation(attempt.invitation_id) if attempt.invitation_id else None
            user = self.store.user(attempt.product_user_id) if attempt.product_user_id else None
            email = invitation.normalized_email if invitation else user.normalized_email if user else None
            if email is None or (invitation and invitation.status != "active") or (user and user.status != "active"):
                attempt.state = "failed"
                attempt.failure_reason = "not_eligible"
                self.store.save_attempt(attempt)
                self._audit("magic_link.issue_failed.v1", "failed", "not_eligible", request.correlation_id, attempt_id=attempt_id)
                return
            attempt.state = "issuing"
            self.store.save_attempt(attempt)
        try:
            generated = self.provider.generate_magic_link(attempt_id=attempt_id, email=email, now=now)
            expected_origin = urlparse(self.capture_origin)
            actual_url = urlparse(generated.capture_url)
            if (
                (actual_url.scheme, actual_url.netloc)
                != (expected_origin.scheme, expected_origin.netloc)
                or actual_url.path != "/auth/capture"
            ):
                raise IdentityError("auth.link_unavailable", status=503, recovery="retry_later")
            acceptance = self.email.send_magic_link(attempt_id=attempt_id, normalized_email=email, capture_url=generated.capture_url, expires_at=generated.expires_at, idempotency_key=f"identity.magic-link/{attempt_id}", now=now)
        except IdentityError as exc:
            with self._transaction():
                attempt = self.store.attempt(attempt_id)
                if attempt is None:
                    return
                attempt.state = "failed"
                attempt.failure_reason = "provider_unavailable" if exc.code.endswith("provider_unavailable") else "provider_rejected"
                self.store.save_attempt(attempt)
                request = self.store.request(attempt.request_id)
                if request is not None:
                    self._audit("magic_link.issue_failed.v1", "failed", attempt.failure_reason, request.correlation_id, attempt_id=attempt_id)
            return
        with self._transaction():
            attempt = self.store.attempt(attempt_id)
            if attempt is None:
                return
            current = self.store.current_attempt(invitation_id=attempt.invitation_id, product_user_id=attempt.product_user_id)
            if current and current.id != attempt.id:
                current_request = self.store.request(current.request_id)
                attempt_request = self.store.request(attempt.request_id)
                if current_request is None or attempt_request is None:
                    return
                current_key = (current_request.requested_at, str(current.request_id))
                attempt_key = (attempt_request.requested_at, str(attempt.request_id))
                if current_key >= attempt_key:
                    attempt.state = "superseded"
                    attempt.superseded_at = acceptance.accepted_at
                    attempt.superseded_by_id = current.id
                    self.store.save_attempt(attempt)
                    self._audit(
                        "magic_link.superseded.v1",
                        "denied",
                        "link_superseded",
                        attempt_request.correlation_id,
                        attempt_id=attempt.id,
                    )
                    return
                current.state = "superseded"
                current.superseded_at = acceptance.accepted_at
                current.superseded_by_id = attempt.id
                self.store.save_attempt(current)
                self._audit("magic_link.superseded.v1", "denied", "link_superseded", current_request.correlation_id, attempt_id=current.id)
            attempt.state = "issued"
            attempt.provider_generated_at = generated.generated_at
            attempt.issued_at = acceptance.accepted_at
            attempt.expires_at = min(generated.expires_at, generated.generated_at + timedelta(minutes=15))
            attempt.provider_message_id = acceptance.message_id
            self.store.save_attempt(attempt)
            request = self.store.request(attempt.request_id)
            if request is not None:
                self._audit("magic_link.issued.v1", "accepted", "email_accepted", request.correlation_id, attempt_id=attempt_id)

    def confirm_magic_link(self, *, attempt_id: UUID, token_hash: str, now: datetime) -> SessionResult:
        now = utc(now)
        with self._transaction():
            attempt = self.store.attempt(attempt_id)
            if attempt is None:
                raise link_unavailable()
            if attempt.state != "issued":
                reason = "link_consumed" if attempt.state == "consumed" else "link_superseded" if attempt.state == "superseded" else "link_invalid"
                request = self.store.request(attempt.request_id)
                if request is not None:
                    self._audit("magic_link.reused.v1", "denied", reason, request.correlation_id, attempt_id=attempt_id)
                raise link_unavailable(reason)
            if not attempt.current_and_valid(now):
                attempt.state = "expired"
                self.store.save_attempt(attempt)
                request = self.store.request(attempt.request_id)
                if request is not None:
                    self._audit("magic_link.expired.v1", "denied", "link_expired", request.correlation_id, attempt_id=attempt_id)
                raise link_unavailable("link_expired")
        proof = self.provider.verify_magic_link(attempt_id=attempt_id, token_hash=token_hash, now=now)
        if (
            proof.provider != self.provider.provider
            or proof.issuer != self.provider.issuer
            or not proof.subject
            or not proof.verified_email
        ):
            with self._transaction():
                current_attempt = self.store.attempt(attempt_id)
                if current_attempt is not None:
                    request = self.store.request(current_attempt.request_id)
                    if request is None:
                        raise link_unavailable()
                    self._audit(
                        "identity.conflict.v1",
                        "denied",
                        "issuer_mismatch"
                        if proof.provider != self.provider.provider
                        or proof.issuer != self.provider.issuer
                        else "missing_verified_attribute",
                        request.correlation_id,
                        attempt_id=attempt_id,
                    )
            raise access_denied()
        try:
            normalized = normalize_email(proof.verified_email).value
        except ValueError as exc:
            raise access_denied() from exc
        if proof.revocation_handle is not None:
            try:
                self.provider.revoke_provider_session(proof.revocation_handle)
            except Exception as exc:
                raise IdentityError(
                    "auth.provider_unavailable", status=503, recovery="retry_later"
                ) from exc
        with self._transaction():
            attempt = self.store.attempt(attempt_id)
            if attempt is None:
                raise link_unavailable()
            request = self.store.request(attempt.request_id)
            if request is None:
                raise link_unavailable()
            if not attempt.current_and_valid(now):
                raise link_unavailable("link_consumed")
            user = self.store.user(attempt.product_user_id) if attempt.product_user_id else None
            invitation = self.store.invitation(attempt.invitation_id) if attempt.invitation_id else None
            existing_link = self.store.link_for_subject(proof.provider, proof.issuer, proof.subject)
            if existing_link and (user is None or existing_link.product_user_id != user.id):
                self._audit("identity.conflict.v1", "denied", "subject_conflict", request.correlation_id, attempt_id=attempt_id)
                raise access_denied()
            if user and user.normalized_email != normalized:
                self._audit("identity.conflict.v1", "denied", "email_mismatch", request.correlation_id, attempt_id=attempt_id)
                raise access_denied()
            if invitation and (invitation.status != "active" or invitation.normalized_email != normalized):
                self._audit("identity.conflict.v1", "denied", "not_eligible", request.correlation_id, attempt_id=attempt_id)
                raise access_denied()
            if user is None:
                user = ProductUser(uuid4(), normalized, status="active", created_at=now, status_changed_at=now)
                self.store.save_user(user)
                assignment = RoleAssignment(uuid4(), user.id, "user", now)
                self.store.save_role(assignment)
                if invitation:
                    invitation.status = "accepted"
                    invitation.accepted_user_id = user.id
                    invitation.accepted_at = now
                    self.store.save_invitation(invitation)
                self._audit("user.activated.v1", "accepted", "eligible", request.correlation_id, subject_user_id=user.id, attempt_id=attempt_id)
            if existing_link is None:
                link = ExternalIdentityLink(uuid4(), user.id, proof.provider, proof.issuer, proof.subject, normalized, proof.verified_at)
                self.store.save_link(link)
                self._audit("identity.linked.v1", "accepted", "eligible", request.correlation_id, subject_user_id=user.id, attempt_id=attempt_id)
            attempt.state = "consumed"
            attempt.consumed_at = now
            self.store.save_attempt(attempt)
            token = secrets.token_urlsafe(32)
            digest = hashlib.sha256(token.encode()).digest()
            session = ProductSession(uuid4(), user.id, attempt.id, digest, now)
            self.store.save_session(session)
            self._audit("magic_link.consumed.v1", "accepted", "link_consumed", request.correlation_id, subject_user_id=user.id, attempt_id=attempt_id, session_id=session.id)
            self._audit("session.started.v1", "accepted", "eligible", request.correlation_id, subject_user_id=user.id, attempt_id=attempt_id, session_id=session.id)
            return SessionResult(session.id, user.id, token, now)

    def principal(
        self,
        token: str,
        *,
        now: datetime,
        action: str = "auth.session.read",
        correlation_id: UUID | None = None,
    ) -> CurrentPrincipal:
        from umbral.application.identity.authorization import AccessControl

        return AccessControl(self.store).authorize(
            token,
            action=action,
            resource_owner_id=None,
            now=now,
            correlation_id=correlation_id,
        )

    def logout(self, token: str, *, now: datetime, correlation_id: UUID | None = None) -> None:
        digest = hashlib.sha256(token.encode()).digest()
        with self._transaction():
            session = self.store.session_by_digest(digest)
            if session is None:
                return
            if session.revoked_at is None:
                session.revoked_at = utc(now)
                session.revocation_reason = "logout"
                self.store.save_session(session)
                self._audit("session.ended.v1", "accepted", "logout", correlation_id or uuid4(), subject_user_id=session.product_user_id, session_id=session.id)

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        """Compose the foundation transaction with the persistence seam."""

        with transaction_scope(self.transaction_manager):
            with self.store.transaction():
                yield

    def _new_audit(self, event_type: str, result: str, reason: str, correlation_id: UUID, *, subject_user_id: UUID | None = None, request_id: UUID | None = None, attempt_id: UUID | None = None, session_id: UUID | None = None, action: str | None = None, provider: str | None = None, provider_event_id: str | None = None) -> AccessAuditEvent:
        AuditContext.system(
            source=event_type.replace(".", "_")[:128],
            correlation_id=correlation_id,
        )
        validate_event(event_type=event_type, result=result, reason=reason, fields={"subject_user_id": subject_user_id, "request_id": request_id, "attempt_id": attempt_id, "session_id": session_id, "action": action, "provider": provider, "provider_event_id": provider_event_id})
        return AccessAuditEvent(uuid4(), event_type, result, reason, correlation_id, datetime.now(timezone.utc), subject_user_id=subject_user_id, request_id=request_id, attempt_id=attempt_id, session_id=session_id, action=action, policy_version="identity-policy.v1" if action else None, provider=provider, provider_event_id=provider_event_id)

    def _audit(
        self,
        event_type: str,
        result: str,
        reason: str,
        correlation_id: UUID,
        *,
        subject_user_id: UUID | None = None,
        request_id: UUID | None = None,
        attempt_id: UUID | None = None,
        session_id: UUID | None = None,
        action: str | None = None,
        provider: str | None = None,
        provider_event_id: str | None = None,
    ) -> None:
        self.store.append_audit(
            self._new_audit(
                event_type,
                result,
                reason,
                correlation_id,
                subject_user_id=subject_user_id,
                request_id=request_id,
                attempt_id=attempt_id,
                session_id=session_id,
                action=action,
                provider=provider,
                provider_event_id=provider_event_id,
            )
        )

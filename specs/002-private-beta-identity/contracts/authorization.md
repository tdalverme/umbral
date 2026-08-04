# Contract: Deny-by-default Authorization

## Interface

```python
class AccessControl(Protocol):
    def authorize(
        self,
        *,
        session_token: SecretStr,
        action: Action,
        resource_owner_id: UUID | None,
        resource_type: str | None,
        resource_id: UUID | None,
        correlation_id: UUID,
    ) -> AuthorizationGrant: ...
```

The interface loads current session, user status, and roles. Callers do not pass
provider claims or cached role snapshots. A successful grant contains the
current product-user ID, action, policy version, and audit reference; it does
not expose session/token data.

## Registered Actions for This Increment

| Action | Owner required | Purpose |
| --- | ---: | --- |
| `auth.session.read` | self implicit | Resolve current protected navigation |
| `auth.session.logout` | self implicit | Revoke current session |
| `product.resource.create` | no | Representative future own-resource create |
| `product.resource.read` | yes | Representative own-resource read |
| `product.resource.update` | yes | Representative own-resource update |
| `product.resource.delete` | yes | Representative own-resource delete |
| `ops.identity.conflict.review` | no | Review bounded conflict metadata, never private content |
| `ops.identity.invitation.preload` | no | Controlled invitation preload |
| `admin.identity.user.status.change` | no | Enable/disable product access |
| `admin.identity.role.change` | no | Grant/revoke fixed roles |
| `admin.identity.bootstrap` | no | One-time zero-admin operation |

Unknown actions are denied. Later increments must register and test an action
before exposing a protected route/tool.

## Role and Ownership Matrix

`allow` below still requires an active, non-idle, non-revoked session and active
product user.

| Action | user | operator | administrator | Ownership / extra condition |
| --- | ---: | ---: | ---: | --- |
| `auth.session.read` | allow | allow | allow | current actor only |
| `auth.session.logout` | allow | allow | allow | current actor only |
| `product.resource.create` | allow | allow | allow | created owner must be current actor |
| `product.resource.read` | allow | allow | allow | only when resource owner is current actor |
| `product.resource.update` | allow | allow | allow | only when resource owner is current actor |
| `product.resource.delete` | allow | allow | allow | only when resource owner is current actor |
| `ops.identity.conflict.review` | deny | allow | allow | bounded identity metadata only |
| `ops.identity.invitation.preload` | deny | allow | allow | controlled operation, audited |
| `admin.identity.user.status.change` | deny | deny | allow | cannot silently bypass audit |
| `admin.identity.role.change` | deny | deny | allow | current active administrator |
| `admin.identity.bootstrap` | deny | deny | deny | deployment actor only; zero current admins |

Possessing multiple roles is additive only across explicit rows. No role creates
a wildcard. Operator/administrator never bypass owner checks for product
content.

## Decision Order

1. Hash and resolve the product session.
2. Deny/revoke if missing, already revoked, or idle for seven full days.
3. Load current product user; deny if not active.
4. Load current non-revoked role assignments.
5. Deny unknown roles and unknown actions.
6. Load the action rule.
7. If owner is required, deny missing, ambiguous, or nonmatching owner.
8. Require at least one current role explicitly allowed for the action.
9. Persist allow audit and touch session activity using database time.

Public, malformed, denied, failed, and background requests never touch session
activity. At the exact idle boundary the session is expired before evaluation.

## External Error Semantics

| Internal case | HTTP behavior | Information rule |
| --- | --- | --- |
| no/invalid/revoked/idle session | `401 auth.session_required` | sign-in recovery only |
| inactive user | `403 auth.access_denied` | no user-state detail |
| unknown action/role/rule | `403 auth.access_denied` | generic denial; high-signal audit |
| foreign or nonexistent resource | same `404`/generic product problem | do not distinguish existence |
| role/ownership denial | `403` or opaque product `404` by resource contract | no private content or owner disclosure |

## Audit Contract

Every decision records:

- `authorization.allowed.v1` or `authorization.denied.v1`;
- actor/product user internal ID when authenticated;
- registered action and `policy_version`;
- `resource_type` and opaque ID only when safe;
- result and stable reason;
- environment, correlation ID, and database time.

No resource content, raw route parameter, email, cookie, token, or free-form
exception is allowed.

## Mandatory Matrix Tests

Cross:

- anonymous, active user, operator, administrator, disabled user;
- active, revoked, and exactly-idle-expired session;
- own, foreign, missing, and ambiguous owner;
- every registered action plus an unknown action;
- known roles plus an injected unknown role;
- role removed/status changed after session creation.

The expected result is explicit for every cell. Any unlisted cell fails the
test as deny, and zero cross-user content access is permitted.

## Verification evidence (2026-07-31)

Executed from the `001-foundation-runtime` worktree:

```text
PYTHONPATH=src .venv/Scripts/python.exe -m pytest \
  tests/unit/identity/test_policy.py \
  tests/integration/identity/test_authorization_matrix.py \
  tests/architecture/test_identity_boundaries.py -q
3 passed
```

This verifies the finite policy registry, deny-by-default handling, ownership
checks, current status/role re-evaluation, and the identity architecture
import boundary. It is the local evidence for SC-003 and FR-014 through
FR-021.

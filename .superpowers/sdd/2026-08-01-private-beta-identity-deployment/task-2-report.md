# Task 2 report — Supabase identity proof

## Files

- `src/umbral/infrastructure/identity/supabase.py`
  - Added the narrow SDK client factory and the Supabase proof adapter mapping.
  - Generates `magiclink` links with the exact capture redirect and uses only
    `properties.hashed_token` in the capture URL.
  - Verifies the `magiclink` hash, validates the verified user/email/session/
    issuer claims, and exposes the access token only as a revocation handle.
  - Calls admin global sign-out through the adapter and translates SDK failures
    to the stable provider-unavailable failure.
- `src/umbral/infrastructure/identity/registry.py`
  - Composes the real SDK client for the Supabase provider and fails closed
    when its required URL or secret key is absent. The fake path is local-only.
- `src/umbral/application/identity/access.py`
  - Revokes a provider session before entering the local identity/session
    transaction; every revocation failure becomes provider-unavailable.
- `tests/contract/test_supabase_adapter.py`
  - New SDK-boundary contract coverage.
- `tests/contract/test_identity_provider.py`
  - Added composition and missing-configuration coverage for Supabase.
- `tests/integration/identity/test_provider_failures.py`
  - Added fail-closed coverage showing a sign-out error leaves all local
    identity state unchanged.

## RED / GREEN

- RED: `tests/contract/test_supabase_adapter.py`, provider-registry tests, and
  the local-mutation integration test failed as expected before implementation:
  11 failures, 4 existing passes. The failures were for the absent SDK client
  injection/composition, missing fail-closed configuration, and no revocation.
- RED: the dedicated global sign-out test failed with no SDK call recorded.
- RED: the encoded token-hash case failed because a raw `+` was parsed as a
  space in the capture URL.
- GREEN: the focused Task 2 slice passed with 16 tests.

## Verification

- `python -m pytest -p no:cacheprovider tests/contract/test_supabase_adapter.py tests/contract/test_identity_provider.py tests/integration/identity/test_provider_failures.py -q`
  - `16 passed`
- `python -m ruff check` on the six Task 2 source/test files
  - `All checks passed!`
- `python -m mypy` on the six Task 2 source/test files
  - `Success: no issues found in 6 source files`
- `python -m pytest -p no:cacheprovider tests/architecture/test_identity_boundaries.py tests/architecture/test_dependency_rules.py -q`
  - `7 passed`

## Self-review

- The Supabase SDK and its `Client` type remain in infrastructure; application
  code uses only `ProviderProof` and the existing proof port.
- The Supabase secret key stays at registry/composition scope and is not
  returned, logged, or passed to application/domain DTOs.
- Provider calls happen before the local mutation transaction. The only
  capture token source is `properties.hashed_token`, URL-encoded as a value.
- The approved `magiclink` compatibility type is isolated in the adapter,
  making a future Supabase migration local to that boundary.

## Concerns

- The broader identity regression command completed 51 tests, but its two
  PostgreSQL-container tests could not access the Docker named pipe in the
  sandbox. Retrying the identical command with Docker permission exceeded the
  120-second command timeout without producing a test result. This is an
  environment-verification limitation, not an observed test failure.

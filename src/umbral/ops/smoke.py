"""Provider-neutral release and identity smoke checks."""
# ruff: noqa: E501

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from time import monotonic
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

from umbral.application.identity.access import IdentityAccess
from umbral.application.identity.administration import AccessAdministration
from umbral.infrastructure.db.repositories.identity import InMemoryIdentityStore
from umbral.infrastructure.email.recording import RecordingEmailAdapter
from umbral.infrastructure.identity.fake import FakeIdentityProvider

REQUIRED_SURFACES = ("web", "api", "worker", "scheduler")
_SHA256 = "0123456789abcdef"


@dataclass(frozen=True, slots=True)
class PreviewHttpResponse:
    """Minimal, injected public-BFF response used by the remote smoke."""

    status_code: int
    headers: Mapping[str, str]
    body: bytes


@dataclass(frozen=True, slots=True)
class ObservedPreviewMessage:
    """Private mailbox observation; its capture URL must never leave this module."""

    message_id: str
    capture_url: str
    correlation_id: UUID


class PreviewSmokeObserver:
    """Operator-only boundary for invitation and provider observations."""

    def preload_invitation(self) -> str:
        raise NotImplementedError

    def wait_for_magic_link(
        self, correlation_id: UUID, *, timeout_seconds: int
    ) -> ObservedPreviewMessage:
        raise NotImplementedError

    def trigger_delivery_event(self, scenario: str, correlation_id: UUID) -> str:
        raise NotImplementedError

    def audit_projection_observed(
        self, provider_event_id: str, *, timeout_seconds: int
    ) -> bool:
        raise NotImplementedError

    def evidence_text(self) -> str:
        raise NotImplementedError


class ResendPreviewObserver(PreviewSmokeObserver):
    """Injected Resend REST observer; credentials stay inside this boundary."""

    def __init__(
        self,
        *,
        observation_token: str,
        resend_get: Callable[[str, str], object],
        preload: Callable[[], str],
        event_trigger: Callable[[str, UUID], str],
        audit_projection: Callable[[str, int], bool],
    ) -> None:
        self._observation_token = observation_token
        self._resend_get = resend_get
        self._preload = preload
        self._event_trigger = event_trigger
        self._audit_projection = audit_projection
        self._observed_message_ids: set[str] = set()

    def preload_invitation(self) -> str:
        return self._preload()

    def wait_for_magic_link(
        self, correlation_id: UUID, *, timeout_seconds: int
    ) -> ObservedPreviewMessage:
        del timeout_seconds
        listing = self._resend_get("https://api.resend.com/emails", self._observation_token)
        if not isinstance(listing, Mapping) or not isinstance(listing.get("data"), list):
            raise ValueError("Resend email listing is invalid")
        for item in listing["data"]:
            if not isinstance(item, Mapping) or not isinstance(item.get("id"), str):
                continue
            message_id = item["id"]
            if message_id in self._observed_message_ids:
                continue
            detail = self._resend_get(
                f"https://api.resend.com/emails/{message_id}", self._observation_token
            )
            capture_url = _capture_url_from_resend_detail(detail)
            if capture_url:
                self._observed_message_ids.add(message_id)
                return ObservedPreviewMessage(message_id, capture_url, correlation_id)
        raise ValueError("Resend message was not observed")

    def trigger_delivery_event(self, scenario: str, correlation_id: UUID) -> str:
        if scenario not in {"delivered", "bounced", "complained"}:
            raise ValueError("unknown Resend test event")
        return self._event_trigger(scenario, correlation_id)

    def audit_projection_observed(
        self, provider_event_id: str, *, timeout_seconds: int
    ) -> bool:
        return self._audit_projection(provider_event_id, timeout_seconds)

    def evidence_text(self) -> str:
        return ""


@dataclass(frozen=True, slots=True)
class PreviewSmokeConfig:
    """Private input to a bounded public-preview journey."""

    public_web_base_url: str
    release_id: str
    manifest_sha256: str
    artifact_digests: Mapping[str, str]
    invited_email: str
    resend_observation_token: str
    timeout_seconds: int

    def __post_init__(self) -> None:
        parsed = urlparse(self.public_web_base_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("preview smoke requires one public HTTPS web origin")
        if not self.release_id or len(self.release_id) > 100:
            raise ValueError("preview smoke requires a release ID")
        if not _is_sha256(self.manifest_sha256):
            raise ValueError("preview smoke requires a manifest checksum")
        if set(self.artifact_digests) != {"web", "runtime"} or not all(
            _is_digest(value) for value in self.artifact_digests.values()
        ):
            raise ValueError("preview smoke requires exact web and runtime digests")
        if not self.invited_email or not self.resend_observation_token:
            raise ValueError("preview smoke requires private invitation and observation inputs")
        if not 1 <= self.timeout_seconds <= 300:
            raise ValueError("preview smoke timeout must be bounded")


@dataclass(frozen=True, slots=True)
class PreviewSmokeCheck:
    scenario: str
    code: str
    provider_id: str | None
    correlation_id: UUID
    observed_at: datetime
    duration_ms: int

    @property
    def passed(self) -> bool:
        return self.code == "smoke.ok"

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "scenario": self.scenario,
            "code": self.code,
            "correlation_id": str(self.correlation_id),
            "observed_at": self.observed_at.isoformat().replace("+00:00", "Z"),
            "duration_ms": self.duration_ms,
        }
        if self.provider_id is not None:
            payload["provider_id"] = self.provider_id
        return payload


@dataclass(frozen=True, slots=True)
class PreviewSmokeReport:
    checks: tuple[PreviewSmokeCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    def to_dict(self) -> dict[str, object]:
        return {"passed": self.passed, "checks": [check.to_dict() for check in self.checks]}


@dataclass(frozen=True, slots=True)
class SmokeCheck:
    name: str
    passed: bool
    code: str


@dataclass(frozen=True, slots=True)
class SmokeReport:
    checks: tuple[SmokeCheck, ...]
    product_data_used: bool = False

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)


def run_smoke(checks: Mapping[str, Callable[[], bool]]) -> SmokeReport:
    """Run a closed set of local checks and normalize failures."""

    required = (*REQUIRED_SURFACES, "extensions", "reference_job", "synthetic_object")
    results: list[SmokeCheck] = []
    for name in required:
        check = checks.get(name)
        if check is None:
            results.append(SmokeCheck(name, False, "smoke.missing_check"))
            continue
        try:
            passed = bool(check())
        except Exception:
            passed = False
        results.append(SmokeCheck(name, passed, "smoke.ok" if passed else "smoke.failed"))
    return SmokeReport(tuple(results))


def run_identity_smoke() -> dict[str, str]:
    store = InMemoryIdentityStore()
    AccessAdministration(store).preload_invitation("smoke@example.test")
    access = IdentityAccess(store, FakeIdentityProvider(), RecordingEmailAdapter())
    now = datetime.now(timezone.utc)
    access.request_magic_link(email="smoke@example.test", origin_fingerprint="smoke", correlation_id=uuid4(), now=now)
    return {"result": "accepted", "sessions": str(store.session_count()), "synthetic": "true"}


def run_preview_identity_smoke(
    config: PreviewSmokeConfig,
    *,
    http: Callable[[str, str, bytes | None], PreviewHttpResponse],
    observer: PreviewSmokeObserver,
    now: Callable[[], datetime] | None = None,
) -> PreviewSmokeReport:
    """Exercise the preview BFF while retaining all secret provider material locally."""

    clock = now or (lambda: datetime.now(timezone.utc))
    checks: list[PreviewSmokeCheck] = []

    def check(
        scenario: str,
        operation: Callable[[], tuple[str | None, bool]],
    ) -> bool:
        started = monotonic()
        correlation_id = uuid4()
        provider_id: str | None = None
        try:
            provider_id, passed = operation()
        except Exception:
            passed = False
        checks.append(
            PreviewSmokeCheck(
                scenario=scenario,
                code="smoke.ok" if passed else "smoke.failed",
                provider_id=provider_id if passed else None,
                correlation_id=correlation_id,
                observed_at=_utc(clock()),
                duration_ms=max(0, round((monotonic() - started) * 1000)),
            )
        )
        return passed

    runtime_ok = check(
        "runtime_identity", lambda: (None, _runtime_identity_matches(config, http))
    )
    invitation_ok = check("invitation", lambda: (_operator_invitation(observer), True))

    correlation_id = uuid4()
    message: ObservedPreviewMessage | None = None

    def request_invited() -> tuple[str | None, bool]:
        nonlocal message
        accepted = _request_magic_link(config, http, config.invited_email)
        message = observer.wait_for_magic_link(
            correlation_id, timeout_seconds=config.timeout_seconds
        )
        return message.message_id, accepted and message.correlation_id == correlation_id

    invited_ok = check("invited", request_invited)
    capture: tuple[str, str] | None = None
    if message is not None:
        try:
            capture = _capture_parameters(config, message.capture_url)
        except ValueError:
            capture = None

    scanner_ok = check(
        "scanner_prefetch",
        lambda: (
            message.message_id if message else None,
            capture is not None
            and message is not None
            and _public_response(http, "GET", message.capture_url, None).status_code == 303,
        ),
    )
    confirmation_ok = check(
        "explicit_confirmation",
        lambda: (
            message.message_id if message else None,
            capture is not None and _confirm_magic_link(config, http, *capture) == 204,
        ),
    )
    check(
        "single_use",
        lambda: (
            message.message_id if message else None,
            capture is not None and _confirm_magic_link(config, http, *capture) >= 400,
        ),
    )
    check(
        "repeat",
        lambda: (None, _request_magic_link(config, http, config.invited_email)),
    )
    check(
        "non_invited",
        lambda: (
            None,
            _request_magic_link(config, http, _non_invited_email(config.invited_email)),
        ),
    )
    check(
        "authorization",
        lambda: (None, _public_response(http, "GET", _url(config, "/api/auth/session"), None).status_code == 200),
    )
    check(
        "logout",
        lambda: (None, _public_response(http, "POST", _url(config, "/api/auth/logout"), None).status_code == 204),
    )
    check(
        "idle_expiry",
        lambda: (
            None,
            _public_response(http, "GET", _url(config, "/api/auth/session?idle=boundary"), None).status_code == 401,
        ),
    )
    for scenario in ("delivered", "bounced", "complained"):
        event_correlation = uuid4()

        def delivery_operation(
            scenario: str = scenario, correlation_id: UUID = event_correlation
        ) -> tuple[str | None, bool]:
            return _delivery_event(observer, scenario, correlation_id, config.timeout_seconds)

        check(
            scenario,
            delivery_operation,
        )
    check(
        "redaction",
        lambda: (
            None,
            _redaction_clean(
                observer.evidence_text(),
                config.invited_email,
                config.resend_observation_token,
                capture[1] if capture else "",
            ),
        ),
    )
    del runtime_ok, invitation_ok, invited_ok, scanner_ok, confirmation_ok
    return PreviewSmokeReport(tuple(checks))


def _runtime_identity_matches(
    config: PreviewSmokeConfig,
    http: Callable[[str, str, bytes | None], PreviewHttpResponse],
) -> bool:
    health = _public_response(http, "GET", _url(config, "/health"), None)
    ready = _public_response(http, "GET", _url(config, "/ready"), None)
    version = _public_response(http, "GET", _url(config, "/version"), None)
    if health.status_code != 200 or ready.status_code != 200 or version.status_code != 200:
        return False
    health_payload = _json_object(health.body)
    ready_payload = _json_object(ready.body)
    version_payload = _json_object(version.body)
    return (
        health_payload == {"status": "alive"}
        and ready_payload.get("surface") == "web"
        and ready_payload.get("state") in {"ready", "degraded"}
        and ready_payload.get("release_id") == config.release_id
        and version_payload.get("surface") == "web"
        and version_payload.get("release_id") == config.release_id
        and version_payload.get("manifest_sha256") == config.manifest_sha256
        and version_payload.get("artifact_digest") == config.artifact_digests["web"]
    )


def _operator_invitation(observer: PreviewSmokeObserver) -> str:
    invitation_id = observer.preload_invitation()
    return str(UUID(invitation_id))


def _request_magic_link(
    config: PreviewSmokeConfig,
    http: Callable[[str, str, bytes | None], PreviewHttpResponse],
    email: str,
) -> bool:
    response = _public_response(
        http,
        "POST",
        _url(config, "/api/auth/magic-link-requests"),
        ("{\"email\":\"" + email + "\"}").encode(),
    )
    return response.status_code == 202


def _capture_parameters(config: PreviewSmokeConfig, capture_url: str) -> tuple[str, str]:
    parsed = urlparse(capture_url)
    if f"{parsed.scheme}://{parsed.netloc}" != config.public_web_base_url.rstrip("/"):
        raise ValueError("capture URL left the public web origin")
    query = parse_qs(parsed.query, strict_parsing=True)
    attempt_id = query.get("attempt_id", [""])[0]
    token_hash = query.get("token_hash", [""])[0]
    UUID(attempt_id)
    if not 32 <= len(token_hash) <= 512:
        raise ValueError("capture token is invalid")
    return attempt_id, token_hash


def _confirm_magic_link(
    config: PreviewSmokeConfig,
    http: Callable[[str, str, bytes | None], PreviewHttpResponse],
    attempt_id: str,
    token_hash: str,
) -> int:
    response = _public_response(
        http,
        "POST",
        _url(config, "/api/auth/confirmations"),
        (
            "{\"attemptId\":\""
            + attempt_id
            + "\",\"tokenHash\":\""
            + token_hash
            + "\"}"
        ).encode(),
    )
    return response.status_code


def _delivery_event(
    observer: PreviewSmokeObserver,
    scenario: str,
    correlation_id: UUID,
    timeout_seconds: int,
) -> tuple[str | None, bool]:
    provider_event_id = observer.trigger_delivery_event(scenario, correlation_id)
    return provider_event_id, observer.audit_projection_observed(
        provider_event_id, timeout_seconds=timeout_seconds
    )


def _public_response(
    http: Callable[[str, str, bytes | None], PreviewHttpResponse],
    method: str,
    url: str,
    body: bytes | None,
) -> PreviewHttpResponse:
    return http(method, url, body)


def _url(config: PreviewSmokeConfig, path: str) -> str:
    return config.public_web_base_url.rstrip("/") + path


def _json_object(body: bytes) -> Mapping[str, object]:
    import json

    payload = json.loads(body)
    if not isinstance(payload, Mapping):
        raise ValueError("response is not an object")
    return payload


def _capture_url_from_resend_detail(detail: object) -> str | None:
    if not isinstance(detail, Mapping):
        return None
    values = (detail.get("html"), detail.get("text"))
    for value in values:
        if not isinstance(value, str):
            continue
        match = re.search(r"https://[^\s\"'<>]+/auth/capture\?[^\s\"'<>]+", value)
        if match:
            return match.group(0)
    return None


def _non_invited_email(invited_email: str) -> str:
    local, separator, domain = invited_email.partition("@")
    if not separator:
        return "not-invited@example.invalid"
    return f"not-invited-{uuid4().hex[:12]}@{domain}"


def _redaction_clean(evidence: str, *canaries: str) -> bool:
    return all(not canary or canary not in evidence for canary in canaries)


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in _SHA256 for character in value)


def _is_digest(value: str) -> bool:
    return value.startswith("sha256:") and _is_sha256(value.removeprefix("sha256:"))


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("smoke timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def main(argv: list[str] | None = None) -> int:
    """Run the synthetic smoke locally or a preview journey with an injected observer."""

    parser = argparse.ArgumentParser(prog="python -m umbral.ops.smoke")
    subparsers = parser.add_subparsers(dest="mode", required=True)
    subparsers.add_parser("local")
    preview = subparsers.add_parser("preview")
    preview.add_argument("--base-url", required=True)
    preview.add_argument("--manifest-path", required=True)
    preview.add_argument("--timeout-seconds", type=int, default=120)
    args = parser.parse_args(argv)
    if args.mode == "local":
        print(json.dumps(run_identity_smoke(), separators=(",", ":")))
        return 0
    try:
        manifest = _json_object(open(args.manifest_path, "rb").read())  # noqa: PTH123
        config = PreviewSmokeConfig(
            public_web_base_url=args.base_url,
            release_id=_required_manifest_string(manifest, "release_id"),
            manifest_sha256=_manifest_sha256(args.manifest_path),
            artifact_digests=_manifest_digests(manifest),
            invited_email=os.environ.get("UMBRAL_SMOKE_INVITEE", ""),
            resend_observation_token=os.environ.get(
                "UMBRAL_SMOKE_RESEND_OBSERVATION_TOKEN", ""
            ),
            timeout_seconds=args.timeout_seconds,
        )
        observer = _load_preview_observer(config)
        report = run_preview_identity_smoke(config, http=_urllib_http, observer=observer)
    except Exception:
        print('{"passed":false,"code":"smoke.preview_unavailable"}')
        return 1
    print(json.dumps(report.to_dict(), separators=(",", ":")))
    return 0 if report.passed else 1


def _load_preview_observer(config: PreviewSmokeConfig) -> PreviewSmokeObserver:
    raw = os.environ.get("UMBRAL_PREVIEW_SMOKE_OBSERVER_FACTORY", "")
    module_name, separator, attribute = raw.partition(":")
    if not separator or not module_name or not attribute:
        raise ValueError("preview observer factory is unavailable")
    factory = getattr(importlib.import_module(module_name), attribute)
    observer = factory(config)
    if not isinstance(observer, PreviewSmokeObserver):
        raise TypeError("preview observer is invalid")
    return observer


def _urllib_http(method: str, url: str, body: bytes | None) -> PreviewHttpResponse:
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen

    request = Request(
        url,
        method=method,
        data=body,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    try:
        with urlopen(request, timeout=30) as response:  # noqa: S310
            return PreviewHttpResponse(
                int(response.status), dict(response.headers.items()), response.read()
            )
    except HTTPError as error:
        return PreviewHttpResponse(int(error.code), dict(error.headers.items()), error.read())


def _manifest_sha256(path: str) -> str:
    import hashlib
    from pathlib import Path

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _required_manifest_string(manifest: Mapping[str, object], name: str) -> str:
    value = manifest.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError("manifest field unavailable")
    return value


def _manifest_digests(manifest: Mapping[str, object]) -> dict[str, str]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError("manifest artifacts unavailable")
    digests: dict[str, str] = {}
    for name in ("web", "runtime"):
        artifact = artifacts.get(name)
        if not isinstance(artifact, Mapping):
            raise ValueError("manifest artifact unavailable")
        digest = artifact.get("digest")
        if not isinstance(digest, str):
            raise ValueError("manifest digest unavailable")
        digests[name] = digest
    return digests


if __name__ == "__main__":
    raise SystemExit(main())

"""Sanitized conformance checks for managed preview dependencies."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class DependencyCheck:
    name: str
    passed: bool
    code: str
    evidence: dict[str, str] | None = None


@dataclass(frozen=True, slots=True)
class PreviewDependencyReport:
    checks: tuple[DependencyCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "checks": [_check_dict(check) for check in self.checks],
        }


PostgresClient = Callable[[str], object]
RedisClient = Callable[[str, bytes | None], object]
ObjectStoreClient = Callable[[str, str, str, bytes | None], object]
HttpClient = Callable[[str, str, dict[str, str], bytes | None], object]


@dataclass(frozen=True, slots=True)
class PreviewDependencyClients:
    """Narrow provider operations, injectable for deterministic gate tests."""

    postgres: PostgresClient
    redis: RedisClient
    object_store: ObjectStoreClient
    http: HttpClient

    @classmethod
    def from_environment(
        cls, config: Mapping[str, str]
    ) -> PreviewDependencyClients:
        return cls(
            postgres=_postgres_client(config["DATABASE_URL"]),
            redis=_redis_client(config["REDIS_URL"]),
            object_store=_object_store_client(config),
            http=_http_client,
        )


def run_preview_dependency_conformance(
    *,
    config: Mapping[str, str],
    manifest_revision: str,
    clients: PreviewDependencyClients,
) -> PreviewDependencyReport:
    """Run closed, non-product probes and return secret-free evidence."""

    checks: list[DependencyCheck] = []
    checks.append(
        _check("postgres.server_major", lambda: clients.postgres("server_major") == 17)
    )
    checks.append(
        _check(
            "postgres.alembic_revision",
            lambda: clients.postgres("alembic_revision") == manifest_revision,
        )
    )
    checks.append(
        _check(
            "postgres.extensions",
            lambda: {"postgis", "vector"}.issubset(
                _extension_names(clients.postgres("extensions"))
            ),
        )
    )

    opaque_message = f"provider-conformance-{uuid4().hex}".encode()
    checks.append(
        _check(
            "redis.round_trip",
            lambda: _redis_round_trip(clients.redis, opaque_message),
        )
    )

    object_key = f"provider-conformance/{uuid4().hex}"
    object_body = b"provider-conformance"
    object_bucket = config.get("OBJECT_STORE_BUCKET", "")
    checks.append(
        _check(
            "object_store.round_trip",
            lambda: _primary_object_round_trip(
                clients.object_store, object_bucket, object_key, object_body
            ),
        )
    )

    checks.append(
        _check(
            "grafana.otlp",
            lambda: _accepted(
                clients.http(
                    "POST",
                    _otlp_trace_endpoint(config.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")),
                    _otlp_headers(config.get("OTEL_EXPORTER_OTLP_HEADERS")),
                    b"",
                )
            ),
        )
    )
    checks.append(_sentry_check(clients.http, config.get("SENTRY_DSN", "")))

    issuer = config.get("IDENTITY_ISSUER", "")
    checks.append(
        _check(
            "supabase.issuer",
            lambda: issuer == f"{config.get('SUPABASE_URL', '').rstrip('/')}/auth/v1",
        )
    )
    checks.append(
        _check(
            "supabase.reachability",
            lambda: _accepted(
                clients.http(
                    "GET",
                    f"{issuer.rstrip('/')}/health",
                    {"apikey": config.get("SUPABASE_SECRET_KEY", "")},
                    None,
                )
            ),
        )
    )
    checks.append(
        _check(
            "resend.reachability",
            lambda: _accepted(
                clients.http(
                    "GET",
                    "https://api.resend.com/domains",
                    {"Authorization": f"Bearer {config.get('RESEND_API_KEY', '')}"},
                    None,
                )
            ),
        )
    )
    return PreviewDependencyReport(tuple(checks))


def _check(name: str, probe: Callable[[], bool]) -> DependencyCheck:
    try:
        passed = bool(probe())
    except Exception:
        passed = False
    code = "dependency.ok" if passed else "dependency.failed"
    return DependencyCheck(name, passed, code)


def _check_dict(check: DependencyCheck) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": check.name,
        "passed": check.passed,
        "code": check.code,
    }
    if check.evidence is not None:
        payload["evidence"] = check.evidence
    return payload


def _extension_names(value: object) -> set[str]:
    if not isinstance(value, (frozenset, list, set, tuple)):
        raise ValueError("extensions response is invalid")
    return {str(name) for name in value}


def _redis_round_trip(redis: RedisClient, message: bytes) -> bool:
    return (
        redis("ping", None) == "PONG"
        and redis("enqueue", message) == "queued"
        and redis("dequeue", None) == message
    )


def _primary_object_round_trip(
    object_store: ObjectStoreClient, bucket: str, key: str, body: bytes
) -> bool:
    written = object_store("put", bucket, key, body)
    stat = object_store("stat", bucket, key, None)
    retrieved = object_store("get", bucket, key, None)
    return (
        isinstance(written, Mapping)
        and isinstance(stat, Mapping)
        and stat.get("size_bytes") == len(body)
        and retrieved == body
    )


def _otlp_trace_endpoint(endpoint: str) -> str:
    return f"{endpoint.rstrip('/').removesuffix('/v1/traces')}/v1/traces"


def _otlp_headers(value: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/x-protobuf"}
    if not value:
        return headers
    for item in value.split(","):
        name, separator, header_value = item.partition("=")
        if not separator or not name.strip() or "\n" in header_value:
            raise ValueError("invalid OTLP headers")
        headers[name.strip()] = header_value.strip()
    return headers


def _accepted(response: object) -> bool:
    status_code = _response_status(response)
    return status_code is not None and 200 <= status_code < 300


def _sentry_check(http: HttpClient, dsn: str) -> DependencyCheck:
    try:
        event_id = _accepted_sentry_event(http, dsn)
    except Exception:
        event_id = None
    return DependencyCheck(
        "sentry.event",
        event_id is not None,
        "dependency.ok" if event_id is not None else "dependency.failed",
        {"event_id": event_id} if event_id is not None else None,
    )


def _accepted_sentry_event(http: HttpClient, dsn: str) -> str | None:
    parsed = urlparse(dsn)
    project_id = parsed.path.strip("/")
    if (
        not parsed.scheme
        or not parsed.hostname
        or not parsed.username
        or not project_id
    ):
        return None
    url = f"{parsed.scheme}://{parsed.hostname}/api/{project_id}/store/"
    event = json.dumps(
        {
            "event_id": uuid4().hex,
            "message": "preview dependency probe",
            "level": "info",
            "tags": {"probe": "dependency-conformance"},
        },
        separators=(",", ":"),
    ).encode()
    response = http(
        "POST",
        url,
        {
            "Content-Type": "application/json",
            "X-Sentry-Auth": (
                "Sentry sentry_version=7, sentry_key=" f"{parsed.username}"
            ),
        },
        event,
    )
    return _response_event_id(response) if _accepted(response) else None


def _response_status(response: object) -> int | None:
    if isinstance(response, int):
        return response
    if isinstance(response, Mapping):
        value = response.get("status_code")
        return value if isinstance(value, int) else None
    return None


def _response_event_id(response: object) -> str | None:
    if not isinstance(response, Mapping):
        return None
    value = response.get("event_id")
    return value if isinstance(value, str) and value else None


def _postgres_client(database_url: str) -> PostgresClient:
    import psycopg

    queries = {
        "server_major": "SHOW server_version_num",
        "alembic_revision": "SELECT version_num FROM alembic_version",
        "extensions": (
            "SELECT extname FROM pg_extension "
            "WHERE extname IN ('postgis', 'vector')"
        ),
    }

    def run(operation: str) -> object:
        with psycopg.connect(database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(queries[operation])
                if operation == "server_major":
                    row = cursor.fetchone()
                    if row is None:
                        raise ValueError("server version response is empty")
                    return int(str(row[0])) // 10000
                if operation == "alembic_revision":
                    row = cursor.fetchone()
                    if row is None:
                        raise ValueError("alembic revision response is empty")
                    return str(row[0])
                return {str(row[0]) for row in cursor.fetchall()}

    return run


def _redis_client(redis_url: str) -> RedisClient:
    from redis import Redis

    client = Redis.from_url(redis_url, decode_responses=False)
    key = f"umbral:provider-conformance:{uuid4().hex}"

    def run(operation: str, value: bytes | None) -> object:
        if operation == "ping":
            return "PONG" if client.ping() else ""
        if operation == "enqueue":
            assert value is not None
            client.lpush(key, value)
            return "queued"
        if operation == "dequeue":
            return client.rpop(key)
        raise ValueError("unknown redis operation")

    return run


def _object_store_client(config: Mapping[str, str]) -> ObjectStoreClient:
    import boto3

    client = boto3.client(
        "s3",
        endpoint_url=config.get("OBJECT_STORE_ENDPOINT_URL"),
        aws_access_key_id=config.get("OBJECT_STORE_ACCESS_KEY"),
        aws_secret_access_key=config.get("OBJECT_STORE_SECRET_KEY"),
    )

    def run(operation: str, bucket: str, key: str, body: bytes | None) -> object:
        if operation == "put":
            assert body is not None
            client.put_object(Bucket=bucket, Key=key, Body=body)
            return {"size_bytes": len(body)}
        if operation == "stat":
            head_response = client.head_object(Bucket=bucket, Key=key)
            return {"size_bytes": int(head_response["ContentLength"])}
        if operation == "get":
            get_response = client.get_object(Bucket=bucket, Key=key)
            return get_response["Body"].read()
        if operation == "copy":
            assert body is not None
            source_bucket, source_key = body.decode().split("/", maxsplit=1)
            client.copy_object(
                Bucket=bucket,
                Key=key,
                CopySource={"Bucket": source_bucket, "Key": source_key},
            )
            response = client.head_object(Bucket=bucket, Key=key)
            return {"size_bytes": int(response["ContentLength"])}
        raise ValueError("unknown object-store operation")

    return run


def _http_client(
    method: str, url: str, headers: dict[str, str], body: bytes | None
) -> object:
    request = Request(url, method=method, headers=headers, data=body)
    try:
        with urlopen(request, timeout=15) as response:  # noqa: S310
            response_body = response.read()
            payload = _safe_json(response_body)
            result: dict[str, object] = {"status_code": int(response.status)}
            if isinstance(payload.get("id"), str):
                result["event_id"] = payload["id"]
            return result
    except HTTPError as error:
        return {"status_code": int(error.code)}


def _safe_json(body: bytes) -> Mapping[str, object]:
    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, Mapping) else {}


def main() -> int:
    config = {
        name: value
        for name, value in os.environ.items()
        if name
        in {
            "DATABASE_URL",
            "REDIS_URL",
            "OBJECT_STORE_BUCKET",
            "OBJECT_STORE_ENDPOINT_URL",
            "OBJECT_STORE_ACCESS_KEY",
            "OBJECT_STORE_SECRET_KEY",
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "OTEL_EXPORTER_OTLP_HEADERS",
            "SENTRY_DSN",
            "SUPABASE_URL",
            "SUPABASE_SECRET_KEY",
            "IDENTITY_ISSUER",
            "RESEND_API_KEY",
        }
    }
    manifest_revision = os.environ.get("UMBRAL_MANIFEST_DATABASE_REVISION", "")
    report = run_preview_dependency_conformance(
        config=config,
        manifest_revision=manifest_revision,
        clients=PreviewDependencyClients.from_environment(config),
    )
    print(json.dumps(report.to_dict(), separators=(",", ":")))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

# Contract: Operational Signals

## Closed Allowlist

Application code may emit only the following fields through the safe telemetry
facade:

| Field | Type | Notes |
| --- | --- | --- |
| `correlation_id` | UUID | Multi-step flow |
| `request_id` | UUID, optional | One HTTP request |
| `service_name` | enum | `web`, `api`, `worker`, `scheduler` |
| `environment` | enum | `local`, `preview`, `production` |
| `release_id` | bounded string | Release manifest identity |
| `operation` | bounded enum/string | Registered operation name |
| `state` | bounded enum/string | Registered state |
| `status_code` | integer, optional | HTTP or normalized internal status |
| `duration_ms` | nonnegative integer | Rounded duration |
| `route_template` | bounded string, optional | Template only, never resolved path |
| `http_method` | enum, optional | Standard method |
| `error_code` | bounded string, optional | Stable normalized code |
| `job_type` | bounded string, optional | Registered type |
| `job_state` | enum, optional | Durable job state |
| `attempt_number` | integer, optional | Bounded attempt |
| `queue_lag_ms` | nonnegative integer, optional | Aggregate timing |
| `object_operation` | enum, optional | `put`, `get`, `stat`, `reconcile` |
| `content_class` | enum, optional | Non-sensitive application class |

No facade method accepts an arbitrary attributes dictionary.

## Always Rejected

- request/response/job bodies or fragments;
- query strings and parameter values;
- raw/resolved URLs or object keys;
- headers, cookies, tokens and credentials;
- email, IP address, free text, address or listing content;
- SQL text with bound values or ORM object representations;
- exception message, arguments, locals or attachments;
- any field not present in the allowlist.

Route templates and normalized error codes replace raw paths and exception
messages. Rejection is default even if a field has not been classified as
personal.

## Signal Behavior

- JSON logs, spans, metrics and Sentry events apply the same allowlist.
- Correlation propagates request -> job -> object operation and is returned to
  the caller where an HTTP contract exists.
- Trace sampling never changes redaction.
- Sentry `sendDefaultPii`, replay and attachments are disabled.
- A defensive `beforeSend` drops unknown event fields and scrubs exception
  text.
- Exporter unavailability never fails a product transaction or job effect.
- Export failures produce a bounded local counter/state and degrade readiness;
  they do not recursively emit the rejected payload.
- Probe and version endpoints use `Cache-Control: no-store`.

## Contract Tests

Use canary secrets and personal-looking values in:

- request body, query, path parameter, headers and cookies;
- invalid configuration values;
- job target/input and exception;
- object key/provider response;
- database exception;
- release and access-control failure.

Capture stdout JSON, in-memory spans and Sentry `beforeSend` output. The test
passes only if every allowed field is correct and every canary/unknown field is
absent. Search serialized nested structures, not only top-level keys.

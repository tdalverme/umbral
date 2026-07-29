# Contract: Versioned Object Storage

## Purpose

Provide immutable, integrity-checked object versions without exposing
filesystem, S3, bucket or credential details to domain/application callers.

## Interface

```python
@dataclass(frozen=True)
class ObjectVersionRef:
    object_id: UUID
    version_id: UUID
    sha256: str
    size_bytes: int
    content_type: str

class ObjectStore(Protocol):
    def put_if_absent(
        self,
        *,
        storage_key: str,
        body: BinaryIO,
        sha256: str,
        size_bytes: int,
        content_type: str,
    ) -> ProviderObjectRef: ...

    def open(self, provider_ref: ProviderObjectRef) -> BinaryIO: ...
    def stat(self, provider_ref: ProviderObjectRef) -> ObjectInfo: ...
```

Application callers use a deeper `VersionedObjects` module that creates
pending metadata, invokes this port, verifies the result and exposes only
available `ObjectVersionRef` values. Callers never construct storage keys.

## Observable Semantics

- `object_id` is a stable logical identity.
- `version_id` is an immutable application-generated version.
- First write of a version and matching content succeeds.
- Repeating the same version, SHA-256, size and content type returns the
  existing version without rewriting it.
- Repeating a version with any different declared or computed property raises
  `ObjectVersionConflict`.
- A body whose computed SHA-256 or size differs from the declaration is
  rejected before the version becomes available.
- `open` returns exactly the bytes of the requested version and verifies the
  hash while streaming.
- Missing bytes, provider mismatch or read corruption raises
  `ObjectIntegrityError` and emits a sanitized operational failure.
- There is no implicit latest-version read.
- `list`, delete, overwrite, signed URL and public ACL are not part of this
  Interface.

## Content and Key Policy

- SHA-256 is lowercase hexadecimal over the stored bytes.
- Content type is normalized and chosen from an application allowlist.
- Storage keys are derived from opaque IDs, for example
  `objects/<object_id>/<version_id>`, and are never logged or traced.
- Remote buckets are private and deny public ACLs.
- Filesystem writes use create-without-overwrite plus atomic rename.
- S3-compatible writes use conditional creation where supported and always
  verify remote stat/checksum; correctness does not depend on ETag.

## Interruption Recovery

1. Persist pending metadata and commit.
2. Write immutable bytes outside the DB transaction.
3. Stat and verify the remote object.
4. Mark metadata available and commit.

If the process stops:

- pending plus matching bytes is completed by the reconciler;
- pending plus absent bytes is retried within a bounded policy;
- pending plus conflicting bytes becomes failed and alerts;
- readers never observe pending or failed versions.

Compensating delete is not required for correctness and is not exposed through
the public port. Provider administration may quarantine an orphan only after
evidence is retained.

## Adapters

| Adapter | Use | Required behavior |
| --- | --- | --- |
| `FilesystemObjectStore` | local and fast contract tests | exclusive create, atomic rename, stat, streaming hash |
| `S3ObjectStore` | preview/production R2 | private bucket, conditional put when supported, exact provider ref, stat/checksum |
| MinIO-backed `S3ObjectStore` | integration tests | exercises S3 wire behavior; not a third application adapter |

The same parameterized conformance suite runs against filesystem and
MinIO-backed S3. A remote smoke runs a bounded synthetic version in each
environment and retains no product data.

## Conformance Cases

1. first write/read round trip preserves bytes, type, size and hash;
2. two versions of one object remain independently readable;
3. same-version same-content retry is idempotent;
4. same-version different-content retry conflicts;
5. declared hash and size mismatches fail closed;
6. concurrent same-version writes expose exactly one version;
7. interrupted pending write is completed or marked failed deterministically;
8. a corrupted/missing provider object is never returned as valid;
9. provider credentials and storage keys never enter telemetry;
10. local and S3 adapters return the same application-level outcomes.

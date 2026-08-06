"""Deterministic test double for the ImportSource seam.

Returns a pre-built parsed batch keyed by file name, or rejects unknown input,
so application and worker tests never need a real file.
"""

from __future__ import annotations

from umbral.application.ingestion.contracts import (
    BatchRejected,
    ImportFormat,
    ParsedBatch,
)


class FakeImportSource:
    def __init__(self, batches: dict[str, ParsedBatch] | None = None) -> None:
        self.batches: dict[str, ParsedBatch] = dict(batches or {})

    def register(self, file_name: str, parsed: ParsedBatch) -> None:
        self.batches[file_name] = parsed

    def read_batch(
        self, *, raw: bytes, file_format: ImportFormat, file_name: str
    ) -> ParsedBatch:
        del raw, file_format
        parsed = self.batches.get(file_name)
        if parsed is None:
            raise BatchRejected("file.parse_error", f"no fake batch for {file_name!r}")
        return parsed

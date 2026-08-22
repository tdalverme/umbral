"""Application ports for the local playground adapters."""

from __future__ import annotations

from typing import Protocol

from umbral.application.playground.contracts import (
    ConversationRequest,
    ConversationTrace,
    GeoInspection,
    GeoInspectionRequest,
)


class ConversationRunner(Protocol):
    def run(self, request: ConversationRequest) -> ConversationTrace: ...


class GeoInspector(Protocol):
    def inspect(self, request: GeoInspectionRequest) -> GeoInspection: ...

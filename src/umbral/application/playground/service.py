"""Use cases exposed by the local playground."""

from __future__ import annotations

from umbral.application.playground.contracts import (
    ConversationRequest,
    ConversationTrace,
    GeoInspection,
    GeoInspectionRequest,
)
from umbral.application.playground.ports import ConversationRunner, GeoInspector


class PlaygroundService:
    """Keep transport concerns out of the local runner and geo inspector."""

    def __init__(
        self,
        *,
        conversation: ConversationRunner,
        geo: GeoInspector,
    ) -> None:
        self.conversation = conversation
        self.geo = geo

    def run_conversation(self, request: ConversationRequest) -> ConversationTrace:
        return self.conversation.run(request)

    def inspect_listing_geo(self, request: GeoInspectionRequest) -> GeoInspection:
        return self.geo.inspect(request)

"""Preference service seam for the single conversation stack."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from umbral.application.preferences.contracts import (
    BindingDraft,
    PreferenceAuthority,
    PreferenceChange,
    PreferenceView,
)


class PreferenceServiceLike(Protocol):
    """The preference service seam the conversation mutates through."""

    def record_expression(
        self,
        *,
        profile_id: UUID,
        source_message_id: UUID | None,
        subject_key: str,
        raw_text: str,
        authority: PreferenceAuthority,
        binding_drafts: tuple[BindingDraft, ...],
        correlation_id: UUID,
    ) -> PreferenceChange: ...

    def revise_expression(
        self,
        *,
        profile_id: UUID,
        previous_expression_id: UUID,
        source_message_id: UUID | None,
        raw_text: str,
        authority: PreferenceAuthority,
        binding_drafts: tuple[BindingDraft, ...],
        correlation_id: UUID,
    ) -> PreferenceChange: ...

    def set_explicit_preference(
        self,
        *,
        profile_id: UUID,
        source_message_id: UUID | None,
        concept_key: str,
        raw_text: str,
        binding_draft: BindingDraft,
        correlation_id: UUID,
    ) -> PreferenceChange: ...

    def withdraw_expression(
        self,
        *,
        profile_id: UUID,
        expression_id: UUID,
        correlation_id: UUID,
    ) -> PreferenceChange: ...

    def active_view(self, profile_id: UUID) -> tuple[PreferenceView, ...]: ...

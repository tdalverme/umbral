"""Durable preference expressions and versioned criterion bindings."""

from __future__ import annotations

from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from umbral.infrastructure.db.base import Base, IdentityAuditMixin


class PreferenceExpression(IdentityAuditMixin, Base):
    """Exact user wording and its durable supersession lineage."""

    __tablename__ = "preference_expressions"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        CheckConstraint(
            "source_kind IN ('chat', 'structured', 'feedback', 'suggestion', "
            "'migration')",
            name="ck_preference_expressions_source_kind",
        ),
        CheckConstraint(
            "authority IN ('explicit', 'deliberate_feedback', 'passive')",
            name="ck_preference_expressions_authority",
        ),
        CheckConstraint(
            "status IN ('active', 'superseded', 'withdrawn')",
            name="ck_preference_expressions_status",
        ),
        CheckConstraint(
            "status = 'superseded' OR superseded_by IS NULL",
            name="ck_preference_expressions_superseded_shape",
        ),
        Index(
            "ix_preference_expressions_profile_status_created",
            "profile_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_preference_expressions_profile_subject_status",
            "profile_id",
            "subject_key",
            "status",
        ),
        Index("ix_preference_expressions_source_message", "source_message_id"),
        Index("ix_preference_expressions_superseded_by", "superseded_by"),
    )

    profile_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("search_profiles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    source_message_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("chat_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    source_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    subject_key: Mapped[str] = mapped_column(String(100), nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    authority: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    superseded_by: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("preference_expressions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    original_text_available: Mapped[bool] = mapped_column(Boolean, nullable=False)


class CriterionBinding(IdentityAuditMixin, Base):
    """One versioned interpretation of a durable expression."""

    __tablename__ = "criterion_bindings"
    __mapper_args__ = {"version_id_col": IdentityAuditMixin.version}
    __table_args__ = (
        CheckConstraint(
            "kind IN ('structured', 'semantic', 'unresolved', 'forbidden')",
            name="ck_criterion_bindings_kind",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_criterion_bindings_confidence",
        ),
        CheckConstraint(
            "mode IN ('soft', 'hard')", name="ck_criterion_bindings_mode"
        ),
        CheckConstraint(
            "kind <> 'semantic' OR mode = 'soft'",
            name="ck_criterion_bindings_semantic_soft",
        ),
        CheckConstraint(
            "kind NOT IN ('unresolved', 'forbidden') OR concept_key IS NULL",
            name="ck_criterion_bindings_unbound_without_concept",
        ),
        CheckConstraint(
            "kind <> 'structured' OR "
            "(concept_key IS NOT NULL AND matcher_type IS NOT NULL "
            "AND query_embedding IS NULL AND embedding_version_id IS NULL)",
            name="ck_criterion_bindings_structured_shape",
        ),
        CheckConstraint(
            "kind <> 'semantic' OR "
            "(concept_key IS NULL AND matcher_type = 'semantic_feature' "
            "AND query_embedding IS NOT NULL AND embedding_version_id IS NOT NULL)",
            name="ck_criterion_bindings_semantic_shape",
        ),
        CheckConstraint(
            "kind NOT IN ('unresolved', 'forbidden') OR "
            "(matcher_type IS NULL AND query_embedding IS NULL "
            "AND embedding_version_id IS NULL AND mode = 'soft')",
            name="ck_criterion_bindings_noncomputable_shape",
        ),
        CheckConstraint(
            "status IN ('active', 'superseded')",
            name="ck_criterion_bindings_status",
        ),
        CheckConstraint(
            "status = 'superseded' OR superseded_by IS NULL",
            name="ck_criterion_bindings_superseded_shape",
        ),
        Index(
            "ix_criterion_bindings_expression_status_created",
            "expression_id",
            "status",
            "created_at",
        ),
        Index(
            "ix_criterion_bindings_expression_status_kind",
            "expression_id",
            "status",
            "kind",
        ),
        Index("ix_criterion_bindings_concept", "concept_key"),
        Index("ix_criterion_bindings_embedding_version", "embedding_version_id"),
        Index("ix_criterion_bindings_superseded_by", "superseded_by"),
    )

    expression_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("preference_expressions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    concept_key: Mapped[str | None] = mapped_column(
        String(100),
        ForeignKey("concepts.key", ondelete="RESTRICT"),
        nullable=True,
    )
    matcher_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mode: Mapped[str] = mapped_column(String(10), nullable=False)
    params: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    evidence_refs: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    limitations: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    interpretation_version: Mapped[str] = mapped_column(String(100), nullable=False)
    query_embedding: Mapped[list[float] | None] = mapped_column(
        Vector(1536), nullable=True
    )
    embedding_version_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("extraction_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    superseded_by: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("criterion_bindings.id", ondelete="RESTRICT"),
        nullable=True,
    )

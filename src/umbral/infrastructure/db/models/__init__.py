"""All foundation database mappings are imported from this module."""
# ruff: noqa: E501

from umbral.infrastructure.db.models.agent import (
    AgentGraphRun,
    AgentModelCall,
    AgentNodeRun,
)
from umbral.infrastructure.db.models.agent_evals import (
    AgentEvalCaseResult,
    AgentEvalSuite,
)
from umbral.infrastructure.db.models.chat import ChatMessage, ChatSession
from umbral.infrastructure.db.models.criteria import (
    Concept,
    ConceptVersion,
    ExtractionVersion,
    ListingEmbedding,
    ListingObservation,
    PreferenceFact,
    ProfileCriteriaCompilation,
    RecomputeRun,
    UrbanSignal,
)
from umbral.infrastructure.db.models.feedback import (
    FeedbackEvent,
    FeedbackEventReason,
    LearningPolicy,
    LearningPolicyVersion,
    LearningProposal,
)
from umbral.infrastructure.db.models.identity import (
    AccessAuditEvent,
    ExternalIdentityLink,
    IdentityInvitation,
    MagicLinkAttempt,
    MagicLinkRequest,
    ProductSession,
    ProductUser,
    RoleAssignment,
)
from umbral.infrastructure.db.models.imports import (
    ImportRun,
    QuarantineRecord,
    RawListingSnapshot,
)
from umbral.infrastructure.db.models.jobs import (
    JobAttempt,
    JobExecution,
    JobOutboxMessage,
    JobSchedule,
)
from umbral.infrastructure.db.models.notifications import (
    NotificationDecisionModel,
    NotificationInboxItemModel,
    NotificationPreferencesModel,
)
from umbral.infrastructure.db.models.objects import StoredObject, StoredObjectVersion
from umbral.infrastructure.db.models.preferences import (
    CriterionBinding,
    PreferenceExpression,
)
from umbral.infrastructure.db.models.radar import (
    ProductEventRow,
    RecommendationItem,
    RecommendationRun,
    SearchProfile,
    SearchProfileVersion,
)
from umbral.infrastructure.db.models.runtime import RuntimeSurfaceStatus
from umbral.infrastructure.db.models.scoring import (
    ComparisonShortlist,
    CriterionEvaluation,
    ScoringPolicy,
    ScoringPolicyVersion,
)
from umbral.infrastructure.db.models.silver import (
    CanonicalProperty,
    DedupeLink,
    ListingChange,
    SilverListing,
)

__all__ = [
    "AgentGraphRun",
    "AgentNodeRun",
    "AgentModelCall",
    "AgentEvalSuite",
    "AgentEvalCaseResult",
    "ChatSession",
    "ChatMessage",
    "Concept",
    "ConceptVersion",
    "PreferenceFact",
    "ProfileCriteriaCompilation",
    "ExtractionVersion",
    "ListingObservation",
    "RecomputeRun",
    "ListingEmbedding",
    "UrbanSignal",
    "ImportRun",
    "QuarantineRecord",
    "RawListingSnapshot",
    "JobAttempt",
    "JobExecution",
    "JobOutboxMessage",
    "JobSchedule",
    "RuntimeSurfaceStatus",
    "StoredObject",
    "StoredObjectVersion",
    "AccessAuditEvent",
    "ExternalIdentityLink",
    "IdentityInvitation",
    "MagicLinkAttempt",
    "MagicLinkRequest",
    "ProductSession",
    "ProductUser",
    "RoleAssignment",
    "CanonicalProperty",
    "SilverListing",
    "DedupeLink",
    "ListingChange",
    "SearchProfile",
    "SearchProfileVersion",
    "RecommendationRun",
    "RecommendationItem",
    "ProductEventRow",
    "PreferenceExpression",
    "CriterionBinding",
    "ScoringPolicy",
    "ScoringPolicyVersion",
    "CriterionEvaluation",
    "ComparisonShortlist",
    "FeedbackEvent",
    "FeedbackEventReason",
    "LearningPolicy",
    "LearningPolicyVersion",
    "LearningProposal",
    "NotificationPreferencesModel",
    "NotificationDecisionModel",
    "NotificationInboxItemModel",
]

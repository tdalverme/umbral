<!--
Sync Impact Report
Version change: 1.0.0 -> 1.1.0
Modified principles:
- Product and Technical Constraints: beta market, controlled import, Next.js
  with shadcn/ui, and LangGraph are now explicit decisions.
Templates requiring updates:
- .specify/templates/plan-template.md: reviewed; no change required
- .specify/templates/spec-template.md: reviewed; no change required
- .specify/templates/tasks-template.md: reviewed; no change required
Follow-up TODOs: none
-->

# Umbral Constitution

## Core Principles

### I. Persistent Radar as Product Truth
Every listing, match, saved item, dismissal, feedback event, explanation, and
notification that affects a user decision MUST exist as a persistent product
object tied to a search profile. Chat MAY create, refine, compare, and explain,
but chat MUST NOT be the only place where opportunities or decisions live.
Rationale: Umbral is a radar and decision workspace, not an infinite chat log.

### II. Auditable Deterministic Matching
Hard filters, final ranking, and notification decisions MUST be performed by
versioned, deterministic, testable code. LLMs MAY interpret intent, extract
observations, draft explanations, and call explicit tools, but MUST NOT be the
source of final scores. Each recommendation SHOULD record the profile snapshot,
listing snapshot or feature version, scoring version, evidence, and confidence.
Rationale: users need clear reasons and the team needs reproducible debugging.

### III. Layered Dependency Direction
Dependencies MUST flow inward: Product UI to Product API to application services
or agent tools to domain contracts and deterministic engines. Infrastructure
adapters MAY implement ports for database, LLM, retrieval, storage, geocoding,
queues, and notifications; domain and scoring code MUST NOT import FastAPI, DB
clients, LLM clients, workers, or UI code. Agent tools MUST be explicit,
permissioned contracts rather than unrestricted database access.

### IV. Minimal, Verifiable Change
Features and fixes MUST state assumptions, meaningful tradeoffs, and success
criteria before implementation when scope is non-trivial. Implementations MUST
use the minimum code that solves the requested problem, avoid speculative
abstractions, and touch only files required by the task. Every behavioral change
MUST include an appropriate verification path: automated test, contract check,
manual check, or documented reason why verification is not yet runnable.

### V. Data Lineage, Observability, and Trust
Data work MUST preserve lineage through Bronze, Silver, and Gold layers: raw
snapshots, normalized/deduplicated entities, then features, observations,
scores, explanations, feedback, and notifications. Dedupe MUST NOT be
destructive without confidence and evidence. Qualitative features MUST store
value, confidence, evidence, source, computed version, and timestamp when used
for recommendations. User-visible uncertainty MUST be represented honestly.

## Product and Technical Constraints

- V1 SHOULD start as a modular monolith with Python/FastAPI, Postgres, PostGIS,
  pgvector, workers, Redis, object storage, and a web UI using Next.js App
  Router, TypeScript, shadcn/ui, Tailwind, TanStack Query, and MapLibre.
- The conversational orchestrator MUST use LangGraph with explicit,
  permissioned application tools and persistent checkpoints. Checkpoints MUST
  NOT replace searches, listings, recommendations, feedback, or audit events as
  product truth.
- The private beta MUST target residential rentals in CABA, use controlled
  listing imports, magic-link invitations, and web plus email notifications.
  Scraping and direct listing publication MUST remain outside the beta's
  critical path.
- RAG and embeddings MAY retrieve context, candidates, or evidence, but MUST NOT
  replace hard filters, deterministic ranking, or notification planning.
- Avoid microservices, Kafka, a separate vector database, multi-agent complexity,
  and fine-tuning until a documented scaling or product need justifies them.
- Explanations MUST cite internal evidence when available and state uncertainty
  when evidence is weak or missing.

## Development Workflow

- Spec Kit feature work SHOULD follow: specify, clarify if needed, plan, tasks,
  implement, then converge/analyze when useful.
- Specs MUST describe what and why before committing to technology choices.
- Plans MUST document architecture boundaries, data/audit implications, scoring
  or notification impact, and verification commands.
- Tasks MUST be grouped into independently testable user-value slices whenever
  possible and MUST keep cross-cutting work explicit.
- Runtime coding guidance in AGENTS.md and this constitution MUST stay aligned;
  if they conflict, stop and reconcile before implementation.

## Governance

This constitution governs Spec Kit artifacts and feature implementation plans
for Umbral. Amendments require an explicit change to this file, a Sync Impact
Report, a semantic version bump, and review of dependent templates. MAJOR
versions change or remove core governance, MINOR versions add or materially
expand principles, and PATCH versions clarify wording without changing meaning.
All feature plans and reviews MUST check compliance with the current
constitution before implementation proceeds.

**Version**: 1.1.0 | **Ratified**: 2026-07-28 | **Last Amended**: 2026-07-28

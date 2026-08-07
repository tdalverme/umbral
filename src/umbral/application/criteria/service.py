"""Orchestration for criteria and observations.

The service owns concept registry versioning (with automatic invalidation of
affected observations), append-only preference facts, criteria compilation,
objective rule extraction and structured qualitative extraction through the
``StructuredExtractor`` port, selective recomputation (manual job with cause),
embedding regeneration (P1) and urban context ingestion (P1). Version changes
invalidate only affected observations; recompute publication (new observations
+ supersede + run state + event) is atomic.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID, uuid4

from umbral.application.criteria.compile import compile_criteria
from umbral.application.criteria.contracts import (
    Compilation,
    Concept,
    ConceptVersion,
    CriteriaError,
    CriteriaNotFound,
    CriteriaPermanentError,
    CriteriaValidationError,
    ExtractionVersion,
    ListingObservation,
    PreferenceFact,
    RecomputeRun,
    RecomputeScope,
)
from umbral.application.criteria.extractor import (
    ExtractionContractSpec,
    StructuredExtractor,
    build_permitted_input,
    evidence_fragment_text,
    validate_model_output,
)
from umbral.application.criteria.ports import (
    CompilationRepository,
    ConceptRepository,
    EmbeddingRepository,
    EventRepository,
    ExtractionVersionRepository,
    FactRepository,
    ListingProjectionReader,
    ObservationRepository,
    ProfileSnapshotReader,
    RecomputeRunRepository,
    UrbanSignalRepository,
)
from umbral.application.criteria.registry import (
    ConceptLike,
    ConceptSeed,
    ConceptsSeedSpec,
    MatcherTypesSpec,
    validate_concept_seed,
)
from umbral.application.criteria.rules import rule_version, run_rule
from umbral.application.events.contracts import ProductEvent
from umbral.application.events.registry import (
    EventsRegistrySpec,
    event_version,
)
from umbral.application.jobs.contracts import SubmitJob
from umbral.application.jobs.ports import JobRuntime
from umbral.application.silver.contracts import NormalizedListing
from umbral.domain.audit import AuditActor

EXTRACTION_RUN_JOB_TYPE = "extraction.run"
RECOMPUTE_JOB_TYPE = "extraction.recompute"

Clock = Callable[[], datetime]

_CAUSE_SLUG_RE = re.compile(r"[^a-z0-9._:-]+")


class EmbeddingModel(Protocol):
    """P1 vectorizer over the permitted projection; adapter supplies it."""

    def embed(self, projection: Mapping[str, object]) -> tuple[float, ...]: ...


class UrbanSource(Protocol):
    """P1 external urban context source with cache and rate limits."""

    def fetch(
        self, listing: NormalizedListing, signal_type: str
    ) -> tuple[Mapping[str, object], ...]: ...


class CriteriaService:
    def __init__(
        self,
        *,
        concepts: ConceptRepository,
        facts: FactRepository,
        compilations: CompilationRepository,
        observations: ObservationRepository,
        extraction_versions: ExtractionVersionRepository,
        recomputes: RecomputeRunRepository,
        events: EventRepository,
        listings: ListingProjectionReader,
        profiles: ProfileSnapshotReader,
        concepts_seed: ConceptsSeedSpec,
        matcher_types: MatcherTypesSpec,
        extraction_contract: ExtractionContractSpec,
        events_registry: EventsRegistrySpec,
        extractor: StructuredExtractor | None,
        embeddings: EmbeddingRepository | None = None,
        embedding_model: EmbeddingModel | None = None,
        urban_signals: UrbanSignalRepository | None = None,
        urban_source: UrbanSource | None = None,
        job_runtime: JobRuntime | None = None,
        extraction_job_type: str = EXTRACTION_RUN_JOB_TYPE,
        recompute_job_type: str = RECOMPUTE_JOB_TYPE,
        qualitative_max_attempts: int = 2,
        batch_size: int = 250,
        embeddings_enabled: bool = False,
        embedding_model_version_key: str | None = None,
        urban_context_enabled: bool = False,
        clock: Clock | None = None,
    ) -> None:
        self.concepts = concepts
        self.facts = facts
        self.compilations = compilations
        self.observations = observations
        self.extraction_versions = extraction_versions
        self.recomputes = recomputes
        self.events = events
        self.listings = listings
        self.profiles = profiles
        self.concepts_seed = concepts_seed
        self.matcher_types = matcher_types
        self.extraction_contract = extraction_contract
        self.events_registry = events_registry
        self.extractor = extractor
        self.embeddings = embeddings
        self.embedding_model = embedding_model
        self.urban_signals = urban_signals
        self.urban_source = urban_source
        self.job_runtime = job_runtime
        self.extraction_job_type = extraction_job_type
        self.recompute_job_type = recompute_job_type
        self.qualitative_max_attempts = qualitative_max_attempts
        self.batch_size = batch_size
        self.embeddings_enabled = embeddings_enabled
        self.embedding_model_version_key = (
            embedding_model_version_key or "embeddings-v1"
        )
        self.urban_context_enabled = urban_context_enabled
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    # ------------------------------------------------------------------
    # Concept registry (US1)
    # ------------------------------------------------------------------

    def seed_registry(self, correlation_id: UUID) -> int:
        """Load the versioned seed idempotently; returns registered count."""

        registered = 0
        for seed in self.concepts_seed.concepts:
            existing = self.concepts.get(seed.key)
            if existing is not None:
                continue
            self._register_seed(seed, correlation_id)
            registered += 1
        return registered

    def register_concept_version(
        self,
        *,
        key: str,
        name: str,
        aliases: tuple[str, ...],
        matcher_type: str,
        params_schema: Mapping[str, object],
        defaults: Mapping[str, object],
        compute_policy: Mapping[str, object],
        correlation_id: UUID,
        actor_kind: str = "service",
        actor_id: str | None = None,
    ) -> ConceptVersion:
        seed = ConceptSeed(
            key=key,
            name=name,
            aliases=aliases,
            matcher_type=matcher_type,  # type: ignore[arg-type]
            params_schema=dict(params_schema),
            source="operator",
            defaults=dict(defaults),
            compute_policy=dict(compute_policy),
        )
        errors = validate_concept_seed(seed, self.matcher_types)
        if errors:
            raise CriteriaValidationError(errors)

        existing = self.concepts.get(key)
        concept_version = (existing.version + 1) if existing is not None else 1
        now = self.clock()
        version = ConceptVersion(
            version_id=uuid4(),
            concept_id=existing.concept_id if existing is not None else uuid4(),
            concept_version=concept_version,
            payload=seed_to_payload(seed),
            created_at=now,
            correlation_id=correlation_id,
            actor_kind=actor_kind,
            actor_id=actor_id,
        )
        if existing is None:
            concept = Concept(
                concept_id=version.concept_id,
                key=key,
                name=name,
                aliases=aliases,
                matcher_type=seed.matcher_type,
                params_schema=dict(params_schema),
                source="operator",
                defaults=dict(defaults),
                compute_policy=dict(compute_policy),
                version=1,
                current_version_id=version.version_id,
                created_at=now,
                updated_at=now,
                correlation_id=correlation_id,
                actor_kind=actor_kind,
                actor_id=actor_id,
            )
            self.concepts.insert(concept)
        else:
            self.concepts.save(
                replace(
                    existing,
                    name=name,
                    aliases=aliases,
                    matcher_type=seed.matcher_type,
                    params_schema=dict(params_schema),
                    defaults=dict(defaults),
                    compute_policy=dict(compute_policy),
                    current_version_id=version.version_id,
                    updated_at=now,
                )
            )
        self.concepts.insert_version(version)
        self.observations.invalidate_for_concept(key)
        self._emit_event(
            event_type="criteria.concept_version_created.v1",
            correlation_id=correlation_id,
            actor_id=(UUID(actor_id) if actor_id else None),
            payload={
                "concept_key": key,
                "concept_version": concept_version,
            },
        )
        return version

    def register_extraction_version(
        self,
        *,
        kind: str,
        key: str,
        version: str,
        payload: Mapping[str, object],
        correlation_id: UUID,
    ) -> ExtractionVersion:
        """Register an immutable extraction artifact version idempotently.

        Registering a new version of an existing artifact automatically
        invalidates the observations referencing the previous version.
        """

        existing_same = self.extraction_versions.find(kind, key, version)
        if existing_same is not None:
            return existing_same
        previous = self.extraction_versions.latest(kind, key)
        entry = ExtractionVersion(
            version_id=uuid4(),
            kind=kind,  # type: ignore[arg-type]
            key=key,
            version=version,
            payload=dict(payload),
            created_at=self.clock(),
            correlation_id=correlation_id,
        )
        self.extraction_versions.insert(entry)
        if previous is not None:
            self.observations.invalidate_for_extraction_version(previous.version_id)
        return entry

    # ------------------------------------------------------------------
    # Preference facts and compilation (US2)
    # ------------------------------------------------------------------

    def record_preference_fact(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        concept_key: str,
        value: object,
        weight: float,
        polarity: str,
        confidence: float,
        fact_source: str,
        correlation_id: UUID,
        actor_kind: str = "service",
        actor_id: str | None = None,
    ) -> PreferenceFact:
        if self.profiles.owner_of(profile_id) != owner_id:
            raise CriteriaNotFound(f"search profile not accessible: {profile_id}")
        if self.concepts.get(concept_key) is None:
            raise CriteriaValidationError(
                (f"criteria.concept_not_found:{concept_key}",)
            )
        if not 0.0 <= weight <= 1.0:
            raise CriteriaValidationError(("criteria.fact_weight_out_of_range",))
        if not 0.0 <= confidence <= 1.0:
            raise CriteriaValidationError(("criteria.fact_confidence_out_of_range",))
        if polarity not in {"positive", "negative"}:
            raise CriteriaValidationError(("criteria.fact_polarity_invalid",))
        fact = PreferenceFact(
            fact_id=uuid4(),
            profile_id=profile_id,
            concept_key=concept_key,
            value=value,
            weight=float(weight),
            polarity=polarity,
            confidence=float(confidence),
            fact_source=fact_source,
            state="active",
            superseded_by=None,
            created_at=self.clock(),
            correlation_id=correlation_id,
            actor_kind=actor_kind,
            actor_id=actor_id,
        )
        self.facts.record_change(fact, superseded_by=fact.fact_id)
        return fact

    def compile_profile(
        self,
        *,
        owner_id: UUID,
        profile_id: UUID,
        profile_version_id: UUID,
        edits: tuple[Mapping[str, object], ...],
        confirmations: tuple[str, ...] = (),
        correlation_id: UUID,
        actor_kind: str = "service",
        actor_id: str | None = None,
    ) -> Compilation:
        if self.profiles.owner_of(profile_id) != owner_id:
            raise CriteriaNotFound(f"search profile not accessible: {profile_id}")
        version_ref = self.profiles.get_version(profile_version_id)
        if version_ref is None or version_ref[0] != profile_id:
            raise CriteriaNotFound(f"profile version not found: {profile_version_id}")
        profile_version_number = version_ref[1]

        facts = self.facts.active_for_profile(profile_id)
        concepts = self._concept_map()
        draft = compile_criteria(
            concepts=concepts,
            matcher_types=self.matcher_types,
            facts=facts,
            edits=edits,
            confirmations=confirmations,
        )
        previous = self.compilations.latest_for_profile_version(profile_version_id)
        version = (previous.compilation_version + 1) if previous is not None else 1
        compilation = Compilation(
            compilation_id=uuid4(),
            profile_id=profile_id,
            profile_version_id=profile_version_id,
            compilation_version=version,
            criteria=draft.criteria,
            warnings=draft.warnings,
            confirmations=draft.confirmations,
            created_at=self.clock(),
            correlation_id=correlation_id,
            actor_kind=actor_kind,
            actor_id=actor_id,
        )
        self.compilations.insert(compilation)
        self._emit_event(
            event_type="criteria.compilation_created.v1",
            correlation_id=correlation_id,
            actor_id=(UUID(actor_id) if actor_id else None),
            payload={
                "profile_id": str(profile_id),
                "profile_version": profile_version_number,
                "compilation_version": version,
                "criterion_count": len(draft.criteria),
                "warning_count": len(draft.warnings),
            },
        )
        return compilation

    def latest_compilation(self, profile_version_id: UUID) -> Compilation | None:
        return self.compilations.latest_for_profile_version(profile_version_id)

    # ------------------------------------------------------------------
    # Extraction and recompute (US3, US4, US5)
    # ------------------------------------------------------------------

    def submit_extraction(
        self,
        scope: RecomputeScope,
        correlation_id: UUID,
    ) -> object | None:
        if self.job_runtime is None:
            return None
        return self.job_runtime.submit(
            SubmitJob.create(
                job_type=self.extraction_job_type,
                logical_target=scope.target,
                idempotency_key=f"extract:{scope.target}",
                correlation_id=correlation_id,
                actor=AuditActor.system(),
            )
        )

    def submit_recompute(
        self,
        scope: RecomputeScope,
        cause: str,
        correlation_id: UUID,
    ) -> object | None:
        if self.job_runtime is None:
            return None
        cause_slug = _cause_slug(cause)
        return self.job_runtime.submit(
            SubmitJob.create(
                job_type=self.recompute_job_type,
                logical_target=scope.target,
                idempotency_key=f"recompute:{scope.target}:{cause_slug}",
                correlation_id=correlation_id,
                actor=AuditActor.system(),
            )
        )

    def invalidate_scope(self, scope: RecomputeScope) -> int:
        if scope.kind == "concept" and scope.key:
            return self.observations.invalidate_for_concept(scope.key)
        if scope.kind == "extraction" and scope.key:
            return self.observations.invalidate_for_extraction_version(UUID(scope.key))
        if scope.kind == "parser" and scope.key:
            return self.observations.invalidate_for_normalizer_version(scope.key)
        return 0

    def process_extraction(
        self,
        scope: RecomputeScope,
        job_execution_id: UUID,
        correlation_id: UUID | None = None,
    ) -> Mapping[str, object]:
        correlation_id = correlation_id or uuid4()
        observations, targets = self._extract_for_scope(scope, correlation_id)
        supersede_ids = self.observations.ids_for_scope(scope)
        published = sum(1 for item in observations if item.state == "active")
        failed = sum(1 for item in observations if item.state == "failed")
        self.observations.publish(
            observations=observations,
            supersede_ids=supersede_ids,
            run=None,
            event=None,
        )
        if scope.kind == "concept":
            self._emit_event(
                event_type="criteria.observation_batch_published.v1",
                correlation_id=correlation_id,
                actor_id=None,
                payload={
                    "scope_kind": scope.kind,
                    "scope_key": scope.key or "full",
                    "extraction_version_id": str(targets[0][2].version_id),
                    "published_count": published,
                    "superseded_count": len(supersede_ids),
                    "failed_count": failed,
                },
            )
        return {
            "scope_kind": scope.kind,
            "scope_key": scope.key or "full",
            "published": published,
            "superseded": len(supersede_ids),
            "failed": failed,
            "concept_count": len(targets),
        }

    def process_recompute(
        self,
        scope: RecomputeScope,
        cause: str,
        job_execution_id: UUID,
        correlation_id: UUID | None = None,
    ) -> Mapping[str, object]:
        correlation_id = correlation_id or uuid4()
        now = self.clock()
        run = RecomputeRun(
            run_id=uuid4(),
            scope=scope,
            cause=cause,
            state="pending",
            counts={},
            job_execution_id=job_execution_id,
            finished_at=None,
            created_at=now,
            correlation_id=correlation_id,
        )
        self.recomputes.insert(run)
        supersede_ids = self.observations.ids_for_scope(scope)
        try:
            observations, _ = self._extract_for_scope(scope, correlation_id)
        except CriteriaError:
            self.recomputes.fail(run, "criteria.recompute_failed")
            raise
        finished = self.clock()
        published = sum(1 for item in observations if item.state == "active")
        failed = sum(1 for item in observations if item.state == "failed")
        counts = {
            "invalidated": len(supersede_ids),
            "published": published,
            "superseded": len(supersede_ids),
            "failed": failed,
        }
        succeeded_run = RecomputeRun(
            run_id=run.run_id,
            scope=scope,
            cause=cause,
            state="succeeded",
            counts=counts,
            job_execution_id=job_execution_id,
            finished_at=finished,
            created_at=now,
            correlation_id=correlation_id,
        )
        event = self._build_event(
            event_type="criteria.recompute_completed.v1",
            correlation_id=correlation_id,
            actor_id=None,
            payload={
                "recompute_run_id": str(run.run_id),
                "scope_kind": scope.kind,
                "scope_key": scope.key or "full",
                "cause": cause,
                "state": "succeeded",
                "published_count": published,
                "failed_count": failed,
            },
        )
        self.observations.publish(
            observations=observations,
            supersede_ids=supersede_ids,
            run=succeeded_run,
            event=event,
        )
        return {
            "recompute_run_id": str(run.run_id),
            "scope_kind": scope.kind,
            "scope_key": scope.key or "full",
            "cause": cause,
            "state": "succeeded",
            "published": published,
            "superseded": len(supersede_ids),
            "failed": failed,
        }

    # ------------------------------------------------------------------
    # Embeddings (US6, P1)
    # ------------------------------------------------------------------

    def process_embeddings(
        self,
        scope: RecomputeScope,
        correlation_id: UUID | None = None,
    ) -> Mapping[str, object]:
        correlation_id = correlation_id or uuid4()
        if not self.embeddings_enabled or self.embedding_model is None:
            return {"enabled": False, "published": 0}
        version_entry = self.register_extraction_version(
            kind="embedding",
            key=self.embedding_model_version_key,
            version="v1",
            payload={"model": self.embedding_model_version_key},
            correlation_id=correlation_id,
        )
        listings = self._listings_for_scope(scope)
        vectors: dict[UUID, tuple[float, ...]] = {}
        for listing in listings:
            projection = build_permitted_input(
                listing, self.extraction_contract, self.embedding_model_version_key
            )
            vectors[listing.listing_id] = self.embedding_model.embed(projection)
        if self.embeddings is not None:
            self.embeddings.publish_embeddings(
                listing_ids=tuple(vectors),
                extraction_version_id=version_entry.version_id,
                vectors=vectors,
                run=None,
            )
        return {"enabled": True, "published": len(vectors)}

    # ------------------------------------------------------------------
    # Urban context (US7, P1)
    # ------------------------------------------------------------------

    def ingest_urban_signals(
        self,
        listing_id: UUID,
        signal_type: str,
        correlation_id: UUID,
    ) -> int:
        if not self.urban_context_enabled or self.urban_source is None:
            return 0
        if self.urban_signals is None:
            return 0
        listing = self.listings.get(listing_id)
        if listing is None:
            raise CriteriaNotFound(f"listing not found: {listing_id}")
        signals = self.urban_source.fetch(listing, signal_type)
        now = self.clock()
        count = 0
        for raw in signals:
            self.urban_signals.insert(
                {
                    "signal_id": uuid4(),
                    "created_at": now,
                    "correlation_id": correlation_id,
                    "listing_id": listing_id,
                    "signal_type": signal_type,
                    "signal_source": str(raw.get("source", "unknown")),
                    "observed_at": now,
                    "geometry": _authorized_geometry(listing, raw),
                    "algorithm_version": str(raw.get("algorithm_version", "v1")),
                    "payload": _raw_payload(raw),
                }
            )
            count += 1
        return count

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _register_seed(self, seed: ConceptSeed, correlation_id: UUID) -> None:
        self.register_concept_version(
            key=seed.key,
            name=seed.name,
            aliases=seed.aliases,
            matcher_type=seed.matcher_type,
            params_schema=seed.params_schema,
            defaults=seed.defaults,
            compute_policy=seed.compute_policy,
            correlation_id=correlation_id,
        )

    def _concept_map(self) -> Mapping[str, ConceptLike]:
        registered = {concept.key: concept for concept in self.concepts.list_active()}
        if registered:
            return registered
        return {concept.key: concept for concept in self.concepts_seed.concepts}

    def _extract_for_scope(
        self,
        scope: RecomputeScope,
        correlation_id: UUID,
    ) -> tuple[
        tuple[ListingObservation, ...], tuple[tuple[str, str, ExtractionVersion], ...]
    ]:
        """Extract all concepts of the scope; publication is the caller's job."""

        targets = self._extraction_targets(scope)
        listings = self._listings_for_scope(scope)
        all_observations: list[ListingObservation] = []
        resolved: list[tuple[str, str, ExtractionVersion]] = []
        for concept_key, source in targets:
            version_entry = self._ensure_extraction_version(
                concept_key, source, correlation_id
            )
            resolved.append((concept_key, source, version_entry))
            for start in range(0, len(listings), self.batch_size):
                chunk = listings[start : start + self.batch_size]
                all_observations.extend(
                    self._extract_concept(
                        concept_key=concept_key,
                        source=source,
                        version_entry=version_entry,
                        listings=chunk,
                        correlation_id=correlation_id,
                    )
                )
        return tuple(all_observations), tuple(resolved)

    def _extraction_targets(self, scope: RecomputeScope) -> tuple[tuple[str, str], ...]:
        if scope.kind == "concept" and scope.key:
            concept = self.concepts.get(scope.key)
            if concept is None:
                raise CriteriaNotFound(f"concept not found: {scope.key}")
            source = self._concept_source(scope.key)
            return ((scope.key, source),)
        if scope.kind == "extraction" and scope.key:
            version = self.extraction_versions.get(UUID(scope.key))
            if version is None:
                raise CriteriaNotFound(f"extraction version not found: {scope.key}")
            if version.kind == "rule":
                return ((version.key, "rule"),)
            if version.kind == "model":
                return ((version.key, "model"),)
            raise CriteriaValidationError(("criteria.extraction_scope_invalid",))
        return tuple(
            (concept.key, self._concept_source(concept.key))
            for concept in self.concepts_seed.concepts
        )

    def _concept_source(self, concept_key: str) -> str:
        concept = self.extraction_contract.concepts.get(concept_key)
        if concept is None:
            raise CriteriaNotFound(f"no extraction contract for concept: {concept_key}")
        return str(concept.get("source", "rule"))

    def _listings_for_scope(
        self, scope: RecomputeScope
    ) -> tuple[NormalizedListing, ...]:
        if scope.kind == "parser" and scope.key:
            return self.listings.list_by_normalizer_version(scope.key)
        return self.listings.list_all()

    def _ensure_extraction_version(
        self, concept_key: str, source: str, correlation_id: UUID
    ) -> ExtractionVersion:
        if source == "rule":
            return self.register_extraction_version(
                kind="rule",
                key=concept_key,
                version=rule_version(concept_key),
                payload={
                    "rule": concept_key,
                    "module": "umbral.application.criteria.rules",
                },
                correlation_id=correlation_id,
            )
        schema = self.extraction_contract.concepts.get(concept_key, {}).get("schema")
        if not isinstance(schema, Mapping):
            raise CriteriaPermanentError(
                "criteria.schema_missing", f"no schema for concept: {concept_key}"
            )
        schema_entry = self.register_extraction_version(
            kind="schema",
            key=f"{concept_key}.schema",
            version="v1",
            payload={"schema": dict(schema)},
            correlation_id=correlation_id,
        )
        prompt_entry = self.register_extraction_version(
            kind="prompt",
            key=f"{concept_key}.prompt",
            version="v1",
            payload={"prompt": _DEFAULT_PROMPT},
            correlation_id=correlation_id,
        )
        return self.register_extraction_version(
            kind="model",
            key=concept_key,
            version=f"{concept_key}.model-v1",
            payload={
                "provider": "managed",
                "schema_ref": str(schema_entry.version_id),
                "prompt_ref": str(prompt_entry.version_id),
            },
            correlation_id=correlation_id,
        )

    def _extract_concept(
        self,
        *,
        concept_key: str,
        source: str,
        version_entry: ExtractionVersion,
        listings: tuple[NormalizedListing, ...],
        correlation_id: UUID,
    ) -> tuple[ListingObservation, ...]:
        now = self.clock()
        observations: list[ListingObservation] = []
        for listing in listings:
            projection = build_permitted_input(
                listing, self.extraction_contract, concept_key
            )
            if source == "rule":
                observations.append(
                    _rule_observation(
                        listing_id=listing.listing_id,
                        concept_key=concept_key,
                        matcher_type=self._matcher_type(concept_key),
                        version_entry=version_entry,
                        projection=projection,
                        now=now,
                        correlation_id=correlation_id,
                    )
                )
                continue
            observations.append(
                self._model_observation(
                    listing_id=listing.listing_id,
                    concept_key=concept_key,
                    matcher_type=self._matcher_type(concept_key),
                    version_entry=version_entry,
                    projection=projection,
                    now=now,
                    correlation_id=correlation_id,
                )
            )
        return tuple(observations)

    def _model_observation(
        self,
        *,
        listing_id: UUID,
        concept_key: str,
        matcher_type: str,
        version_entry: ExtractionVersion,
        projection: Mapping[str, object],
        now: datetime,
        correlation_id: UUID,
    ) -> ListingObservation:
        if self.extractor is None:
            raise CriteriaPermanentError(
                "criteria.extractor_unavailable", f"no extractor for: {concept_key}"
            )
        schema = self.extraction_contract.concepts.get(concept_key, {}).get("schema")
        if not isinstance(schema, Mapping):
            raise CriteriaPermanentError(
                "criteria.schema_missing", f"no schema for concept: {concept_key}"
            )
        result: object | None = None
        evidence: str | None = None
        confidence = 0.0
        failure_code: str | None = None
        for _ in range(max(1, self.qualitative_max_attempts)):
            attempt = self.extractor.extract(
                concept_key=concept_key,
                permitted_input=projection,
                schema=schema,
                version=version_entry.version,
            )
            if attempt.failed:
                failure_code = attempt.failure_code or "extraction.failed"
                continue
            if not isinstance(attempt.value, Mapping):
                failure_code = "extraction.invalid_output"
                continue
            valid, error_code = validate_model_output(attempt.value, schema)
            if not valid:
                failure_code = f"extraction.invalid_output:{error_code}"
                continue
            result = attempt.value.get("value")
            evidence = evidence_fragment_text(attempt.value)
            confidence = float(attempt.value.get("confidence", 0.0))
            failure_code = None
            break
        state = "failed" if failure_code is not None else "active"
        return ListingObservation(
            observation_id=uuid4(),
            listing_id=listing_id,
            concept_key=concept_key,
            matcher_type=matcher_type,  # type: ignore[arg-type]
            value=result,
            score=0.0,
            confidence=confidence,
            evidence={
                "fragment": evidence,
                "span": None,
                "matched_on": [],
            },
            source="model",
            extraction_version_id=version_entry.version_id,
            state=state,  # type: ignore[arg-type]
            failure_code=failure_code,
            recomputation_run_id=None,
            created_at=now,
            correlation_id=correlation_id,
        )

    def _matcher_type(self, concept_key: str) -> str:
        concept = self.concepts.get(concept_key)
        if concept is not None:
            return concept.matcher_type
        for seed in self.concepts_seed.concepts:
            if seed.key == concept_key:
                return seed.matcher_type
        return "categorical"

    def _emit_event(
        self,
        *,
        event_type: str,
        correlation_id: UUID,
        actor_id: UUID | None,
        payload: Mapping[str, object],
    ) -> None:
        event = self._build_event(
            event_type=event_type,
            correlation_id=correlation_id,
            actor_id=actor_id,
            payload=payload,
        )
        self.events.insert(event)

    def _build_event(
        self,
        *,
        event_type: str,
        correlation_id: UUID,
        actor_id: UUID | None,
        payload: Mapping[str, object],
    ) -> ProductEvent:
        version = event_version(self.events_registry, event_type)
        return ProductEvent(
            event_id=uuid4(),
            event_type=event_type,
            event_version=version or 1,
            actor_id=actor_id,
            occurred_at=self.clock(),
            correlation_id=correlation_id,
            payload=dict(payload),
        )


def _rule_observation(
    *,
    listing_id: UUID,
    concept_key: str,
    matcher_type: str,
    version_entry: ExtractionVersion,
    projection: Mapping[str, object],
    now: datetime,
    correlation_id: UUID,
) -> ListingObservation:
    outcome = run_rule(concept_key, projection)
    return ListingObservation(
        observation_id=uuid4(),
        listing_id=listing_id,
        concept_key=concept_key,
        matcher_type=matcher_type,  # type: ignore[arg-type]
        value=outcome.value,
        score=_rule_score(outcome.value, outcome.fragment),
        confidence=1.0 if outcome.value is not None else 0.0,
        evidence={
            "fragment": outcome.fragment,
            "span": list(outcome.span) if outcome.span is not None else None,
            "matched_on": list(outcome.matched_on),
        },
        source="rule",
        extraction_version_id=version_entry.version_id,
        state="active",
        failure_code=None,
        recomputation_run_id=None,
        created_at=now,
        correlation_id=correlation_id,
    )


def _rule_score(value: object, fragment: str | None) -> float:
    if value is None:
        return 0.0
    return 1.0 if fragment is not None else 0.6


def _cause_slug(cause: str) -> str:
    slug = _CAUSE_SLUG_RE.sub("-", cause.strip().lower())
    slug = slug.strip("-")[:80]
    return slug or "recompute"


def _authorized_geometry(
    listing: NormalizedListing, raw: Mapping[str, object]
) -> object:
    if listing.geo_precision not in {"exact", "block"}:
        return None
    geometry = raw.get("geometry")
    if isinstance(geometry, tuple) and len(geometry) == 2:
        return f"POINT({geometry[0]} {geometry[1]})"
    return None


def _raw_payload(raw: Mapping[str, object]) -> Mapping[str, object]:
    payload = raw.get("payload")
    return dict(payload) if isinstance(payload, Mapping) else {}


def seed_to_payload(seed: ConceptSeed) -> Mapping[str, object]:
    return {
        "key": seed.key,
        "name": seed.name,
        "aliases": list(seed.aliases),
        "matcher_type": seed.matcher_type,
        "params_schema": dict(seed.params_schema),
        "source": seed.source,
        "defaults": dict(seed.defaults),
        "compute_policy": dict(seed.compute_policy),
    }


_DEFAULT_PROMPT = (
    "Eres un extractor de datos inmobiliarios. A partir de los campos "
    "permitidos del listing, responde solo con el esquema JSON solicitado, "
    "con evidencia textual citada del texto y un nivel de confianza 0..1. "
    "No inventes hechos que no esten soportados."
)

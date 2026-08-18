# Conversational Search Copilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convertir el chat de Umbral en un copiloto que crea y refina radares parciales, conserva deseos arbitrarios y solo usa evidencia computable, sin loops ni confirmaciones innecesarias.

**Architecture:** Dos módulos profundos nuevos separan expresión de preferencia y ejecución conversacional. LangGraph v4 interpreta una lista de actos, pero una política determinista valida contexto y autoridad antes de llamar servicios explícitos; el scoring recibe criterios y señales semánticas congeladas, nunca texto libre ni decisiones generativas. PostgreSQL conserva expresiones, bindings, lineage y versiones, mientras los refreshes obsoletos no pueden publicar.

**Tech Stack:** Python 3.13, FastAPI, Pydantic 2.13, SQLAlchemy 2.0, Alembic, PostgreSQL/pgvector, LangGraph 1.2, pytest; Next.js 16.2, React 19.2, TypeScript 6, shadcn/ui, Tailwind 4, TanStack Query, Vitest y Playwright.

## Global Constraints

- La beta continúa limitada a alquileres residenciales en CABA.
- Primera señal visible de progreso: menos de 1 segundo.
- p95 de respuestas conversacionales normales: menos de 5 segundos.
- Invariantes críticos de estado, seguridad, equidad y mutaciones: 100%.
- Trayectorias completas: al menos 95%; ninguna familia por debajo de 90%.
- La similitud semántica es siempre suave, usa peso máximo `0.10` y aporta cero sin evidencia compatible.
- El modelo produce estructura; filtros duros, efectos, ranking y publicación los decide código determinista y versionado.
- Un mensaje puede aplicar efectos seguros y dejar una única aclaración material; ninguna parte se descarta silenciosamente.
- El radar durable, no el historial del chat, es la fuente de verdad operativa.
- No refactorizar ingestión, identidad, notificaciones ni superficies ajenas a los seams enumerados en este plan.

---

## File Map

| Área | Archivos responsables |
|---|---|
| Contratos versionados | `contracts/agent/v4/*`, `contracts/preferences/v1/*`, `contracts/scoring/v2/*`, `contracts/agent-evals/v2/*` |
| Radar parcial | `src/umbral/application/radar/{contracts,profile_policy,hard_filters,service}.py`, `contracts/search-profiles/v2/*` |
| Expresiones y bindings | `src/umbral/application/preferences/{contracts,ports,policy,service}.py` |
| Persistencia | `src/umbral/infrastructure/db/models/preferences.py`, `repositories/preferences.py`, migración `0016` |
| Orquestación de turno | `src/umbral/application/conversation/{contracts,ports,policy,service}.py` |
| Interpretación/grafo | `src/umbral/agent/{state,graph,runtime}.py`, `src/umbral/agent/interpretation/compiler.py` |
| Scoring/diagnóstico | `src/umbral/application/scoring/{contracts,engine,evaluators,service}.py`, `src/umbral/application/radar/service.py` |
| API/SSE | `src/umbral/api/routers/{chat,search_profiles}.py` |
| UI | `apps/web/src/app/(protected)/radar/new/page.tsx`, `components/chat/*`, `lib/chat/*` |
| Trayectorias | `src/umbral/application/agent_evals/*`, `contracts/agent-evals/v2/*`, tests de integración |

### Task 1: Publicar contratos v4/v2 y políticas de producto

**Files:**
- Create: `contracts/agent/v4/interpretation-schema-v4.json`
- Create: `contracts/agent/v4/state-schema-v4.json`
- Create: `contracts/agent/v4/reply-schema-v4.json`
- Create: `contracts/agent/v4/graph-topology-v4.json`
- Create: `contracts/preferences/v1/preference-policy-v1.json`
- Create: `contracts/scoring/v2/scoring-policy-v2.json`
- Create: `contracts/search-profiles/v2/search-profile-policy-v2.json`
- Create: `contracts/agent-evals/v2/conversation-trajectories-v2.schema.json`
- Create: `contracts/agent-evals/v2/release-gate-v2.json`
- Create: `tests/contract/test_agent_contracts_v4.py`
- Create: `tests/contract/test_preference_policy.py`
- Create: `tests/contract/test_conversation_trajectories_v2.py`

**Interfaces:**
- Consumes: decisiones de `specs/016-conversational-search-copilot/contracts/chat-copilot-contracts-v1.md`.
- Produces: schemas JSON con versions exactas `4`, `1`, `2` y políticas cargables por tareas posteriores.

- [ ] **Step 1: Escribir tests que exijan actos múltiples, perfil opcional y gates exactos**

```python
def test_interpretation_v4_accepts_ordered_multi_act_payload(load_contract):
    schema = load_contract("contracts/agent/v4/interpretation-schema-v4.json")
    payload = {
        "contract_version": "4",
        "interpretation_version": "conversation-interpretation-v4",
        "acts": [
            {"act_id": "a1", "kind": "resolve_pending", "target": {}, "payload": {"decision": "approve"}, "confidence": 0.99},
            {"act_id": "a2", "kind": "express_preference", "target": {}, "payload": {"subject_key": "balcon", "text": "quiero balcon"}, "confidence": 0.95},
        ],
        "ambiguity": None,
    }
    jsonschema.validate(payload, schema)

def test_release_gate_is_strict(load_json):
    gate = load_json("contracts/agent-evals/v2/release-gate-v2.json")
    assert gate["critical_invariants"] == 1.0
    assert gate["trajectory_success"] == 0.95
    assert gate["minimum_family_success"] == 0.90
    assert gate["wrong_target_mutations"] == 0
```

- [ ] **Step 2: Ejecutar los tests y confirmar que fallan por archivos ausentes**

Run: `pytest tests/contract/test_agent_contracts_v4.py tests/contract/test_preference_policy.py tests/contract/test_conversation_trajectories_v2.py -q`

Expected: FAIL con `FileNotFoundError` para contratos v4/v2.

- [ ] **Step 3: Crear schemas con enums y restricciones cerradas**

La interpretación debe exigir este núcleo:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "required": ["contract_version", "interpretation_version", "acts", "ambiguity"],
  "properties": {
    "contract_version": {"const": "4"},
    "interpretation_version": {"const": "conversation-interpretation-v4"},
    "acts": {"type": "array", "items": {"$ref": "#/$defs/act"}},
    "ambiguity": {"type": ["object", "null"]}
  }
}
```

`preference-policy-v1.json` debe fijar:

```json
{
  "contract_version": "1",
  "authority_order": ["explicit", "deliberate_feedback", "passive"],
  "auto_apply": ["soft_add", "soft_revise", "soft_withdraw", "open_location"],
  "require_confirmation": ["hard_filter", "material_contradiction", "irreversible_delete"],
  "semantic": {"mode": "soft", "max_weight": 0.10, "missing_evidence_contribution": 0.0}
}
```

- [ ] **Step 4: Validar que los contratos se parsean y los tests pasan**

Run: `pytest tests/contract/test_agent_contracts_v4.py tests/contract/test_preference_policy.py tests/contract/test_conversation_trajectories_v2.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add contracts/agent/v4 contracts/preferences/v1 contracts/scoring/v2 contracts/search-profiles/v2 contracts/agent-evals/v2 tests/contract/test_agent_contracts_v4.py tests/contract/test_preference_policy.py tests/contract/test_conversation_trajectories_v2.py
git commit -m "feat: publish conversational copilot contracts"
```

### Task 2: Hacer que el radar parcial sea un estado válido

**Files:**
- Modify: `src/umbral/application/radar/contracts.py`
- Modify: `src/umbral/application/radar/profile_policy.py`
- Modify: `src/umbral/application/radar/hard_filters.py`
- Modify: `src/umbral/application/radar/scoring.py`
- Modify: `src/umbral/application/radar/service.py`
- Modify: `src/umbral/infrastructure/db/repositories/radar.py`
- Modify: `src/umbral/api/routers/search_profiles.py`
- Modify: `tests/fakes/radar.py`
- Modify: `tests/support/radar.py`
- Modify: `tests/unit/application/radar/test_profile_service.py`
- Modify: `tests/unit/application/radar/test_hard_filters.py`
- Modify: `tests/unit/application/radar/test_learning_seams.py`

**Interfaces:**
- Consumes: `search-profile-policy-v2` de Task 1.
- Produces: `SearchProfile.budget_max: float | None`, `SearchProfile.min_rooms: int | None`, `RadarService.version_profile(...)` y `RadarService.schedule_version_run(...)`.

- [ ] **Step 1: Escribir tests para perfil parcial y alcance abierto**

```python
def test_create_partial_profile_is_active_without_constraints(radar_context):
    profile, run = radar_context.service.create_profile(
        owner_id=radar_context.owner_id,
        name="Nueva búsqueda",
        zones=(),
        budget_max=None,
        budget_min=None,
        min_rooms=None,
        surface_min=None,
        surface_max=None,
        unknown_strategy=None,
        correlation_id=uuid4(),
    )
    assert profile.status == "active"
    assert profile.zones == ()
    assert profile.budget_max is None
    assert profile.min_rooms is None

def test_open_profile_does_not_filter_known_caba_listing(profile, listing):
    profile = replace(profile, zones=(), budget_max=None, min_rooms=None)
    assert apply_hard_filters(listing, profile) is True
```

- [ ] **Step 2: Ejecutar los tests y confirmar los fallos de tipos/validación**

Run: `pytest tests/unit/application/radar/test_profile_service.py tests/unit/application/radar/test_hard_filters.py -q`

Expected: FAIL porque presupuesto y zona siguen requeridos.

- [ ] **Step 3: Cambiar contrato y policy sin sentinelas**

```python
@dataclass(frozen=True, slots=True)
class SearchProfile:
    # campos existentes omitidos aquí conservan su nombre y orden lógico
    zones: tuple[str, ...]
    budget_max: float | None
    budget_min: float | None
    min_rooms: int | None

    @property
    def budget_bound(self) -> float | None:
        return self.budget_max
```

`validate_profile` acepta `zones=[]`, `budget_max=None`, `min_rooms=None`; si existen ambos presupuestos exige `0 <= budget_min < budget_max`.

- [ ] **Step 4: Hacer filtros y candidate query condicionales**

```python
if profile.budget_max is not None:
    if listing.total_cost is None or listing.total_cost > profile.budget_max:
        return False

if profile.zones:
    if listing.neighborhood is None:
        return False
    if listing.neighborhood.casefold() not in _zones_casefold(profile):
        return False

if profile.min_rooms is not None and profile.min_rooms > 0:
    # conservar la estrategia unknown existente
```

- [ ] **Step 5: Separar versionado de scheduling para coalescer un turno**

Agregar firmas exactas:

```python
def version_profile(
    self,
    *,
    owner_id: UUID,
    profile_id: UUID,
    expected_version: int,
    changes: Mapping[str, object],
    correlation_id: UUID,
    actor_kind: str = "service",
    actor_id: str | None = None,
) -> tuple[SearchProfile, ProfileVersion]: ...

def schedule_version_run(
    self,
    *,
    profile: SearchProfile,
    version: ProfileVersion,
    trigger: RecommendationRunTrigger,
) -> RecommendationRun | None: ...
```

`update_profile` queda como wrapper compatible que llama ambas funciones. `bump_profile_version` reutiliza el mismo snapshot path.

- [ ] **Step 6: Actualizar schemas HTTP manteniendo requests legacy**

```python
class CreateSearchProfileRequest(BaseModel):
    name: str
    zones: list[str] = Field(default_factory=list)
    budget_max: float | None = None
    budget_min: float | None = None
    min_rooms: int | None = None
    surface_min: float | None = None
    surface_max: float | None = None
```

- [ ] **Step 7: Ejecutar unidad y contratos de radar**

Run: `pytest tests/unit/application/radar tests/contract/test_scoring_baseline.py tests/contract/test_chat_http_contract.py -q`

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add src/umbral/application/radar src/umbral/infrastructure/db/repositories/radar.py src/umbral/api/routers/search_profiles.py tests/fakes/radar.py tests/support/radar.py tests/unit/application/radar
git commit -m "feat: support partial search radars"
```

### Task 3: Implementar el módulo profundo de expresiones y bindings

**Files:**
- Create: `src/umbral/application/preferences/__init__.py`
- Create: `src/umbral/application/preferences/contracts.py`
- Create: `src/umbral/application/preferences/ports.py`
- Create: `src/umbral/application/preferences/policy.py`
- Create: `src/umbral/application/preferences/service.py`
- Create: `tests/fakes/preferences.py`
- Create: `tests/unit/application/preferences/test_policy.py`
- Create: `tests/unit/application/preferences/test_service.py`
- Create: `tests/architecture/test_preferences_boundaries.py`

**Interfaces:**
- Consumes: `ConceptReader`, `PreferencePolicySpec`, optional `PreferenceEmbeddingGateway`.
- Produces: `PreferenceExpression`, `CriterionBinding`, `BindingDraft`, `PreferenceChange`, `PreferenceView`, `PreferenceService`.

- [ ] **Step 1: Escribir tests de conservación, corrección y jerarquía**

```python
def test_unknown_desire_is_preserved_without_fact(preference_service):
    change = preference_service.record_expression(
        profile_id=uuid4(),
        source_message_id=uuid4(),
        subject_key="cocina_grande",
        raw_text="quiero una cocina grande",
        authority="explicit",
        binding_drafts=(BindingDraft.unresolved("no_reliable_evidence"),),
        correlation_id=uuid4(),
    )
    assert change.expression.raw_text == "quiero una cocina grande"
    assert change.bindings[0].kind == "unresolved"
    assert change.fact_ids == ()

def test_passive_signal_cannot_supersede_explicit_expression(preference_service, explicit_expression):
    with pytest.raises(PreferenceAuthorityError):
        preference_service.revise_expression(
            profile_id=explicit_expression.profile_id,
            previous_expression_id=explicit_expression.expression_id,
            source_message_id=None,
            raw_text="parece que no quiere balcon",
            authority="passive",
            binding_drafts=(BindingDraft.unresolved("passive_only"),),
            correlation_id=uuid4(),
        )
```

- [ ] **Step 2: Ejecutar tests y confirmar imports ausentes**

Run: `pytest tests/unit/application/preferences -q`

Expected: FAIL con `ModuleNotFoundError: umbral.application.preferences`.

- [ ] **Step 3: Definir valores puros y factories seguras**

```python
PreferenceAuthority = Literal["explicit", "deliberate_feedback", "passive"]
BindingKind = Literal["structured", "semantic", "unresolved", "forbidden"]
PreferenceStatus = Literal["active", "superseded", "withdrawn"]
BindingMode = Literal["soft", "hard"]

@dataclass(frozen=True, slots=True)
class BindingDraft:
    kind: BindingKind
    concept_key: str | None
    matcher_type: MatcherType | None
    mode: BindingMode
    params: Mapping[str, object]
    confidence: float
    evidence_refs: tuple[Mapping[str, object], ...]
    limitations: tuple[str, ...]
    query_embedding: tuple[float, ...] | None = None
    embedding_version_id: UUID | None = None
```

Factories `structured(...)`, `semantic(...)`, `unresolved(reason)` y `forbidden(reason)` deben producir combinaciones válidas sin que callers construyan estados imposibles.

- [ ] **Step 4: Implementar policy pura**

```python
def can_supersede(current: PreferenceAuthority, incoming: PreferenceAuthority) -> bool:
    order = {"passive": 0, "deliberate_feedback": 1, "explicit": 2}
    return order[incoming] >= order[current]

def validate_binding(draft: BindingDraft, policy: PreferencePolicySpec) -> tuple[str, ...]:
    # semantic: soft, vector+version, max weight en compilación
    # unresolved/forbidden: sin matcher ni vector
    # hard: solo structured y con confirmación registrada por el caller
```

- [ ] **Step 5: Implementar `PreferenceService` con append/supersede atómico a través de puertos**

```python
class ExpressionRepository(Protocol):
    def insert(self, expression: PreferenceExpression) -> None: ...
    def get(self, expression_id: UUID) -> PreferenceExpression | None: ...
    def active_for_profile(self, profile_id: UUID) -> tuple[PreferenceExpression, ...]: ...
    def supersede(self, previous_id: UUID, replacement_id: UUID) -> None: ...
    def withdraw(self, expression_id: UUID) -> None: ...

class BindingRepository(Protocol):
    def insert_many(self, bindings: tuple[CriterionBinding, ...]) -> None: ...
    def active_for_expression_ids(self, expression_ids: tuple[UUID, ...]) -> tuple[CriterionBinding, ...]: ...
    def supersede_for_expression(self, expression_id: UUID) -> None: ...
```

El servicio solo llama `FactWriter` para bindings estructurados computables; semánticos, unresolved y forbidden quedan fuera de `PreferenceFact`.

- [ ] **Step 6: Probar corrección, retiro, varias vinculaciones y política prohibida**

Run: `pytest tests/unit/application/preferences tests/architecture/test_preferences_boundaries.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add src/umbral/application/preferences tests/fakes/preferences.py tests/unit/application/preferences tests/architecture/test_preferences_boundaries.py
git commit -m "feat: preserve preference expressions and bindings"
```

### Task 4: Persistir y migrar expresiones, radar parcial y runs superseded

**Files:**
- Create: `src/umbral/infrastructure/db/models/preferences.py`
- Create: `src/umbral/infrastructure/db/repositories/preferences.py`
- Modify: `src/umbral/infrastructure/db/models/__init__.py`
- Modify: `src/umbral/infrastructure/db/repositories/__init__.py`
- Modify: `src/umbral/infrastructure/db/models/radar.py`
- Modify: `src/umbral/infrastructure/db/models/chat.py`
- Modify: `src/umbral/infrastructure/db/models/criteria.py`
- Create: `alembic/versions/0016_conversational_search_copilot.py`
- Create: `tests/migrations/test_0016_conversational_search_copilot.py`
- Create: `tests/integration/preferences/conftest.py`
- Create: `tests/integration/preferences/test_repository.py`
- Modify: `tests/integration/chat/test_session_repo.py`

**Interfaces:**
- Consumes: domain types y repositorios de Task 3; nullable fields de Task 2.
- Produces: `SqlAlchemyExpressionRepository`, `SqlAlchemyBindingRepository`, schema DB revision `0016`.

- [ ] **Step 1: Escribir test de migración upgrade/backfill**

```python
def test_0016_backfills_fact_lineage(connection, migrate_to):
    migrate_to("0015")
    fact_id = seed_preference_fact(connection, concept_key="balcon", value="si")
    migrate_to("0016")
    row = connection.execute(sa.text("""
        SELECT pf.criterion_binding_id, pe.source_kind, pe.original_text_available
        FROM preference_facts pf
        JOIN criterion_bindings cb ON cb.id = pf.criterion_binding_id
        JOIN preference_expressions pe ON pe.id = cb.expression_id
        WHERE pf.id = :fact_id
    """), {"fact_id": fact_id}).one()
    assert row.source_kind == "migration"
    assert row.original_text_available is False
```

- [ ] **Step 2: Escribir tests de repositorio para cadena superseded y múltiples bindings**

Run: `pytest tests/migrations/test_0016_conversational_search_copilot.py tests/integration/preferences/test_repository.py -q`

Expected: FAIL por tablas y adapters ausentes.

- [ ] **Step 3: Crear modelos con checks relacionales de forma**

El modelo `CriterionBinding` debe incluir:

```python
CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_criterion_bindings_confidence")
CheckConstraint("mode IN ('soft', 'hard')", name="ck_criterion_bindings_mode")
CheckConstraint("kind <> 'semantic' OR mode = 'soft'", name="ck_criterion_bindings_semantic_soft")
CheckConstraint("kind NOT IN ('unresolved', 'forbidden') OR concept_key IS NULL", name="ck_criterion_bindings_unbound_without_concept")
```

Usar `Vector(1536)` para `query_embedding`, `JSONB` para refs/limitaciones/params y FKs `RESTRICT` salvo `source_message_id ON DELETE SET NULL`.

- [ ] **Step 4: Implementar migración con downgrade guardado**

Upgrade exacto:

1. tablas e índices nuevos;
2. `preference_facts.criterion_binding_id`;
3. nullable de radar/chat;
4. checks de presupuesto;
5. enum `recommendation_run_state += superseded`;
6. `recommendation_runs.diagnostics JSONB NOT NULL DEFAULT '{}'`;
7. backfill SQL de expresiones/bindings/facts.

Downgrade debe consultar filas incompatibles y lanzar `RuntimeError("0016 downgrade would invent required search constraints")` si existen.

- [ ] **Step 5: Implementar adapters y mappings completos**

No exponer vectores en `PreferenceView`; cargarlos únicamente mediante `BindingRepository.active_semantic_for_profile_version(...)` para scoring.

- [ ] **Step 6: Ejecutar migración, repositorios y chat nullable**

Run: `pytest tests/migrations/test_0016_conversational_search_copilot.py tests/integration/preferences tests/integration/chat/test_session_repo.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add src/umbral/infrastructure/db/models src/umbral/infrastructure/db/repositories alembic/versions/0016_conversational_search_copilot.py tests/migrations/test_0016_conversational_search_copilot.py tests/integration/preferences tests/integration/chat/test_session_repo.py
git commit -m "feat: persist conversational preference lineage"
```

### Task 5: Crear interpretación multi-acto y política de materialidad

**Files:**
- Create: `src/umbral/application/conversation/__init__.py`
- Create: `src/umbral/application/conversation/contracts.py`
- Create: `src/umbral/application/conversation/policy.py`
- Create: `src/umbral/agent/interpretation/__init__.py`
- Create: `src/umbral/agent/interpretation/compiler.py`
- Modify: `src/umbral/infrastructure/agent/managed_gateway.py`
- Create: `tests/unit/application/conversation/test_policy.py`
- Create: `tests/unit/agent/interpretation/test_compiler.py`
- Create: `tests/fixtures/agent/interpretation-v4.json`

**Interfaces:**
- Consumes: schemas y preference policy de Task 1.
- Produces: `ConversationAct`, `ConversationInterpretation`, `ConversationContext`, `PlannedEffect`, `compile_interpretation(...)`, `plan_effects(...)`.

- [ ] **Step 1: Escribir tests para pending primero, actos restantes y ambigüedad material**

```python
def test_pending_resolution_must_be_first(context_with_pending):
    result = compile_interpretation(
        model_payload={
            "contract_version": "4",
            "interpretation_version": "conversation-interpretation-v4",
            "acts": [
                act("resolve_pending", {"decision": "approve"}),
                act("express_preference", {"subject_key": "balcon", "text": "tambien quiero balcon"}),
            ],
            "ambiguity": None,
        },
        context=context_with_pending,
    )
    assert [item.kind for item in result.acts] == ["resolve_pending", "express_preference"]

def test_soft_effect_applies_while_hard_effect_waits(context):
    effects = plan_effects(context, interpretation_with_soft_and_hard())
    assert [e.requires_confirmation for e in effects] == [False, True]
```

- [ ] **Step 2: Ejecutar tests y confirmar módulos ausentes**

Run: `pytest tests/unit/application/conversation/test_policy.py tests/unit/agent/interpretation/test_compiler.py -q`

Expected: FAIL con módulos ausentes.

- [ ] **Step 3: Definir contexto verificable**

```python
@dataclass(frozen=True, slots=True)
class ConversationContext:
    user_id: UUID
    session_id: UUID
    search_profile_id: UUID | None
    profile_version: int | None
    active_listing_id: UUID | None
    visible_listing_ids: tuple[UUID, ...]
    pending_action: Mapping[str, object] | None
    answered_slots: Mapping[str, object]
```

Todo target del modelo se intersecta con estos IDs. “Este depto” solo resuelve si hay una referencia única.

- [ ] **Step 4: Implementar compilación cerrada y fallos sanitizados**

```python
def compile_interpretation(
    *, model_payload: Mapping[str, object], context: ConversationContext
) -> ConversationInterpretation:
    validate_json_schema(model_payload, "agent/v4/interpretation-schema-v4.json")
    interpretation = parse_acts(model_payload)
    validate_pending_precedence(interpretation, context)
    validate_targets(interpretation, context)
    return interpretation
```

- [ ] **Step 5: Implementar materialidad pura**

`plan_effects` consolida varios `set_filter` al mismo radar, auto-aplica soft/reversible y marca solo hard/contradicción/eliminación irreversible como pendiente. Máximo una pregunta, elegida por mayor impacto estimado.

- [ ] **Step 6: Probar mensajes contradictorios, referencias y política de equidad**

Run: `pytest tests/unit/application/conversation tests/unit/agent/interpretation -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add src/umbral/application/conversation src/umbral/agent/interpretation src/umbral/infrastructure/agent/managed_gateway.py tests/unit/application/conversation tests/unit/agent/interpretation tests/fixtures/agent/interpretation-v4.json
git commit -m "feat: interpret conversational turns as ordered acts"
```

### Task 6: Implementar `ConversationTurnService` y binding de sesión

**Files:**
- Create: `src/umbral/application/conversation/ports.py`
- Create: `src/umbral/application/conversation/service.py`
- Modify: `src/umbral/application/chat/contracts.py`
- Modify: `src/umbral/application/chat/ports.py`
- Modify: `src/umbral/application/chat/service.py`
- Modify: `src/umbral/infrastructure/db/repositories/chat.py`
- Modify: `src/umbral/infrastructure/agent/composition.py`
- Modify: `src/umbral/infrastructure/agent/production.py`
- Create: `tests/unit/application/conversation/test_service.py`
- Modify: `tests/unit/application/chat/test_service.py`

**Interfaces:**
- Consumes: `PlannedEffect` de Task 5, `PreferenceService` de Task 3, `RadarService.version_profile/schedule_version_run` de Task 2.
- Produces: `ConversationTurnService.plan_turn(...)`, `apply_turn(...)`, `ChatService.bind_profile(...)`, `ConversationTurnResult`.

- [ ] **Step 1: Escribir test del primer deseo hasta radar durable**

```python
def test_first_significant_turn_creates_and_binds_partial_radar(turn_service, context):
    effects = turn_service.plan_turn(
        context=context,
        interpretation=interpretation(
            create_radar(),
            express("luminosidad", "un depto luminoso"),
            express("subte", "cerca del subte"),
        ),
    )
    result = turn_service.apply_turn(
        user_id=context.user_id,
        session_id=context.session_id,
        message_id=uuid4(),
        effects=effects,
        correlation_id=uuid4(),
    )
    assert result.search_profile_id is not None
    assert result.profile_version_id is not None
    assert [effect.status for effect in result.effects] == ["applied", "applied", "applied"]
    assert turn_service.chat.get_session(user_id=context.user_id, session_id=context.session_id).search_profile_id == result.search_profile_id
```

- [ ] **Step 2: Escribir test de un solo versionado/refresh por turno**

```python
def test_multiple_reversible_effects_schedule_one_run(turn_service, bound_context):
    result = execute(bound_context, set_zone("nunez"), express("balcon", "quiero balcon"))
    assert turn_service.radar.recorded_version_calls == 1
    assert turn_service.radar.recorded_schedule_calls == 1
    assert result.refresh_run_id is not None
```

- [ ] **Step 3: Ejecutar tests y confirmar que faltan service/bind**

Run: `pytest tests/unit/application/conversation/test_service.py tests/unit/application/chat/test_service.py -q`

Expected: FAIL.

- [ ] **Step 4: Hacer la sesión nullable y bind-once**

```python
def bind_profile(
    self,
    *,
    user_id: UUID,
    session_id: UUID,
    search_profile_id: UUID,
    correlation_id: UUID,
) -> ChatSession:
    session = self.get_session(user_id=user_id, session_id=session_id)
    if session.search_profile_id not in (None, search_profile_id):
        raise ChatSessionAlreadyBound()
    self._profile_status(search_profile_id)
    return self.sessions.bind_profile(session, search_profile_id, correlation_id)
```

- [ ] **Step 5: Aplicar efectos por clase y consolidar perfil**

Secuencia dentro de la transacción del turno:

1. validar todos los effects y crear nombre `Nueva búsqueda[ n]` desde nombres existentes;
2. crear/bind radar si hace falta;
3. persistir expresiones/bindings seguros;
4. consolidar filtros en un único `changes`;
5. versionar radar una vez;
6. compilar criterios para esa versión;
7. encolar un run;
8. devolver estado por acto; mantener el effect material como `pending`.

- [ ] **Step 6: Emitir eventos de lineage**

Agregar al registry y emitir `preference.expression_recorded.v1`, `preference.binding_recorded.v1`, `preference.expression_superseded.v1` y `chat.session_bound.v1` con IDs, nunca texto/vector crudo en el evento.

- [ ] **Step 7: Ejecutar tests unitarios y de arquitectura**

Run: `pytest tests/unit/application/conversation/test_service.py tests/unit/application/chat/test_service.py tests/architecture/test_agent_boundaries.py tests/architecture/test_criteria_boundaries.py -q`

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add src/umbral/application/conversation src/umbral/application/chat src/umbral/infrastructure/db/repositories/chat.py src/umbral/infrastructure/agent/composition.py src/umbral/infrastructure/agent/production.py contracts/events/v1/events-registry.json tests/unit/application/conversation/test_service.py tests/unit/application/chat/test_service.py
git commit -m "feat: apply conversational turns to durable radar state"
```

### Task 7: Reemplazar el atajo de confirmación por el grafo v4

**Files:**
- Modify: `src/umbral/agent/state.py`
- Modify: `src/umbral/agent/graph.py`
- Modify: `src/umbral/agent/runtime.py`
- Modify: `src/umbral/api/routers/chat.py`
- Modify: `src/umbral/application/agent/contracts.py`
- Modify: `src/umbral/infrastructure/db/models/agent.py`
- Create: `tests/unit/agent/test_graph_v4.py`
- Modify: `tests/unit/agent/test_runtime_v3.py`
- Modify: `tests/integration/chat/test_hitl_lifecycle.py`
- Modify: `tests/integration/chat/test_streaming_router.py`

**Interfaces:**
- Consumes: `ConversationTurnService` y `compile_interpretation`.
- Produces: state schema version `4`, topology v4 y resume payload `{ "text": str }`.

- [ ] **Step 1: Escribir regresión exacta para confirmación más preferencia**

```python
def test_resume_keeps_full_text_and_executes_remaining_act(client, interrupted_session):
    response = client.post(
        f"/api/chat/sessions/{interrupted_session.id}/messages",
        json={"text": "Sí, confirmo, y también quiero balcón", "client_message_id": str(uuid4())},
    )
    events = collect_sse(response)
    assert effect(events, "proposal", "applied")
    assert effect(events, "preference", "applied")
    assert not any(e.get("error", {}).get("code") == "feedback.listing_required" for e in events)
```

- [ ] **Step 2: Ejecutar y observar el 409/drop actual**

Run: `pytest tests/integration/chat/test_hitl_lifecycle.py tests/integration/chat/test_streaming_router.py -q`

Expected: FAIL porque `_natural_decision` exige coincidencia exacta o reanuda con texto vacío.

- [ ] **Step 3: Extender estado v4 sin romper lectura de v3**

```python
class AgentState(TypedDict, total=False):
    # campos v3 existentes
    interpretation: object | None
    planned_effects: list[dict[str, object]]
    effect_results: list[dict[str, object]]
```

Los checkpoints v3 solo se reanudan por el flow legacy; sesiones nuevas estampan v4.

- [ ] **Step 4: Cambiar topology a nodos profundos**

```text
load_context -> interpret_turn -> plan_effects -> apply_safe_effects
apply_safe_effects -> require_confirmation | schedule_refresh | compose_reply
require_confirmation -> END(interrupted)
resume -> resolve_pending -> interpret_remaining -> plan_effects
schedule_refresh -> compose_reply -> persist_reply -> END
```

- [ ] **Step 5: Eliminar `_natural_decision` y pasar el texto completo**

```python
if active_run.status == "interrupted":
    runtime.run_turn(
        session_id=session_id,
        user_id=user.id,
        user_message_text=text,
        decision={"text": text},
        emit=emit,
    )
```

No devolver `409` por vocabulario. Una respuesta realmente ambigua vuelve a interrumpir con una sola pregunta.

- [ ] **Step 6: Ejecutar graph/runtime/HITL**

Run: `pytest tests/unit/agent/test_graph_v4.py tests/unit/agent/test_runtime_v3.py tests/integration/chat/test_hitl_lifecycle.py tests/integration/chat/test_streaming_router.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add src/umbral/agent src/umbral/api/routers/chat.py src/umbral/application/agent/contracts.py src/umbral/infrastructure/db/models/agent.py tests/unit/agent/test_graph_v4.py tests/unit/agent/test_runtime_v3.py tests/integration/chat/test_hitl_lifecycle.py tests/integration/chat/test_streaming_router.py
git commit -m "feat: resume pending chat actions with full user turns"
```

### Task 8: Compilar bindings y puntuar señales semánticas congeladas

**Files:**
- Modify: `src/umbral/application/criteria/contracts.py`
- Modify: `src/umbral/application/criteria/compile.py`
- Modify: `src/umbral/application/criteria/service.py`
- Modify: `src/umbral/application/scoring/contracts.py`
- Modify: `src/umbral/application/scoring/ports.py`
- Modify: `src/umbral/application/scoring/engine.py`
- Modify: `src/umbral/application/scoring/evaluators.py`
- Modify: `src/umbral/application/scoring/service.py`
- Modify: `src/umbral/infrastructure/db/repositories/scoring.py`
- Create: `tests/unit/application/scoring/test_semantic_bindings.py`
- Create: `tests/unit/application/scoring/test_active_criteria.py`
- Modify: `tests/unit/application/criteria/test_compile_service.py`
- Modify: `tests/integration/scoring/test_scoring_lineage.py`

**Interfaces:**
- Consumes: bindings persistidos de Task 4 y perfil nullable de Task 2.
- Produces: `CompiledCriterion(criterion_key, concept_key, binding_id, mode, ...)`, `SemanticSignal`, `ScoringRunResult`.

- [ ] **Step 1: Escribir tests de cero evidencia, cap semántico y criterios no declarados**

```python
def test_semantic_binding_without_signal_contributes_zero(scoring_inputs):
    result = score_candidates(**scoring_inputs, semantic_signals={})
    evaluation = evaluation_for(result, "binding:semantic-id")
    assert evaluation.state == "unknown"
    assert evaluation.contribution == 0

def test_undeclared_balcony_does_not_affect_rank(scoring_inputs):
    result = score_candidates(**scoring_inputs, compilation=empty_compilation())
    assert all("balcon" not in item.contributions for item in result.candidates)

def test_semantic_weight_is_capped_and_confidence_adjusted(scoring_inputs):
    result = score_candidates(**scoring_inputs, compilation=semantic_compilation(weight=0.8), semantic_signals=signal(score=0.9, confidence=0.5))
    assert evaluation_for(result, "binding:semantic-id").contribution == 0.045
```

- [ ] **Step 2: Ejecutar tests y confirmar semántica/activación actuales**

Run: `pytest tests/unit/application/scoring/test_semantic_bindings.py tests/unit/application/scoring/test_active_criteria.py -q`

Expected: FAIL: engine solo lee observaciones por concepto y activa policy global.

- [ ] **Step 3: Evolucionar criterio compilado**

```python
@dataclass(frozen=True, slots=True)
class CompiledCriterion:
    criterion_key: str
    concept_key: str | None
    binding_id: UUID | None
    matcher_type: MatcherType
    mode: Literal["soft", "hard"]
    params: Mapping[str, object]
    source_ref: str
    weight: float | None = None
```

Facts legacy generan `criterion_key=concept_key`; bindings semánticos generan `criterion_key=f"binding:{binding_id}"`, `concept_key=None`.

- [ ] **Step 4: Implementar `SemanticSignalReader` y similitud compatible**

```python
class SemanticSignalReader(Protocol):
    def for_run(
        self,
        *,
        bindings: tuple[CriterionBinding, ...],
        listing_ids: tuple[UUID, ...],
    ) -> Mapping[UUID, Mapping[UUID, SemanticSignal]]: ...
```

El adapter calcula cosine solo si ambos embeddings comparten `extraction_version_id`; refs apuntan a binding y listing embedding.

- [ ] **Step 5: Activar solo criterios declarados y normalizar**

```python
active = active_criteria(profile=profile, compilation=compilation, policy=policy)
active_weight = sum(item.weight for item in active if item.weight > 0)
raw = sum(evaluation.contribution for evaluation in evaluations)
score = 0.0 if active_weight == 0 else raw / active_weight
```

Los criterios fixed se activan solo si su campo existe; los opcionales, solo si hay criterio compilado. Un hard structured mismatch excluye; unknown sigue la estrategia versionada. Semántica nunca excluye.

- [ ] **Step 6: Mantener lineage en evaluación y explicación**

`input_refs` semánticos deben contener `criterion_binding`, `query_embedding` y `listing_embedding`. `params` no serializa el vector.

- [ ] **Step 7: Ejecutar criterios/scoring unit e integración**

Run: `pytest tests/unit/application/criteria tests/unit/application/scoring tests/integration/scoring/test_scoring_lineage.py -q`

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add src/umbral/application/criteria src/umbral/application/scoring src/umbral/infrastructure/db/repositories/scoring.py tests/unit/application/criteria tests/unit/application/scoring tests/integration/scoring/test_scoring_lineage.py
git commit -m "feat: score auditable semantic preference bindings"
```

### Task 9: Evitar publicación obsoleta y diagnosticar cero resultados

**Files:**
- Modify: `src/umbral/application/radar/contracts.py`
- Modify: `src/umbral/application/radar/ports.py`
- Modify: `src/umbral/application/radar/service.py`
- Modify: `src/umbral/application/scoring/contracts.py`
- Modify: `src/umbral/application/scoring/engine.py`
- Modify: `src/umbral/infrastructure/db/repositories/radar.py`
- Modify: `src/umbral/workers/radar.py`
- Create: `tests/unit/application/radar/test_run_supersession.py`
- Create: `tests/unit/application/scoring/test_exclusion_diagnostics.py`
- Modify: `tests/integration/radar/test_run_pipeline.py`

**Interfaces:**
- Consumes: `ScoringRunResult` de Task 8 y `SearchProfile.current_version_id`.
- Produces: `RecommendationRun.state="superseded"`, `RunDiagnostics`, relajaciones deterministas.

- [ ] **Step 1: Escribir tests de carrera entre versiones**

```python
def test_old_run_cannot_publish_after_new_profile_version(radar_stack):
    old = radar_stack.pending_run(version=1)
    radar_stack.advance_profile_to(version=2)
    finished = radar_stack.service.process_run(run_id=old.run_id, correlation_id=uuid4())
    assert finished.state == "superseded"
    assert radar_stack.profiles.get(old.profile_id).latest_run_id != old.run_id
```

- [ ] **Step 2: Escribir test de exclusiones solo hard**

```python
def test_zero_match_diagnostics_exclude_soft_preferences(scoring_inputs):
    result = score_candidates(**scoring_inputs)
    assert result.candidates == ()
    assert result.exclusion_counts == {"presupuesto": 3, "ubicacion": 2}
    assert "luminosidad" not in result.exclusion_counts
```

- [ ] **Step 3: Ejecutar y confirmar publicación/diagnóstico ausente**

Run: `pytest tests/unit/application/radar/test_run_supersession.py tests/unit/application/scoring/test_exclusion_diagnostics.py -q`

Expected: FAIL.

- [ ] **Step 4: Agregar checks antes de scoring y publicación**

```python
def _is_current_run(self, run: RecommendationRun) -> bool:
    profile = self.profiles.get(run.profile_id)
    return profile is not None and profile.current_version_id == run.profile_version_id
```

Si es falso, `runs.supersede(run)` y terminar sin cargar candidatos. Repetir el check dentro de `publish` para cerrar la carrera.

- [ ] **Step 5: Persistir diagnóstico y generar relajaciones sin mutar**

```python
def propose_relaxations(exclusion_counts: Mapping[str, int]) -> tuple[Mapping[str, object], ...]:
    return tuple(
        {"criterion_key": key, "excluded_count": count, "action": "relax"}
        for key, count in sorted(exclusion_counts.items(), key=lambda item: (-item[1], item[0]))
        if count > 0
    )
```

- [ ] **Step 6: Ejecutar pipeline de radar completo**

Run: `pytest tests/unit/application/radar/test_run_supersession.py tests/unit/application/scoring/test_exclusion_diagnostics.py tests/integration/radar/test_run_pipeline.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add src/umbral/application/radar src/umbral/application/scoring src/umbral/infrastructure/db/repositories/radar.py src/umbral/workers/radar.py tests/unit/application/radar/test_run_supersession.py tests/unit/application/scoring/test_exclusion_diagnostics.py tests/integration/radar/test_run_pipeline.py
git commit -m "feat: supersede stale runs and explain empty results"
```

### Task 10: Exponer estado durable y progreso por API/SSE

**Files:**
- Modify: `src/umbral/api/routers/chat.py`
- Modify: `src/umbral/api/routers/search_profiles.py`
- Modify: `src/umbral/application/chat/contracts.py`
- Modify: `src/umbral/agent/events.py`
- Modify: `contracts/chat/v1/streaming-events-v1.json`
- Modify: `tests/contract/test_agent_chat_events.py`
- Modify: `tests/contract/test_chat_http_contract.py`
- Create: `tests/integration/api/test_chat_copilot_e2e.py`

**Interfaces:**
- Consumes: `ConversationTurnResult`, `PreferenceService.active_view`, run diagnostics.
- Produces: sesión sin perfil, `state`/`progress` SSE y `GET /api/search-profiles/{id}/preferences`.

- [ ] **Step 1: Escribir contrato HTTP de sesión opcional**

```python
def test_create_unbound_chat_session(client, auth_headers):
    response = client.post("/api/chat/sessions", json={}, headers=auth_headers)
    assert response.status_code == 201
    assert response.json()["search_profile_id"] is None
```

- [ ] **Step 2: Escribir e2e de primer turno y estado estructurado**

```python
def test_first_turn_emits_durable_state_before_done(client, unbound_session):
    events = send_turn(client, unbound_session, "quiero un depto luminoso y cerca del subte")
    state_index = next(i for i, event in enumerate(events) if event["type"] == "state")
    done_index = next(i for i, event in enumerate(events) if event["type"] == "done")
    assert state_index < done_index
    assert events[state_index]["profile_id"]
```

- [ ] **Step 3: Ejecutar contratos y confirmar rutas/eventos ausentes**

Run: `pytest tests/contract/test_agent_chat_events.py tests/contract/test_chat_http_contract.py tests/integration/api/test_chat_copilot_e2e.py -q`

Expected: FAIL.

- [ ] **Step 4: Implementar responses sin exponer vectores**

```python
class PreferenceViewResponse(BaseModel):
    expression_id: UUID
    raw_text: str
    subject_key: str
    status: str
    binding_kind: str
    mode: str
    confidence: float
    limitations: list[str]
    evidence_refs: list[dict[str, object]]
```

- [ ] **Step 5: Emitir `state` inmediatamente después del commit y `progress` al encolar**

El `ack` sigue siendo primero. `state` no espera tokens de reply ni finalización del run. `done` contiene resumen breve y refs, no un dump del modelo.

- [ ] **Step 6: Ejecutar contratos/e2e**

Run: `pytest tests/contract/test_agent_chat_events.py tests/contract/test_chat_http_contract.py tests/integration/api/test_chat_copilot_e2e.py -q`

Expected: PASS.

- [ ] **Step 7: Exportar OpenAPI, regenerar cliente TypeScript y verificar diff limitado**

Run: `.\scripts\export-openapi.ps1`

Expected: `contracts/openapi/v1/openapi.json` refleja sesión opcional, preferencias y nuevos eventos.

Run: `npm run api:generate --workspace @umbral/web`

Expected: tipos `search_profile_id?: string | null`, `state`, `progress` y preferencias disponibles.

- [ ] **Step 8: Commit**

```powershell
git add src/umbral/api/routers/chat.py src/umbral/api/routers/search_profiles.py src/umbral/application/chat/contracts.py src/umbral/agent/events.py contracts/chat/v1/streaming-events-v1.json contracts/openapi/v1/openapi.json tests/contract/test_agent_chat_events.py tests/contract/test_chat_http_contract.py tests/integration/api/test_chat_copilot_e2e.py apps/web/src/lib/api/generated apps/web/src/lib/chat/types.ts
git commit -m "feat: expose conversational radar state and progress"
```

### Task 11: Convertir `/radar/new` en una experiencia chat-first

**Files:**
- Modify: `apps/web/src/app/(protected)/radar/new/page.tsx`
- Modify: `apps/web/src/components/chat/chat-panel.tsx`
- Modify: `apps/web/src/components/chat/message-list.tsx`
- Modify: `apps/web/src/components/chat/message-item.tsx`
- Modify: `apps/web/src/components/chat/composer.tsx`
- Create: `apps/web/src/components/chat/radar-context-strip.tsx`
- Create: `apps/web/src/components/chat/preference-state-list.tsx`
- Modify: `apps/web/src/lib/chat/use-chat-stream.ts`
- Modify: `apps/web/src/lib/chat/client.ts`
- Create or update from registry: `apps/web/src/components/ui/message-scroller.tsx`
- Create or update from registry: `apps/web/src/components/ui/message.tsx`
- Create or update from registry: `apps/web/src/components/ui/bubble.tsx`
- Create or update from registry: `apps/web/src/components/ui/marker.tsx`
- Create or update from registry: `apps/web/src/components/ui/empty.tsx`
- Create or update from registry: `apps/web/src/components/ui/badge.tsx`
- Create or update from registry: `apps/web/src/components/ui/input-group.tsx`
- Modify: `apps/web/src/components/chat/chat-panel.test.tsx`
- Create: `apps/web/src/components/chat/radar-context-strip.test.tsx`
- Create: `apps/web/src/app/(protected)/radar/new/page.test.tsx`

**Interfaces:**
- Consumes: API de Task 10 y componentes shadcn con aliases `@/*`, estilo Vega, RSC y Tailwind v4.
- Produces: sesión lazy sin radar, input siempre interactivo, contexto activo y estados `Aplicado`, `Tentativo`, `Sin evidencia`.

- [ ] **Step 1: Escribir tests de pantalla chat-first**

```tsx
it("starts a chat without requiring the old three-step form", async () => {
  render(<NewRadarPage />)
  expect(screen.getByPlaceholderText(/contame qué estás buscando/i)).toBeEnabled()
  expect(screen.queryByText(/paso 1 de 3/i)).not.toBeInTheDocument()
})

it("keeps the composer enabled while matches refresh", () => {
  render(<ChatPanel initialProfileId={null} initialEvents={[progressEvent]} />)
  expect(screen.getByRole("textbox")).toBeEnabled()
  expect(screen.getByText(/actualizando oportunidades/i)).toBeVisible()
})
```

- [ ] **Step 2: Ejecutar Vitest y confirmar que muestra el form actual**

Run: `npm --prefix apps/web test -- --run apps/web/src/app/(protected)/radar/new/page.test.tsx apps/web/src/components/chat/chat-panel.test.tsx`

Expected: FAIL.

- [ ] **Step 3: Instalar primitivas de chat shadcn**

Run: `npx shadcn@latest add message-scroller message bubble marker empty badge input-group --cwd apps/web`

Expected: componentes generados/actualizados respetando `apps/web/components.json`. Revisar cada diff y conservar estilos locales; si el registry renombra una primitiva, usar la primitiva equivalente documentada y mantener los exports locales enumerados en **Files**.

- [ ] **Step 4: Componer chat con estado visible y alternativa estructurada**

```tsx
<ChatPanel initialProfileId={null}>
  <RadarContextStrip profile={profile} refresh={refreshState} />
  <MessageScroller>
    <MessageList messages={messages} />
  </MessageScroller>
  <PreferenceStateList preferences={preferences} />
  <Composer disabled={sendState === "sending"} />
</ChatPanel>
```

El editor estructurado queda detrás de un enlace `Editar criterios` y no antecede al primer mensaje.

- [ ] **Step 5: Separar estado reactivo para evitar rerenders del input**

`useChatStream` expone hooks/selectores separados:

```ts
export function useChatMessages(): ChatMessage[]
export function useChatConnection(): ConnectionState
export function useRadarState(): RadarState | null
export function useRefreshProgress(): RefreshProgress | null
```

Mantener callback estable para enviar y evitar que cada token reconstruya el composer.

- [ ] **Step 6: Mostrar copy breve y corregible**

- `Aplicado`: binding estructurado o cambio durable.
- `Tentativo`: binding semántico de baja confianza.
- `Sin evidencia`: deseo conservado sin contribución.
- Pregunta: máximo una, debajo del resumen del estado aplicado.

- [ ] **Step 7: Ejecutar tests y build**

Run: `npm --prefix apps/web test -- --run`

Expected: PASS.

Run: `npm --prefix apps/web run build`

Expected: PASS sin hydration errors ni imports client-only desde server components.

- [ ] **Step 8: Commit**

```powershell
git add apps/web/src/app/(protected)/radar/new apps/web/src/components/chat apps/web/src/components/ui apps/web/src/lib/chat
git commit -m "feat: make radar creation a chat-first experience"
```

### Task 12: Reemplazar goldens aislados por trayectorias v2

**Files:**
- Modify: `src/umbral/application/agent_evals/contracts.py`
- Create: `src/umbral/application/agent_evals/trajectories.py`
- Modify: `src/umbral/application/agent_evals/runner.py`
- Modify: `src/umbral/application/agent_evals/metrics.py`
- Modify: `src/umbral/application/agent_evals/regression.py`
- Create: `contracts/agent-evals/v2/conversation-trajectories-v2.json`
- Modify: `src/umbral/infrastructure/agent_evals/real_flow.py`
- Modify: `src/umbral/infrastructure/agent_evals/composition.py`
- Create: `tests/unit/application/agent_evals/test_trajectories.py`
- Modify: `tests/unit/application/agent_evals/test_metrics.py`
- Create: `tests/integration/agent_evals/test_trajectory_suite.py`

**Interfaces:**
- Consumes: state/effects v4 y release gate de Task 1.
- Produces: `ConversationTrajectory`, `TurnExpectation`, `DurableStateSnapshot`, `TrajectoryResult`, gate agregado v2.

- [ ] **Step 1: Escribir parser tests con estado final y forbidden outcomes**

```python
def test_trajectory_requires_state_evolution(load_trajectory_dataset):
    dataset = load_trajectory_dataset()
    case = dataset.case_by_id("reported-zone-loop")
    assert len(case.turns) >= 10
    assert case.final_state["zones"] == []
    assert "nunez" in case.final_state["superseded_zone_values"]
    assert "no_repeated_answered_question" in case.invariants
```

- [ ] **Step 2: Corregir el golden erróneo de feedback**

En `contracts/agent-evals/v1/conversations-golden-v1.json`, el caso `Guarda este, me interesa` debe esperar `decision=like` y no `dislike/price_too_high`. Mantener v1 como baseline legacy, con nota de corrección product-reviewed.

- [ ] **Step 3: Ejecutar tests y confirmar soporte v2 ausente**

Run: `pytest tests/unit/application/agent_evals/test_trajectories.py tests/integration/agent_evals/test_trajectory_suite.py -q`

Expected: FAIL.

- [ ] **Step 4: Crear caso canónico con todos los turnos reportados**

El estado final exacto debe contener:

```json
{
  "zones": [],
  "active_subjects": ["luminosidad", "subte", "cocina_grande", "cafes_home_office", "parque"],
  "superseded_zone_values": ["nunez"],
  "wrong_listing_feedback_count": 0,
  "repeated_zone_question_count": 0
}
```

Agregar variantes de mayúsculas/acentos, `Confirmo`, `sí, confirmo y...`, cambio de radar, open zone y referencia a listing visible.

- [ ] **Step 5: Derivar métricas de snapshots, no de texto**

```python
@dataclass(frozen=True, slots=True)
class TrajectoryResult:
    case_id: str
    family: str
    final_state_ok: bool
    turn_effects_ok: bool
    critical_invariants_ok: bool
    forbidden_outcomes: tuple[str, ...]
    latency_p95_ms: int
```

El runner captura radar/versiones/expresiones/bindings/pending action después de cada turno y compara campos declarados.

- [ ] **Step 6: Implementar gate estricto agregado**

Bloquear si cualquier critical invariant falla, si `wrong_target_mutations > 0`, success global `<0.95` o cualquier familia `<0.90`. Reportar todas las razones, no solo la primera.

- [ ] **Step 7: Ejecutar unit/integration evals v1+v2**

Run: `pytest tests/unit/application/agent_evals tests/contract/test_agent_evals_golden.py tests/integration/agent_evals/test_trajectory_suite.py -q`

Expected: PASS para legacy v1 y v2.

- [ ] **Step 8: Commit**

```powershell
git add src/umbral/application/agent_evals src/umbral/infrastructure/agent_evals contracts/agent-evals/v1/conversations-golden-v1.json contracts/agent-evals/v2 tests/unit/application/agent_evals tests/integration/agent_evals/test_trajectory_suite.py
git commit -m "feat: gate agent releases on conversation trajectories"
```

### Task 13: Cerrar integración, performance y beta usability

**Files:**
- Modify: `tests/integration/api/test_chat_copilot_e2e.py`
- Create: `tests/e2e/chat-copilot.spec.ts`
- Create: `docs/product/chat-copilot-beta-protocol.md`
- Create: `docs/product/chat-copilot-release-checklist.md`
- Modify: `specs/011-conversational-ui/spec.md`
- Modify: `specs/014-soft-preferences-chat/spec.md`
- Modify: `specs/015-catalog-concept-expansion/spec.md`
- Modify: `README.md` only if its documented start flow contradicts chat-first.

**Interfaces:**
- Consumes: flujo completo Tasks 1–12.
- Produces: evidencia end-to-end, presupuesto de latencia, protocolo de ocho participantes y notas de supersession de specs.

- [ ] **Step 1: Crear Playwright de la transcripción canónica**

```ts
test("reported conversation finishes without zone loop", async ({ page }) => {
  await page.goto("/radar/new")
  await send(page, "Quiero un depto luminoso y cerca del subte")
  await send(page, "En nuñez")
  await send(page, "Confirmo")
  await send(page, "Quiero deptos con cocina grande")
  await send(page, "Quiero un depto cerca de cafes para poder hacer home office")
  await send(page, "Cualquiera, pero cerca de un parque")
  await expect(page.getByText(/¿En qué zona querés buscar?/i)).toHaveCount(0)
  await expect(page.getByText(/alcance abierto/i)).toBeVisible()
})
```

- [ ] **Step 2: Agregar asserts de primer ack y p95**

El test de API registra `ack_ms`, `state_ms`, `done_ms`. La suite local falla si `ack/state >=1000ms`; el gate de ambiente estable calcula p95 y falla en `>=5000ms`.

- [ ] **Step 3: Ejecutar suite dirigida completa**

Run: `pytest tests/unit/application/preferences tests/unit/application/conversation tests/unit/application/radar tests/unit/application/scoring tests/unit/application/agent_evals tests/contract tests/integration/chat tests/integration/preferences tests/integration/scoring tests/integration/radar tests/integration/api/test_chat_copilot_e2e.py -q`

Expected: PASS.

- [ ] **Step 4: Ejecutar frontend e2e/build**

Run: `npm --prefix apps/web test -- --run`

Expected: PASS.

Run: `npm --prefix apps/web run build`

Expected: PASS.

Run: `npm --prefix apps/web run test:e2e -- chat-copilot.spec.ts`

Expected: PASS con cero loops.

- [ ] **Step 5: Documentar protocolo humano exacto**

`chat-copilot-beta-protocol.md` debe exigir ocho participantes representativos, cuatro tareas (crear, refinar, corregir, recuperar cero resultados), ayuda permitida solo después de marcar fracaso, escala SEQ 1–7 y registro de loops/corrección al siguiente turno. Criterios: `>=80%` sin ayuda, mediana `>=6`, cero loops irrecuperables.

- [ ] **Step 6: Marcar specs previas como superseded en conflictos**

Agregar una nota al inicio de 011/014/015 que enlace `specs/016-conversational-search-copilot/spec.md`; no reescribir su historia ni borrar contratos legacy.

- [ ] **Step 7: Ejecutar harness final**

Run: `.\scripts\check.ps1`

Expected: PASS de lint, tipos, contracts y tests configurados.

- [ ] **Step 8: Commit**

```powershell
git add tests/integration/api/test_chat_copilot_e2e.py tests/e2e/chat-copilot.spec.ts docs/product/chat-copilot-beta-protocol.md docs/product/chat-copilot-release-checklist.md specs/011-conversational-ui/spec.md specs/014-soft-preferences-chat/spec.md specs/015-catalog-concept-expansion/spec.md README.md
git commit -m "test: validate conversational copilot release gate"
```

## Coverage Check

| Requisitos | Tareas |
|---|---|
| FR-001–FR-003 radar durable parcial | 2, 4, 6, 10, 11 |
| FR-004–FR-006 multi-acto y contexto | 5, 6, 7 |
| FR-007–FR-010 expresión/binding sin catálogo explosivo | 3, 4, 8, 10 |
| FR-011–FR-019 autoridad, soft/hard y evidencia | 1, 3, 5, 6, 8 |
| FR-020 continuidad sin preguntas repetidas | 5, 7, 12, 13 |
| FR-021–FR-022 cero resultados y soft no excluye | 8, 9, 10 |
| FR-023–FR-024 radares/listings/acción pendiente | 5, 7, 12 |
| FR-025–FR-026 estado inmediato y runs obsoletos | 6, 9, 10, 11 |
| FR-027 inspección/corrección fuera del chat | 3, 10, 11 |
| FR-028–FR-030 trayectorias y caso canónico | 12, 13 |
| SC-008 usabilidad humana | 13 |
| SC-009 performance | 10, 11, 13 |

## Self-Review Result

- Spec coverage: los 30 requisitos y 12 criterios de éxito tienen tarea y verificación; no quedan gaps funcionales.
- Type consistency: `ConversationInterpretation -> PlannedEffect -> ConversationTurnResult`, `CriterionBinding -> CompiledCriterion -> SemanticSignal -> ScoringRunResult` y `ProfileVersion -> RecommendationRun` mantienen nombres estables entre tareas.
- Scope: el plan no modifica ranking con LLM, no crea conceptos por usuario y no rediseña subsistemas fuera de los seams requeridos.
- Migration safety: upgrade tiene backfill explícito; downgrade se niega antes de inventar restricciones.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-14-conversational-search-copilot.md`. Two execution options:

1. **Subagent-Driven (recommended)** — fresh worker per task with review checkpoints.
2. **Inline Execution** — execute tasks in this session in batches with checkpoints.

No implementation should begin until the execution mode is chosen.

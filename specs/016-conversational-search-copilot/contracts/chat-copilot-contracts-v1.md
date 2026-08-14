# Contracts: Copiloto conversacional

## 1. Interpretación v4

El gateway del modelo devuelve estructura y nunca efectos:

```python
ActKind = Literal[
    "resolve_pending",
    "create_radar",
    "set_filter",
    "clear_filter",
    "express_preference",
    "revise_preference",
    "withdraw_preference",
    "record_feedback",
    "query",
]

@dataclass(frozen=True, slots=True)
class ConversationAct:
    act_id: str
    kind: ActKind
    target: Mapping[str, str]
    payload: Mapping[str, object]
    confidence: float

@dataclass(frozen=True, slots=True)
class ConversationInterpretation:
    interpretation_version: str
    acts: tuple[ConversationAct, ...]
    ambiguity: Mapping[str, object] | None
```

Reglas de validación:

- Los IDs del target deben existir en `ConversationContext`; el modelo no puede introducir un radar o listing arbitrario.
- Si hay acción pendiente, el primer acto debe ser `resolve_pending` o la interpretación queda inválida.
- Los actos posteriores a `resolve_pending=approve` conservan el texto y orden original.
- Una ambigüedad solo bloquea actos materialmente dependientes de ella.

Ejemplo:

```json
{
  "interpretation_version": "conversation-interpretation-v4",
  "acts": [
    {
      "act_id": "a1",
      "kind": "resolve_pending",
      "target": {"pending_action_id": "proposal-123"},
      "payload": {"decision": "approve"},
      "confidence": 0.99
    },
    {
      "act_id": "a2",
      "kind": "express_preference",
      "target": {"profile_id": "profile-456"},
      "payload": {"subject_key": "balcon", "text": "también quiero balcón"},
      "confidence": 0.96
    }
  ],
  "ambiguity": null
}
```

## 2. Plan y resultado del turno

```python
EffectStatus = Literal["applied", "pending", "remembered", "rejected"]

@dataclass(frozen=True, slots=True)
class PlannedEffect:
    act_id: str
    effect_kind: str
    target_id: UUID | None
    payload: Mapping[str, object]
    requires_confirmation: bool
    reason_code: str | None

@dataclass(frozen=True, slots=True)
class TurnEffect:
    act_id: str
    status: EffectStatus
    object_type: str
    object_id: UUID | None
    reason_code: str | None

@dataclass(frozen=True, slots=True)
class ConversationTurnResult:
    search_profile_id: UUID | None
    profile_version_id: UUID | None
    effects: tuple[TurnEffect, ...]
    question: str | None
    refresh_run_id: UUID | None
```

Interfaz profunda:

```python
class ConversationTurnService:
    def plan_turn(
        self,
        *,
        context: ConversationContext,
        interpretation: ConversationInterpretation,
    ) -> tuple[PlannedEffect, ...]: ...

    def apply_turn(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        message_id: UUID,
        effects: tuple[PlannedEffect, ...],
        correlation_id: UUID,
    ) -> ConversationTurnResult: ...
```

El servicio aplica efectos reversibles independientes aunque otro efecto quede pendiente. Cada `TurnEffect` identifica el objeto durable creado o modificado.

## 3. Servicio de preferencias

```python
class PreferenceService:
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
        binding_drafts: tuple[BindingDraft, ...],
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
```

`BindingDraft.kind=structured` debe resolver un concepto compartido existente. `semantic` requiere un embedding versionado. `unresolved` y `forbidden` se persisten, pero no producen criterio.

## 4. Política de autoridad v1

| Cambio | Aplicación |
|---|---|
| Preferencia suave explícita nueva | Automática |
| Corrección o retiro suave explícito | Automática y trazable |
| Zona abierta (`zones=[]`) explícita | Automática |
| Cambio inequívoco de un filtro reversible | Automática |
| Conversión a filtro duro | Confirmación |
| Contradicción con impactos materiales distintos | Una aclaración |
| Eliminación irreversible | Confirmación |
| Señal pasiva | Solo hipótesis/sugerencia |

Orden de autoridad: `explicit > deliberate_feedback > passive`. Un nivel menor no reemplaza uno mayor.

## 5. Chat HTTP

### Crear sesión

`POST /api/chat/sessions`

```json
{}
```

`search_profile_id` pasa a ser opcional. La respuesta contiene:

```json
{
  "session_id": "uuid",
  "search_profile_id": null,
  "status": "active"
}
```

El body legacy `{ "search_profile_id": "uuid" }` continúa vigente.

### Enviar turno

`POST /api/chat/sessions/{session_id}/messages`

No cambia el request idempotente. Si existe una interrupción, el router reanuda con el texto completo; no devuelve `409` por no coincidir con un vocabulario de decisión.

Los eventos SSE conservan `ack`, `token`, `proposal`, `done` y `error`, y agregan:

```json
{"type":"state","profile_id":"uuid","profile_version":4,"effects":[{"act_id":"a1","status":"applied"}]}
{"type":"progress","stage":"refreshing_matches","run_id":"uuid"}
```

El primer `ack` o `state` debe emitirse antes de un segundo. `done` puede llegar mientras el refresh sigue en segundo plano.

### Vista de preferencias

`GET /api/search-profiles/{profile_id}/preferences`

Cada elemento expone `expression`, `binding_status`, `confidence`, `limitations`, `mode` y refs. La API no expone el vector crudo.

## 6. Scoring

```python
@dataclass(frozen=True, slots=True)
class SemanticSignal:
    binding_id: UUID
    listing_id: UUID
    score: float
    confidence: float
    query_embedding_ref: UUID
    listing_embedding_ref: UUID

@dataclass(frozen=True, slots=True)
class ScoringRunResult:
    candidates: tuple[ScoredCandidate, ...]
    exclusion_counts: Mapping[str, int]
```

`score_candidates(...)` recibe `semantic_signals: Mapping[UUID, Mapping[UUID, SemanticSignal]]`. Solo activa criterios presentes en perfil/compilación y normaliza por peso activo. La contribución semántica es `min(weight, 0.10) * score * confidence`.

## 7. Trayectorias v2

Cada caso declara:

```json
{
  "id": "reported-zone-loop",
  "family": "context_continuity",
  "initial_state": {"profiles": [], "session": {"profile_id": null}},
  "turns": [
    {
      "user": "Quiero un depto luminoso y cerca del subte",
      "expected_acts": ["create_radar", "express_preference", "express_preference"],
      "expected_effects": ["radar.created", "preference.remembered"],
      "forbidden": ["ask_zone_before_persist"]
    }
  ],
  "final_state": {
    "zones": [],
    "active_subjects": ["luminosidad", "subte", "cocina_grande", "cafes_home_office", "parque"],
    "superseded_zone_values": ["nunez"]
  },
  "invariants": ["no_wrong_target_mutation", "no_repeated_answered_question"]
}
```

Gate:

- invariantes críticos: `100%`;
- trayectorias completas: `>=95%`;
- cada familia: `>=90%`;
- una mutación sobre objeto equivocado bloquea release aunque el promedio pase.

# Data Model: Copiloto conversacional de búsqueda

## Principio

El modelo crece por filas de expresiones y vinculaciones, no por columnas ni clases de criterio por usuario. El catálogo `concepts` continúa reservado a capacidades compartidas y versionadas.

## Entidades nuevas

### PreferenceExpression

Representa exactamente lo que una persona expresó dentro de un radar.

| Campo | Tipo | Regla |
|---|---|---|
| `expression_id` | UUID | PK |
| `profile_id` | UUID | FK `search_profiles`, requerido |
| `source_message_id` | UUID nullable | FK `chat_messages`, `SET NULL` |
| `source_kind` | string | `chat`, `structured`, `feedback`, `suggestion`, `migration` |
| `subject_key` | string | Identidad local y estable para correcciones; no crea un concepto global |
| `raw_text` | text | Formulación original completa o reconstrucción explícita de migración |
| `authority` | string | `explicit`, `deliberate_feedback`, `passive` |
| `status` | string | `active`, `superseded`, `withdrawn` |
| `superseded_by` | UUID nullable | FK a otra expresión |
| `original_text_available` | boolean | `false` solo para backfill sin texto original |
| auditoría | mixin existente | actor, versión, timestamps, correlation id |

Índices:

- `(profile_id, status, created_at)` para reconstruir la verdad vigente.
- `(profile_id, subject_key, status)` para resolver correcciones.
- `source_message_id` para trazabilidad.

Invariantes:

- Solo expresiones del mismo radar pueden formar una cadena de reemplazo.
- `passive` nunca produce un binding duro.
- `withdrawn` y `superseded` no se compilan.

### CriterionBinding

Interpreta una expresión contra capacidades evaluables sin modificarla.

| Campo | Tipo | Regla |
|---|---|---|
| `binding_id` | UUID | PK |
| `expression_id` | UUID | FK `preference_expressions` |
| `kind` | string | `structured`, `semantic`, `unresolved`, `forbidden` |
| `concept_key` | string nullable | Solo para `structured`, debe existir en `concepts` |
| `matcher_type` | string nullable | Matcher validado; `semantic_feature` para semántica |
| `mode` | string | `soft` o `hard`; semántica/unresolved/forbidden solo `soft` |
| `params` | JSONB | Parámetros validados por matcher |
| `confidence` | numeric(4,3) | `[0,1]` |
| `evidence_refs` | JSONB array | Refs internas utilizadas para vincular |
| `limitations` | JSONB array | Códigos explicables, no prosa generativa |
| `interpretation_version` | string | Prompt/model/schema/policy congelados |
| `query_embedding` | vector(1536) nullable | Solo para `semantic` |
| `embedding_version_id` | UUID nullable | FK `extraction_versions` de tipo embedding |
| `status` | string | `active`, `superseded` |
| `superseded_by` | UUID nullable | FK a otro binding |
| auditoría | mixin existente | actor, versión, timestamps, correlation id |

Restricciones:

- `structured`: requiere `concept_key` y `matcher_type`; el modo `hard` requiere confirmación auditable.
- `semantic`: requiere embedding y versión compatible, usa `semantic_feature`, `mode=soft`, peso compilado máximo `0.10`.
- `unresolved` y `forbidden`: no tienen matcher ni embedding, confianza de scoring cero y no compilan.
- Una expresión puede tener varias vinculaciones activas si describe capacidades independientes.

## Entidades modificadas

### SearchProfile

| Cambio | Semántica |
|---|---|
| `zones` acepta `[]` | Alcance abierto dentro de CABA |
| `budget_max` nullable | Sin máximo declarado |
| `min_rooms` nullable | Sin mínimo declarado |
| `name` sigue requerido | El chat asigna un nombre determinista no bloqueante |

No se agrega un estado `draft`. Un perfil parcial puede estar `active`, `paused` o `archived`.

### ChatSession

`search_profile_id` pasa a nullable. Transición permitida:

```text
unbound --bind_profile(profile_id)--> bound
bound --bind_profile(other_id)------> rejected
```

Cambiar de radar activo crea o reutiliza otra sesión; no se reescribe la pertenencia histórica de la sesión.

### PreferenceFact

Agrega `criterion_binding_id UUID nullable`. Los hechos estructurados nuevos siempre lo informan. Los datos históricos se vinculan durante el backfill. Una vinculación semántica no necesita fabricar un `PreferenceFact` ni un `Concept` por usuario.

### CompiledCriterion

Evoluciona de usar `concept_key` como identidad universal a:

| Campo | Uso |
|---|---|
| `criterion_key` | Identidad única dentro de la compilación |
| `concept_key` | Concepto compartido nullable |
| `binding_id` | Lineage a la vinculación nullable para criterios legacy |
| `matcher_type` | Evaluador puro |
| `mode` | `soft` o `hard` |
| `params` | Parámetros congelados |
| `weight` | Peso validado; semántica `<=0.10` |
| `source_ref` | Fact, binding o edición que lo originó |

Para una vinculación semántica, `criterion_key = "binding:<uuid>"` y `concept_key = null`; no se registra un concepto global dinámico.

### RecommendationRun

Agrega estado `superseded` y `diagnostics JSONB NOT NULL DEFAULT '{}'`. Un run pasa a ese estado si su `profile_version_id` ya no es el vigente antes de scoring o publicación. `diagnostics` conserva `exclusion_counts`, `active_criteria` y propuestas deterministas de relajación; no contiene cambios aplicados.

```text
pending -> running -> succeeded
   |          |  \-> failed
   |          \----> superseded
   \---------------> superseded
```

El diagnóstico del run conserva conteos de exclusión por filtro duro y sugerencias deterministas de relajación; no aplica cambios.

## Señal semántica congelada

No se crea una observación global por preferencia personal. Antes del scoring, el adaptador carga:

- embedding y versión del binding;
- embedding y versión del listing;
- compatibilidad dimensional/de modelo.

El motor puro recibe:

```python
@dataclass(frozen=True, slots=True)
class SemanticSignal:
    binding_id: UUID
    listing_id: UUID
    score: float
    confidence: float
    query_embedding_ref: UUID
    listing_embedding_ref: UUID
```

Si falta un vector o las versiones son incompatibles, no hay señal: la evaluación queda `unknown`, contribución cero y una limitación visible.

## Migración `0016_conversational_search_copilot.py`

Orden de upgrade:

1. Crear `preference_expressions` y `criterion_bindings` con índices y checks.
2. Agregar `preference_facts.criterion_binding_id` nullable.
3. Hacer nullable `chat_sessions.search_profile_id`, `search_profiles.budget_max` y `search_profiles.min_rooms`.
4. Reemplazar los checks de presupuesto para aceptar ambos límites nulos y exigir `budget_min < budget_max` cuando ambos existan.
5. Reemplazar `zones_min=1` en el contrato; la columna sigue siendo JSONB no nula.
6. Agregar `superseded` al enum `recommendation_run_state` y `recommendation_runs.diagnostics JSONB NOT NULL DEFAULT '{}'`.
7. Por cada `preference_fact` existente, crear una expresión `source_kind=migration`, `raw_text="<concept_key>=<json value>"`, `original_text_available=false` y un binding estructurado al concepto existente; actualizar `criterion_binding_id`.
8. Verificar que todo hecho histórico quedó vinculado antes de hacer obligatorio el lineage para escrituras nuevas a nivel de aplicación. La columna permanece nullable para importaciones legacy explícitas.

Downgrade:

- Rechazar downgrade si existen perfiles con `budget_max IS NULL`, `min_rooms IS NULL`, sesiones sin radar o runs `superseded`; no inventar valores para satisfacer v1.
- Si no existen esos datos, eliminar bindings/expresiones, restaurar checks/nullable y quitar el valor de enum mediante recreación segura del tipo PostgreSQL.

## Promoción de conceptos compartidos

Un `subject_key` o binding semántico no entra automáticamente al catálogo. La promoción requiere simultáneamente:

1. recurrencia entre múltiples radares/usuarios;
2. definición estable y no prohibida;
3. fuente de evidencia medible;
4. golden de extracción aprobado;
5. mejora demostrada de matching sin degradar familias existentes.

La promoción crea una nueva versión de `Concept`; un job selectivo puede reemplazar bindings semánticos/unresolved por bindings estructurados sin perder las expresiones originales.

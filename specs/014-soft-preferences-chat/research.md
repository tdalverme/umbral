# Research: Criterios suaves activos y chat de preferencias

**Date**: 2026-08-12

## Decisiones de diseño

### D-01: La capa suave se activa reutilizando servicios existentes, no código nuevo

- **Decision**: sembrar conceptos y versiones de extracción con `CriteriaService.seed_registry` / `register_concept_version`; correr la extracción con `process_extraction` (inline en el seed local, job `extraction.run` en worker para producción); la compilación y el scoring ya consumen criteria compilados sin cambios.
- **Rationale**: el pipeline (concepts → observations → facts → compilation → scoring → explanations) está construido y testeado; solo falta ejecutarlo y verificar el flujo completo localmente.
- **Alternatives considered**: construir un pipeline nuevo → descartado (duplicación, viola Minimal Verifiable Change).

### D-02: El chat crea LearningProposals, no un tipo de propuesta nuevo

- **Decision**: la tool `propose_search_preference_update` crea un `LearningProposal` (state pending) con `change` de tipo `preference_fact` sobre un concepto del catálogo, usando la política de aprendizaje vigente (peso/confianza default). Al confirmar por HITL, se ejecuta `FeedbackService.confirm_proposal` (fact + bump de versión + compile + run), que ya orquesta exactamente el flujo requerido.
- **Rationale**: el feedback aprendido y el chat convergen en el mismo objeto durable con confirmación explícita; `confirm_proposal` (feedback/service.py:333) ya hace fact + recompute; cero duplicación de la maquinaria de propuestas.
- **Alternatives considered**: (a) extender `SearchProfileUpdateProposals` con un segundo tipo → duplica lifecycle de propuestas; (b) aplicar directo sin HITL → viola Constitución II y el spec FR-006.

### D-03: Traducción canónica → concepto por código versionado

- **Decision**: módulo puro `application/agent/tools/preferences.py` con el vocabulario publicado (`contracts/criteria/v1/preferences-vocabulary-v1.json`): aliases naturales → (concept_key, polarity, value opcional). El LLM solo clasifica intención y extrae la frase canónica (`preferencia=luminoso`); el código decide concepto/polaridad. Conceptos fuera del vocabulario → error accionable `preference.unknown_concept`.
- **Rationale**: 0 adivinanza del modelo sobre conceptos (Constitución II); el vocabulario es versionable y auditable como los demás contratos.
- **Alternatives considered**: dejar que el LLM emita `concept_key` libre → riesgo de claves inexistentes y contradicciones silenciosas; validar en runtime igual pero sin vocabulario → mensajes de error pobres.

### D-04: HITL reusa el interrupt `proposal_decision`

- **Decision**: el nodo `resolve_decision` del grafo v3 distingue `pending_action.kind` (`profile` vs `preference`) según la tool que creó la propuesta; para preferencia, `approve` ejecuta `confirm_proposal` en vez de `apply_search_profile_update`; `reject`/`edit` usan los mismos portales (`reject`, `derive` no aplica para preference → se rechaza con nota).
- **Rationale**: el frontend ya maneja el interrupt y el ProposalCard; el cambio es un branch determinístico en el grafo.
- **Alternatives considered**: segundo interrupt custom → más superficie nueva sin necesidad.

### D-05: Vocabulario V1 acotado al catálogo actual con semántica clara

- **Decision**: V1 soporta `luminosidad` (±), `balcon` (+), `estado_general` (±), `tipo_cocina` (value `separada`/`integrada`, polarity +). `ambientes`/`piso` se atienden por el perfil duro (ya soportado por el chat); rechazo accionable si se expresan como preferencia.
- **Rationale**: el matcher de cada concepto define cómo se compila un fact a criterio; luminosidad/balcón/estado/tipo_cocina son los casos con mayor valor percibido (el transcript pedía "luminoso" y "cocina").
- **Alternatives considered**: habilitar los 7 conceptos → ambientes/piso como facts compiten con el perfil duro (min_rooms) generando criterios duplicados; requiere decidir precedencia — fuera de alcance.

### D-06: Seed local completo en `scripts/seed-local.py`

- **Decision**: el seed existente se extiende para sembrar conceptos + extraction versions + correr `process_extraction` inline (reglas siempre; cualitativos dependen del modelo configurado y quedan `failed` con código si no hay endpoint) + crear/compilar un perfil demo y disparar un run. Idempotente.
- **Rationale**: un comando deja el stack completo verificable (SC-004/SC-005); reutiliza los repos y servicios ya usados por el seed.
- **Alternatives considered**: comando separado `python -m umbral.ops...` → dos caminos de seed que pueden divergir.

### D-07: La tool entra en el intent `refinamiento`

- **Decision**: `propose_search_preference_update` se agrega a `allowed_tools` de `refinamiento` (es una mutación de criterios con HITL, no una consulta); el intent compiler extrae parámetro canónico `preferencia`.
- **Rationale**: la política deterministic tool→intent (R-02) exige declararlo en el contrato; `consulta` no debe mutar.
- **Alternatives considered**: intent nuevo "preferencia" → más taxonomía para un solo tool; refinamiento ya expresa "cambio de criterios".

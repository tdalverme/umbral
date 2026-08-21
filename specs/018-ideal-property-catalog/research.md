# Research: Catalogo del inmueble ideal con fuerza por usuario

## Decision - Versionado de contratos: v2 nuevo, v1 intacto

- **Decision**: crear `contracts/criteria/v2/concepts-seed-v2.json`, `contracts/criteria/v2/extraction-v2.json` y `contracts/urban/v2/urban-contract-v2.json`, supercediendo v1 por el lifecycle ya existente (`register_concept_version`/`register_extraction_version` invalidan observaciones previas).
- **Rationale**: es la convencion de todos los contratos del repo (scoring v1->v2, search-profiles v1->v2, agent v1->v4); deja trazabilidad del catalogo y evita romper los tests de conformance que pinchan shape exacto de v1 (por ejemplo, `tests/contract/test_concept_registry.py` con el set exacto de 19 conceptos, `tests/contract/test_urban_contract.py` con 12 tag mappings y la lista exacta de senales).
- **Alternatives consideradas**: mutar v1. Rechazada: rompe la inmutabilidad versionada y viola la convencion del repo.
- **Impacto**: `contract_loader.py` debe apuntar/cargar v2 para la composicion activa al tiempo que los tests de v1 siguen validando el documento original.

## Decision - Conceptos de vivienda y su extraccion

- **Decision**: conceptos nuevos: `dormitorios` (numeric_range desde `bedrooms`), `banos` (numeric_range), `mascotas` (categorical true/false), `amoblado` (categorical amoblado/semiamoblado/vacio), `ascensor`, `cochera`, `piscina` (categorical booleanos).
- **Rationale**: dormitorios ya existe en Silver (`silver-schema.json`), es determinista y barato; baños, mascotas y amoblado no tienen campo estructurado y se extraen por regla sobre texto o por modelo con schema versionado segun la fiabilidad del dato. Los amenities (ascensor/cochera/piscina) se derivan de la lista cruda `amenities` por mapeo deterministico como `run_balcon` ya hace.
- **Alternatives**:
  - Baños por regla de texto ("2 baños") — viable, pero con falsos positivos ("baño de visitas"); se prioriza regla con evidencia de fragmento y el modelo para frases ambiguas (FR-003).
  - Amoblado/mascotas por modelo (LLM) por negaciones ("no aceptan mascotas") — se mantiene regla de doble sentido (positivo/negativo) y si el dato es ambiguo cae a `unknown` nunca a inventar.
- **Impacto**: `rules.py` gana runners nuevos registrados en `RULE_RUNNERS`; los tests de set exacto deben actualizarse atomicamente (TDD).

## Decision - Senales urbanas v2

- **Decision**: agregar en `urban-contract-v2.json`: categorias `school` (amenity=kindergarten/school/college, son areas -> `linear_tags_mapping`), `sport` (leisure=pitch/sports_centre como area + amenity=gym como nodo), `culture` (amenity=cinema/library/theatre + tourism=museum), `bike` (highway=cycleway como lineal + amenity=bicycle_parking como nodo), y exponer `health` ya existente como senal `accesso_salud`. Senales: `accesso_escuela`, `accesso_deporte`, `accesso_cultura`, `accesso_bici`, `accesso_salud`.
- **Rationale**: el pipeline es contract-driven (spec 017 US3, FR-004; test `test_new_category_and_signal_parse_without_code_changes`). El matcher `signal_score` ya traspasa score/confidence. El costo de exponer `health` es casi cero porque la categoria y las primitivas existen.
- **Alternatives**: juegos infantiles, mercados/ferias, familia como composite. Rechazadas para V1 por cobertura baja en OSM; `proximidad_parque`/`green_access` ya cubre parte de la capa verde.
- **Impacto**: `urban/contract.py`/`composition.py` leen v2; nuevos `signal_ref`; el batch de urban computa las senales y publica observaciones con las categorias/radios del contrato. La normalizacion por barrio con `min_sample_per_barrio=10` y fallback CABA con penalidad de confianza 0.3 cubre las categorias raras.

## Decision - Degradacion de datos

- **Decision**: aceptar `unknown`/`mismatch` honesto con confianza penalizada para categorias raras; nunca inventar un percentil medio como valor. El matcher `signal_score` con `score=None` queda `unknown`; con score presente pero muestra pequena, la confianza cae (x0.7 en el fallback global).
- **Rationale**: el contrato urbano ya declara esta politica (confidence `weighted_input_coverage` + `missing_penalty`), y la cobertura baja es un resultado honesto, no un error (FR-011/SC-005).
- **Alternatives**: forzar muestra mínima mayor a 10 en CABA — rechazada en V1 porque dejaría muchas senales en fallback permanente.
- **Impacto**: los tests de normalización (017, T023–T025) ya cubren este comportamiento; se replican para las nuevas senales.

## Decision - Hard/soft por usuario

- **Decision**: completar el seam existente: `BindingDraft.mode` (soft/hard) ya existe en `preferences/contracts.py` y `CompiledCriterion.soft_to_hard` ya existe en `criteria/contracts.py` (fijado a False). Se produce el mode desde el copiloto (deteccion de fuerza "si o si"/"plus"), se propaga a la compilacion y se consume en el engine para excluir en `mismatch`.
- **Rationale**: no hay otra forma de satisfacer la US3 sin arquitectura nueva; el seam esta disenado por 016 pero desconectado (nada produce un hard binding y el engine no lee `soft_to_hard`). Es racional y de bajo costo con tests.
- **Alternatives**:
  - No tocar el seam y registrar hard como flag inerte — rechazado: una feature de hard que no excluye miente al usuario.
  - Construir un sistema de filtros hard por usuario desde cero — rechazado: duplicaría el seam y rompería la dependencia hacia adentro.
- **Impacto**: 
  - `compile.py` lee el `mode` del binding (o el `soft_to_hard` del fact) y lo escribe en `CompiledCriterion`.
  - `engine.py`: un criterio compilado con `soft_to_hard=True` y resultado `mismatch` excluye el candidato (igual que `gate=="exclude_on_mismatch"`).
  - Se aplica solo a conceptos estructurados; los semánticos (matcher semantic_feature) se rechazan por `policy`/`compile` (FR-009).
  - El umbral de una señal hard es un `params.threshold` percentil que el evaluador compara contra el score.

## Decision - Golden dataset y medicion

- **Decision**: extender `HardFilterOutcome` para soportar exclusiones por criterio (p.ej. `excluded_criterion:<concept>`), agregar casos golden para un hard de mascotas y un hard de señal con umbral, y extender `conversation-trajectories-v2.json` con una trayectoria por cluster (vivienda y urbano). Medir la tasa de mapeo con el harness de agent-evals.
- **Rationale**: la métrica de la spec (SC-002/SC-003) exige evidencia medible y la regresión de matching exige declarar cualquier cambio de orden (spec 008).
- **Alternatives**: no tocar goldens — rechazado porque la regresión fallaría ante cambios de ranking explicables.
- **Impacto**: `matching/golden.py`/`regression.py` aceptan el nuevo outcome; el golden v2 re-baselinea con release declaration.
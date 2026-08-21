# Quickstart: Catalogo del inmueble ideal con fuerza por usuario

## Escenario 1: extraccion de un concepto de vivienda

1. **Prerequisito**: entorno local con `.venv` y Postgres corriendo (`docs/runbooks/runtime-local.md`).
2. **Seed**: `python -m umbral.ops.seed_local` (o el comando de seed ya usado) registra `concepts-v2` y `extraction-v2`.
3. **Comprobar**: `specify check` no regresa errores (si el CLI esta disponible) o correr los conformance:
   ```text
   pytest tests/contract/test_concept_registry.py
   pytest tests/contract/test_extraction_goldens.py
   ```
4. **Resultado esperado**: el catalogo incluye `dormitorios`, `banos`, `mascotas`, `amoblado`, `ascensor`, `cochera`, `piscina` y los urbanos `acceso_*`, cada uno con validacion de seed en cero errores.

## Escenario 2: senales urbanas v2

1. **Prerequisito**: snapshot urbano importado (`python -m umbral.ops.import_urban --import`).
2. **Reimport/recálculo**: los cambios de contrato fuerzan invalida de observaciones urbanas y un batch completo:
   ```text
   python -m umbral.workers urban.batch
   ```
3. **Comprobar**:
   ```text
   pytest tests/contract/test_urban_contract.py
   pytest tests/integration/urban/test_batch_worker.py
   ```
4. **Resultado esperado**: `school_access`, `sport_access`, `culture_access`, `bike_access`, `health_access` se computan para listings con coordenadas y quedan `unknown`/baja confianza donde no hay muestra; la atribucion OSM permanece visible.

## Escenario 3: hard/soft por usuario

1. **Prerequisito**: un radar con un fact (p.ej. `mascotas` soft).
2. **Elevar a hard**: el copiloto detecta wording de exclusion ("tiene que aceptar mascotas sí o sí"), propone `mode=hard` y pide confirmacion; se registra `HardConfirmationRef`.
3. **Comprobar**:
   ```text
   pytest tests/contract/test_compilation.py
   pytest tests/unit/application/scoring/test_hard_soft.py
   pytest tests/unit/application/radar/test_hard_filters.py
   ```
4. **Resultado esperado**: con confirmacion, el criterio compila con `soft_to_hard=True` y el engine excluye candidatos en `mismatch`; sin confirmacion, `SoftToHardRequiresConfirmation`. Un concepto semantico no puede elevarse.

## Escenario 4: trazabilidad del vacio

1. **Prerequisito**: hard que deja entre el set de candidatos vacio.
2. **Comprobar**: los diagnostics persistidos contienen la exclusion responsable y `/explanations` declara el limite y las relajaciones sugeridas; hay evento auditable.
3. **Resultado esperado**: cero radares vacios silenciosos (SC-008).
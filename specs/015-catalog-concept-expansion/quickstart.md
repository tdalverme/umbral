# Quickstart: Expansión del catálogo de conceptos (Fase 3)

**Date**: 2026-08-12

Guía de validación de la estrategia: agregar un concepto nuevo = contrato + golden, sin tocar el pipeline.

## Evidencia de validación local (2026-08-12/13)

Validado de punta a punta con el stack real (seed → extracción → chat → fact → ranking):

- **Conceptos nuevos**: `moderno` (modelo cualitativo), `proximidad_cafes` y `acceso_transporte` (urbanos con proxy `{radio_m: 500, min: 1}`) — el pipeline no cambió por concepto.
- **Canal urbano**: el seed siembra 6 señales demo (cafe/transport con geometría y `algorithm_version`); la consolidación produce observaciones `source = urban` con conteo y evidencia citando señales.
- **Peso del hecho**: `CompiledCriterion.weight` viaja por la compilación (0.3 del learning); el engine evalúa los conceptos fuera del policy con su propio peso.
- **Ranking con cafés**: con el fact `proximidad_cafes` positive, el run final evalúa `proximidad_cafes` (match 1.0) y el ranking cambia (los listings con cafés suben).
- **Chat**: "quiero algo moderno" / "quiero un depto cerca de cafés" → el vocabulario los traduce (evals golden conversation-025/026).
- **Bugs encontrados en vivo**: (1) `_normalize_zones` devolvía tupla y `validate_change` exige lista (zona "Palermo" fallaba); (2) el repo de compilaciones no serializaba `weight`; (3) `list_for_listing` no exponía la geometría de las señales (consolidación contaba 0). Corregidos con tests.

## Prerrequisitos

- Stack local (compose + API dev_main + worker + gateway) — ver `docs/runbooks/structured-search-radar.md`.
- Postgres con migraciones al head.

## 1. Validar la fundación (brechas cerradas)

```powershell
$env:PYTHONPATH = "src"
.venv\Scripts\python.exe -m pytest tests\unit\application\criteria tests\unit\application\scoring -q
```

- Compilación: un fact de un concepto fuera del policy produce un `CompiledCriterion` con su `weight`; el run con el fact difiere del run sin fact en la dirección de la polarity.
- Consolidación urban: con señales cafe sembradas, la extracción produce observaciones `source = urban` con evidencia citando señales y proxy aplicado.
- Golden: `check-criteria.ps1` corre los casos del golden por concepto y bloquea si el umbral no se cumple.

## 2. Caso cualitativo: "moderno"

1. Agregar `moderno` a `concepts-seed-v1.json` + schema en `extraction-v1.json` + golden + vocabulario ("moderno", "renovado").
2. Seed + extracción: cada listing tiene observación de `moderno` con valor, score del enum, confianza y evidencia.
3. Chat: "quiero algo moderno" → el agente propone la preferencia (vocabulario) → confirmar → fact con peso → recompute → el ranking premia listings modernos; la explicación cita la evidencia.
4. Harness: el golden de moderno corre y pasa.

## 3. Caso urbano: "proximidad_cafes"

1. Sembrar señales demo (o usar urban_signals existentes): cafe con geometría y `algorithm_version`.
2. Agregar `proximidad_cafes` al catálogo con proxy `{radio_m, min}` + golden + vocabulario ("cerca de cafés", "con cafés cerca").
3. Consolidación: observaciones `source = urban` con conteo y evidencia citando señales.
4. Chat: "quiero un depto cerca de cafés" → propuesta → confirmar → ranking premia según el proxy; la explicación cita las señales y declara el proxy ("X cafés en un radio de Y").
5. Cambiar el proxy (radio) → nueva versión del concepto → invalidación selectiva solo de ese concepto.

## 4. Caso urbano réplica: "acceso_transporte"

- Mismo ciclo con señales `transport`; vocabulario "buen transporte", "bien conectado".

## 5. Regla de oro (verificación final)

```powershell
.\scripts\check.ps1
```

El pipeline (engine, graph, tools) no cambia en los pasos 2-4; solo contratos y golden. Verificar con `git diff --stat` que los cambios del paso 2+ están solo en `contracts/`, `scripts/` y tests/goldens.

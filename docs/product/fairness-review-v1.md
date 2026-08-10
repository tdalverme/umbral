# Revision de fairness y lenguaje geografico (UM-H3-035, P1)

**Version**: `fairness-review-v1` | **Fecha**: 2026-08-09 | **Estado**: reviewed

## Alcance

Revision de features, conceptos, copy y lenguaje geografico del matching para
evitar inferencias sensibles, proxies discriminatorios y afirmaciones
normativas sobre zonas. No construye infraestructura nueva; deja documentadas
las features prohibidas como no computables en el concept registry (H3.1).

## Hallazgos

### Concepto prohibido: `barrio_seguro`

- **Riesgo**: inferencia sensible sobre seguridad de una zona; no existe
  politica de datos ni fuente aprobada que la soporte.
- **Decision**: marcado `compute_policy.computable: false` en el concepts seed.
  Cualquier compilacion que lo referencie se rechaza con
  `criteria.concept_not_computable`.
- **Registro**: `contracts/matching/v1/forbidden-features-v1.json`.

### Proxy prohibido: `nivel_socioeconomico_zona`

- **Riesgo**: proxy discriminatorio por nivel socioeconomico estimado de la
  zona; puede sesgar el ranking sin consentimiento ni evidencia.
- **Decision**: documentado como feature prohibida; no se computa en v1.

## Lenguaje geografico

- 0 afirmaciones normativas sobre zonas ("mejor barrio", "zona peligrosa",
  "barrio exclusivo") en templates de explicaciones, comparador o copy.
- El escaner de frases normativas (`application/matching/fairness.py`) corre en
  el harness sobre los templates publicados y falla si aparece una frase
  prohibida.
- El copy de explicaciones v1 es determinista y cita evidencia interna, sin
  juicios cualitativos no soportados (UM-H0-007).

## Reglas de enforcement

1. Toda feature prohibida se documenta en
   `contracts/matching/v1/forbidden-features-v1.json` con justificacion.
2. Todo concepto prohibido es `computable: false` en el concepts seed.
3. El compilador rechaza compilaciones que referencien conceptos no
   computables.
4. El harness verifica el linkage y el escaner de frases en CI.

## Pendientes (no bloquean)

- Revisar con producto el copy de feedback libre y del historial (UM-H0-007)
  antes del release.
- Incorporar nuevas features prohibidas a este documento y al registry al
  ampliar el registry de conceptos.

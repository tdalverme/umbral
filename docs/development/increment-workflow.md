# Flujo de implementacion por incremento

Este documento define el loop operativo para convertir un slice del
[backlog maestro](../product/backlog.md) en software desplegable, demostrable y
verificable.

## Principio

Cada incremento debe entregar un resultado independiente. No se deben agrupar
varios subsistemas en una sola feature si pueden especificarse, implementarse y
validarse por separado.

```text
Elegir slice del backlog
  -> specify
  -> clarify
  -> checklist
  -> plan
  -> tasks
  -> analyze
  -> implement
  -> verify
  -> converge
  -> cerrar y actualizar backlog
```

## 1. Elegir el incremento

Seleccionar un resultado concreto del backlog, con historias relacionadas y
una puerta de salida observable.

Antes de comenzar:

- definir las stories incluidas;
- declarar exclusiones;
- identificar dependencias satisfechas;
- comprobar que el incremento puede demostrarse por si mismo.

## 2. Specify

Ejecutar:

```text
$speckit-specify
```

Resultado: `spec.md`.

La especificacion define:

- problema y resultado buscado;
- actores e historias;
- criterios de aceptacion;
- casos limite relevantes;
- requisitos de datos, auditoria y seguridad;
- alcance y exclusiones.

La spec describe que se construye y por que. No anticipa detalles de
implementacion.

## 3. Clarify

Ejecutar:

```text
$speckit-clarify
```

Resultado: ambiguedades resueltas y respuestas incorporadas en `spec.md`.

Se recomienda realizar siempre una pasada corta. Solo se omite si la
especificacion no contiene decisiones abiertas que puedan cambiar arquitectura,
datos, experiencia o criterios de aceptacion.

## 4. Checklist

Ejecutar:

```text
$speckit-checklist
```

Resultado: checklist de calidad específico del incremento.

Es especialmente importante para:

- ingestion y lineage;
- scoring y explicaciones;
- LangGraph y tools;
- privacidad y seguridad;
- notificaciones;
- operacion de beta.

## 5. Plan

Ejecutar:

```text
$speckit-plan
```

Resultado: `plan.md` y, cuando corresponda, artefactos como `research.md`,
`data-model.md`, contratos y `quickstart.md`.

El plan debe definir:

- modulos, interfaces y seams;
- direccion de dependencias;
- cambios de datos y migraciones;
- contratos HTTP, eventos y tools;
- impacto de auditoria y observabilidad;
- estrategia de errores e idempotencia;
- pruebas, evals y comandos de verificacion.

## 6. Tasks

Ejecutar:

```text
$speckit-tasks
```

Resultado: `tasks.md`.

Las tareas deben:

- agruparse por historia;
- respetar dependencias;
- incluir paths concretos;
- producir entregables verificables;
- permitir trabajo paralelo solo cuando no comparten estado o bloqueos;
- mantener tests y observabilidad dentro del slice que los necesita.

## 7. Analyze

Ejecutar:

```text
$speckit-analyze
```

Resultado: reporte no destructivo de consistencia entre `spec.md`, `plan.md` y
`tasks.md`.

No comenzar a implementar mientras existan:

- requisitos sin tarea;
- tareas que contradicen la arquitectura;
- contratos o nombres inconsistentes;
- historias sin prueba independiente;
- decisiones relevantes sin resolver.

Corregir los artefactos y repetir el analisis hasta cerrar los hallazgos
bloqueantes.

## 8. Implement

Ejecutar:

```text
$speckit-implement
```

Procesar `tasks.md` en orden de dependencias.

Durante la implementacion:

- usar TDD para cambios de comportamiento cuando corresponda;
- hacer cambios quirurgicos;
- verificar cada tarea antes de marcarla;
- mantener migraciones y efectos mutantes idempotentes;
- no ampliar el alcance sin volver a la spec;
- conservar trazabilidad hacia stories y criterios de aceptacion.

## 9. Verify

La implementacion no esta terminada hasta verificar el incremento completo.

Ejecutar, segun corresponda:

- tests unitarios y golden cases;
- tests de integracion;
- contract tests;
- E2E con Playwright;
- evals de agente, extraccion o explicaciones;
- pruebas de seguridad, datos o notificaciones;
- migraciones y rollback;
- `.\scripts\check.ps1`.

Ademas:

- recorrer los criterios de aceptacion de `spec.md`;
- demostrar el flujo de punta a punta;
- confirmar telemetria y eventos de auditoria;
- registrar cualquier limitacion conocida.

## 10. Converge

Ejecutar:

```text
$speckit-converge
```

Converge compara el codigo real contra `spec.md`, `plan.md` y `tasks.md`.

Si encuentra gaps:

```text
converge
  -> tasks.md recibe trabajo faltante
  -> analyze
  -> implement
  -> verify
  -> converge nuevamente
```

El loop se repite hasta que no quede trabajo requerido por la especificacion.

## 11. Cerrar el incremento

Antes de pasar al siguiente:

- marcar las stories terminadas en el backlog;
- actualizar ADRs y documentacion afectada;
- registrar metricas y evidencia de aceptacion;
- confirmar que el harness pasa;
- hacer el commit correspondiente;
- identificar el siguiente incremento desbloqueado.

## Orden inicial recomendado

```text
foundation-runtime
  -> private-beta-identity
  -> controlled-import
  -> structured-search-radar
  -> explainable-matching
  -> feedback-learning
  -> proactive-alerts / conversational-radar
  -> private-beta-readiness
```

`proactive-alerts` y `conversational-radar` se desbloquean despues del matching
explicable. Pueden avanzar en paralelo con equipos separados. Con un solo
equipo, conviene priorizar `proactive-alerts` porque valida antes la metrica
principal de la beta.

## Regla de salida

Un incremento sale del loop solamente cuando:

> esta desplegado o desplegable, puede demostrarse de punta a punta, cumple su
> especificacion y cuenta con evidencia fresca de verificacion.

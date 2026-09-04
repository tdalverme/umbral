# Agente semántico de preferencias

**Fecha:** 2026-09-03  
**Estado:** Diseño aprobado, pendiente de plan de implementación

## Objetivo

Reemplazar el flujo conversacional actual por un único agente que comprenda el
lenguaje libre del usuario, descomponga cada mensaje en intenciones tipadas y
actualice el radar con una política de autoridad clara:

- las preferencias suaves se aplican automáticamente;
- los filtros duros requieren confirmación individual;
- los deseos no computables se preservan sin inventar equivalencias;
- ninguna interpretación depende de regex, coincidencia literal de aliases ni
  listas de frases programadas.

No se mantendrá retrocompatibilidad con versiones anteriores del agente, graph,
prompts o contratos. La implementación debe converger en un solo flujo vigente
y eliminar los caminos reemplazados cuando dejen de tener consumidores reales.

## Decisiones de dominio

### Preferencias suaves

Un deseo evaluable que modifica el orden relativo de oportunidades se aplica
sin confirmación. El LLM interpreta:

- el concepto canónico;
- la polaridad positiva o negativa;
- la intensidad semántica `low`, `medium`, `high` o `essential`;
- la evidencia literal que respalda la interpretación;
- la confianza de la vinculación.

El LLM no produce pesos numéricos. Una política determinística y versionada
traduce la intensidad a un peso. Una nueva declaración explícita sobre el mismo
concepto reemplaza la intensidad vigente y conserva el historial auditable; la
mera repetición no acumula peso.

Los conceptos cualitativos o de entorno siempre son suaves, incluso cuando el
usuario usa expresiones como "sí o sí" o "fundamental". En esos casos pueden
alcanzar intensidad `essential`, pero nunca excluir candidatos.

### Filtros duros

Solo una condición binaria, compilable y auditable puede ser un filtro duro.
Presupuesto, ambientes mínimos, zonas obligatorias y futuros criterios con esas
propiedades requieren confirmación antes de cualquier aplicación.

Cada filtro duro genera una confirmación independiente. Cuando un mensaje
contiene varios, el chat presenta un stepper en el orden en que fueron
expresados. Cada paso se acepta o rechaza por separado.

Si el usuario modifica el filtro que se está confirmando, la nueva intención
supersede la propuesta pendiente con trazabilidad y el paso pide confirmación
sobre el nuevo valor. Ninguna de las dos versiones se aplica silenciosamente.

### Deseos no computables

Si el agente comprende un deseo pero no puede vincularlo con un concepto del
catálogo, persiste el deseo expresado con las palabras del usuario y una
vinculación no resuelta. La respuesta reconoce que fue recordado sin afirmar
que ya afecta el ranking. No responde con una lista cerrada de cosas que sí
puede entender.

## Interpretación semántica

El intérprete recibe el mensaje completo, el contexto conversacional autorizado
y el catálogo publicado de conceptos y filtros. Devuelve una secuencia ordenada
de actos tipados. Un mensaje puede producir varios actos y cada deseo debe tener
su propia evidencia e intensidad.

Ejemplo:

> Me gustan deptos luminosos y silenciosos. Si está bien conectado, mejor.

Produce tres deseos independientes: `luminosidad`, `calma_residencial` y
`acceso_transporte`. Los tres son suaves, se aplican automáticamente y pueden
tener intensidades distintas según el énfasis comprendido.

Los aliases del catálogo pueden aparecer como ejemplos para orientar al modelo,
pero no son un algoritmo de resolución ni una allowlist lingüística. El runtime
no inspecciona el texto del usuario con regex, substrings, normalización léxica
o alias matching para decidir conceptos. La comprensión pertenece al modelo;
el código solo valida la salida estructurada contra contratos publicados.

## Contrato del intérprete

Cada deseo interpretado contiene, como mínimo:

- `raw_text` y evidencia literal;
- `subject_ref` estable dentro del turno;
- cero o una vinculación al concepto canónico;
- `polarity: positive | negative` cuando existe vinculación;
- `intensity: low | medium | high | essential`;
- `confidence` de interpretación.

Cada filtro contiene su clave canónica, valor tipado y evidencia literal. La
salida conserva el orden del mensaje. El modelo no decide si un acto se aplica,
queda pendiente ni altera ranking: esas decisiones pertenecen a políticas
determinísticas.

## Ejecución

El executor procesa el turno en dos fases:

1. persiste y activa todos los deseos suaves en el orden interpretado;
2. crea una propuesta independiente por cada filtro duro y deja activo el
   primer paso pendiente del stepper.

El tipo de matcher, los parámetros válidos y la naturaleza evaluable de un
concepto se leen del catálogo. Se elimina la inferencia por prefijos del nombre
del concepto y cualquier conjunto hardcodeado equivalente.

La política de intensidad es el único componente que convierte los cuatro
niveles semánticos en pesos. Su versión queda registrada con el hecho de
preferencia para que ranking y explicaciones sean reproducibles.

## Estado conversacional y HITL

El estado conserva una cola ordenada de propuestas duras. La respuesta muestra
un solo paso por vez, con el cambio concreto y su impacto. Aceptar o rechazar
resuelve ese paso y avanza al siguiente. Las preferencias suaves del mismo turno
no dependen del resultado del stepper.

Una corrección del paso actual supersede la propuesta previa. Una intención
ajena al paso puede ejecutarse normalmente sin perder la cola pendiente. El
runtime, no el LLM, resuelve respuestas de confirmación contra el paso activo.

## Arquitectura y reemplazo

Habrá una sola composición productiva para interpretación, autorización,
ejecución y respuesta. No se introducirá una nueva versión paralela del graph.
Durante la implementación se identificarán consumidores reales y se eliminarán
los graphs, prompts, schemas, adapters, feature flags y tests de compatibilidad
reemplazados.

Los contratos históricos persistidos solo se migrarán si son necesarios para
que los datos existentes sigan siendo legibles. No se conservará comportamiento
ejecutable antiguo. Si no existen datos productivos que requieran migración, se
prefiere reemplazo directo y eliminación.

## Errores y límites

- Una salida del LLM que inventa refs o conceptos se rechaza estructuralmente y
  no produce efectos.
- Un deseo explícito sin vinculación válida se preserva como no resuelto.
- Un fallo técnico del modelo no debe presentarse como incapacidad semántica;
  el turno queda sin efectos y comunica un error recuperable.
- La confianza baja puede producir una pregunta aclaratoria, pero nunca alias
  matching como fallback.
- Ninguna intensidad puede elevar un concepto cualitativo a hard.

## Verificación

El feedback loop principal será un test del seam conversacional productivo con
un gateway estructurado controlado. Debe verificar los efectos persistidos, no
solo el texto de respuesta.

Casos mínimos:

1. "prefiero deptos con buen acceso al transporte" activa
   `acceso_transporte` sin confirmación;
2. "quiero deptos con cafés cerca" activa `proximidad_cafes` sin confirmación;
3. el ejemplo luminoso/silencioso/conectado crea tres preferencias separadas;
4. paráfrasis no presentes en aliases producen el mismo concepto mediante la
   salida semántica del LLM;
5. intensidades positivas y negativas se traducen mediante la política
   versionada;
6. una nueva declaración reemplaza la intensidad vigente sin acumularla;
7. un deseo no computable se preserva y no genera rechazo engañoso;
8. un mensaje mixto aplica los soft y crea pasos hard individuales en orden;
9. aceptar, rechazar y corregir cada paso producen estados auditables;
10. no existe ningún fallback productivo de regex o alias matching;
11. la composición productiva no conserva caminos ejecutables de versiones
    anteriores.

Los tests unitarios cubrirán interpretación, política de intensidad y cola HITL.
Los tests de integración cubrirán persistencia, supersesión y mensajes mixtos.
Los contratos/evals conversacionales incluirán paráfrasis nuevas para demostrar
generalización semántica sin convertirlas en aliases de producción.

## Fuera de alcance

- permitir que el LLM cree conceptos nuevos;
- asignar pesos numéricos directamente desde el modelo;
- convertir deseos cualitativos en exclusiones;
- conservar APIs o comportamiento antiguos solo por compatibilidad;
- refactorizar ranking, extracción urbana o notificaciones más allá de lo
  necesario para consumir los nuevos hechos de preferencia.

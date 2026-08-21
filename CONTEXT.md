# Umbral

Umbral es un radar personal de vivienda que convierte intenciones cambiantes en busquedas persistentes, oportunidades explicables y aprendizaje controlado por la persona.

## Language

**Radar**:
Busqueda persistente de vivienda de una persona. Puede ser parcial, se versiona al cambiar y es la fuente de verdad operativa de la intencion.
_Avoid_: Chat, formulario, perfil efimero

**Deseo expresado**:
Formulacion completa y contextual de lo que una persona busca o evita en un radar, sea o no evaluable por Umbral.
_Avoid_: Alias, campo libre, concepto del usuario

**Concepto**:
Caracteristica compartida de una vivienda o su entorno que Umbral puede observar y evaluar con una semantica versionada.
_Avoid_: Deseo, preferencia personal, alias

**Conceptos economicos**:
`precio_m2` es el cociente determinista entre `price_value` y `surface_m2`,
conservando la moneda declarada por el listing. `variacion_precio` es el delta
`after - before` de un cambio historico de precio. Ambos quedan en `unknown`
cuando faltan datos y nunca usan conversiones o promedios no versionados.

**Fuerza de feedback**:
`strength` y `confidence` describen la evidencia de una interpretacion de
feedback por concepto. En V1 se persisten y se muestran como evidencia, pero
no alteran el conteo determinista del learning policy ni pueden crear fuerza
hard.

**Vinculacion de criterio**:
Interpretacion versionada que relaciona un deseo expresado con cero, una o varias capacidades evaluables y declara confianza, evidencia y limitaciones.
_Avoid_: Mapeo magico, clasificacion final

**Hecho de preferencia**:
Interpretacion estructurada y vigente de la parte computable de un deseo expresado para un radar.
_Avoid_: Fuente completa del deseo, preferencia global

**Preferencia suave**:
Deseo computable que modifica el orden relativo de oportunidades sin excluirlas.
_Avoid_: Filtro, requisito obligatorio

**Filtro duro**:
Condicion binaria, explicita y auditable que excluye oportunidades del conjunto candidato.
_Avoid_: Gusto, señal implicita, inferencia semantica

**Observacion**:
Valor atribuido a un anuncio para un concepto, acompañado por confianza, evidencia, fuente y version.
_Avoid_: Opinion del agente, dato sin procedencia

**Criterio compilado**:
Condicion validada y ejecutable que traduce filtros y preferencias computables para el matching.
_Avoid_: Prompt, respuesta generativa

**Hipotesis de preferencia**:
Inferencia de baja autoridad nacida de comportamiento pasivo o patrones entre radares; no modifica criterios por si sola.
_Avoid_: Preferencia confirmada, filtro aprendido

**Modo de fuerza (soft/hard)**:
Atributo por radar de un criterio estructurado que decide si reordena (`soft`) o excluye (`hard`) candidatos. Nace de una declaracion explicita confirmada; los conceptos semanticos/cualitativos son siempre soft.
_Avoid_: Filtro global, preferencia aprendida que excluye

**Elevacion a hard**:
Transicion auditable de un criterio de soft a hard para un radar, con confirmacion y supersesion de hipotesis del mismo concepto; el learning nunca genera ni supera hard.
_Avoid_: Cambio silencioso de fuerza, requisito sin trazabilidad

**Trayectoria conversacional**:
Secuencia de estados y turnos que verifica como una conversacion modifica objetos persistentes y que comportamientos estan prohibidos.
_Avoid_: Mensaje golden, ejemplo aislado

**Contrato urbano**:
Documento versionado que declara categorias OSM, primitivas, senales, formulas, normalizacion, atribucion y licencia de los datos de entorno.
_Avoid_: Codigo de scoring, configuracion ad hoc

**Snapshot urbano**:
Captura inmutable de datos OSM (fuente, fecha, hash SHA-256) importada y lista para calcular senales.
_Avoid_: Dato en vivo sin version, archivo localizado

**Categoria urbana**:
Entidad OSM clasificada por el contrato (poi o lineal) que alimenta las primitivas de distancia.
_Avoid_: Punto de interes generico sin semantica

**Señal urbana**:
Valor factual de entorno de un anuncio (densidad, distancia) declarado en el contrato urbano y calculado a partir de un snapshot.
_Avoid_: Opinion, preferencia del usuario

**Primitiva urbana**:
Metrica agregada por categoria y anuncio (conteo en 300m/600m, distancia al mas cercano) sobre la que se construyen las senales.
_Avoid_: Dato crudo sin contrato, campo libre

**Atribucion de OpenStreetMap**:
Reconocimiento requerido por la licencia ODbL al usar datos de OSM; se muestra en una superficie global y via el endpoint de senales.
_Avoid_: Omision de credito, dato sin procedencia

**Catalogo de vivienda**:
Conjunto versionado de caracteristicas de la vivienda evaluables (dormitorios, banos, mascotas, amoblado, ascensor, cochera, piscina) que amplia el catalogo compartido mas alla de balcon/ambientes/piso/cocina.
_Avoid_: Campo por usuario, lista cerrada sin version

**Senales de entorno nuevas**:
Signals urbanas de acceso escolar, deportivo, cultural, en bici y de salud; extienden las de transporte/cafes/parques y se declaran en el contrato v2 sin tocar el ranking.
_Avoid_: Nueva categoria sin contrato, senal sin signal_ref


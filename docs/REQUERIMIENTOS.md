# CENTINELA · Requerimientos de los agentes y la interfaz

Este documento es la fuente de verdad de **qué** construimos. Cada requerimiento tiene un ID
estable; el código lo cita en su docstring y los tests en su nombre o docstring.
`python scripts/trazabilidad.py` verifica que ningún requerimiento quede sin implementación ni
sin prueba y genera [TRAZABILIDAD.md](TRAZABILIDAD.md).

## Contexto

**Alcance**: el correo electrónico que procesa el flujo n8n ya pautado. Todo requerimiento de este
documento se define en relación con ese flujo, sus reportes y sus decisiones.

El flujo n8n de CENTINELA (`workflow/`, autor: Pablo; el JSON importable se genera con
`workflow/build_workflow.py`) analiza correos, y desde esta versión también WhatsApp y SMS: parser,
analizadores en paralelo, puntaje 0-100, decisión con IA local, guardrails, 3 acciones, reportes en
`data/reports/` y bitácora. **Ese flujo se considera terminado.** Los agentes lo complementan sin
reemplazar ninguna de sus partes. Los canales de mensajería no amplían el alcance de los agentes: el
Agente 1 no aplica a WhatsApp/SMS (el flujo lo marca `NO_APLICA`) y el Agente 2 percibe esos reportes
con los mismos requerimientos, sin reglas propias de mensajería (brechas conocidas: la regla
`secuestro_de_cuenta` no está en su réplica del puntaje y el número de origen no es indicador de actor).

| Pieza | Rol | Taxonomía R&N | Momento |
|---|---|---|---|
| Flujo n8n | decide y actúa; mapea MITRE ATT&CK | — | durante |
| Agente 1 · identidad | verifica quién envía realmente el correo | basado en modelos + objetivos | en línea, antes de decidir |
| Agente 2 · aprendizaje | aprende del veredicto humano y supervisa al decisor IA | de aprendizaje | fuera de banda, después |
| Interfaz | cola del investigador, detalle, métricas | — | — |

## Generales (RG)

| ID | Requerimiento | Criterio de aceptación |
|---|---|---|
| RG-01 | No modificar el flujo original. | El flujo integra el nodo del Agente 1 (`integracion_n8n/nodo_agente1.js`) sin cambios salvo la guarda de canal, el JSON importable está sincronizado con `workflow/nodes/` y el nodo falla abierto. |
| RG-02 | Contratos de datos explícitos y validados. | Entradas y salidas de cada agente modeladas con pydantic; una entrada inválida responde 422 sin romper el flujo. |
| RG-03 | Trazabilidad de cada decisión de un agente. | Cada análisis/decisión se registra en JSONL con id, entrada resumida, pasos y resultado. |
| RG-04 | Falla abierta respecto del flujo. | Si un agente no responde, el flujo sigue produciendo el mismo veredicto que sin agentes. |
| RG-05 | Operación local y soberana. | Ningún agente envía datos a servicios externos; sólo consultas DNS. |
| RG-06 | Contratos entre agentes verificados. | Pruebas que ejercitan ambos agentes juntos: los veredictos que escribe el Agente 2 los consume el Agente 1; las trazas y resultados del Agente 1 los consume el Agente 2; ambos coinciden en qué es "el mismo dominio". |

## Agente 1 · Identidad del remitente — basado en modelos y objetivos (RA1)

**Objetivo del agente:** establecer, con evidencia verificada y no declarada, si el remitente es
quien dice ser. **No mapea MITRE ATT&CK** (eso lo hace el flujo).

| ID | Requerimiento | Criterio de aceptación |
|---|---|---|
| RA1-01 | Servicio en línea con el contrato de analizador del flujo. | `POST /analizar` recibe la salida de "Desarmar correo" (+ `.eml` crudo opcional) y responde `{fuente, estado, resultados, hallazgos, n_hallazgos}`, el mismo formato que los otros 10 analizadores. |
| RA1-02 | Modelo de la organización. | Dominios propios por configuración; MX de confianza = configuración ∪ registros MX de los dominios propios. |
| RA1-03 | Salto de origen confiable. | Se toma la IP conectante del `Received` más alto agregado por un MX de confianza, sólo si el tipo de entrada está habilitado como confiable; si no, el origen queda "no verificable". |
| RA1-04 | SPF recalculado, no leído. | Evaluador RFC 7208 (`ip4`, `ip6`, `a`, `mx`, `include`, `redirect`, `all`, límite de 10 consultas DNS) sobre la IP de origen y el dominio del Return-Path (o del From). |
| RA1-05 | DKIM verificado criptográficamente. | Con el `.eml` crudo se verifican las firmas contra la clave pública en DNS; sin crudo, DKIM queda "no verificable" (nunca "pass"). |
| RA1-06 | DMARC recalculado. | Alineación estricta o relajada según `adkim`/`aspf` publicados, con el resultado recalculado de SPF y DKIM y la política `p=`. |
| RA1-07 | Autenticación declarada contradictoria. | Si `Authentication-Results` declara `pass` y el recálculo da `fail`, se emite hallazgo crítico de cabecera forjada. |
| RA1-08 | Modelo de relaciones con defensa ante envenenamiento. | Registro persistente remitente→destinatario; sólo aprende de reportes finales con veredicto legítimo. |
| RA1-09 | Patrón BEC compuesto. | Identidad no verificada o suplantada + se presenta como autoridad interna + instrucción de pago (CBU válido por dígito verificador, CVU o alias) + primer contacto. |
| RA1-10 | Bucle orientado a objetivos, trazado. | Estado de creencias, acciones con precondiciones, selección de acción, test de objetivo y detención; cada paso queda en la traza. |
| RA1-11 | Hallazgos sin duplicar el flujo. | Tipos de hallazgo nuevos (prefijo `a1_`), categorías existentes del motor de puntaje, pesos dentro de sus topes. |
| RA1-12 | Latencia y degradación. | Caché DNS y timeout por consulta; ante error DNS el estado es `parcial` y no se emiten hallazgos sobre lo que no se pudo verificar. |
| RA1-13 | Sin mapeo MITRE. | La salida no contiene técnicas ATT&CK. |

## Agente 2 · Aprendizaje y supervisión — de aprendizaje (RA2)

**Objetivo del agente:** medir y mejorar la política de decisión del flujo usando el veredicto
humano como verdad, y vigilar al decisor IA.

| ID | Requerimiento | Criterio de aceptación |
|---|---|---|
| RA2-01 | Percepción de reportes en solo lectura. | Lee `data/reports/*.json` de forma incremental; nunca escribe en el directorio del flujo. |
| RA2-02 | Veredicto humano auditable. | `MALICIOSO` o `LEGITIMO`, append-only, con analista, fecha y comentario; vale el último y se conserva el historial. |
| RA2-03 | Crítico con estándar de costos. | Compara la acción del flujo (bloquear/escalar/entregar) con la verdad; matriz de costos configurable; métricas de detección y de bloqueo automático. |
| RA2-04 | Elemento de aprendizaje: propuesta de umbrales. | Barre los umbrales de escalar/bloquear sobre el motor de reglas y propone el par de menor costo esperado; exige muestra mínima con ambas clases; **no aplica cambios**. |
| RA2-05 | Supervisión del decisor IA. | Por reporte: acuerdo IA↔reglas, degradación, guardrail activado, IA caída, latencia. Meta-alerta si la tasa reciente de degradación supera la línea base, y alerta crítica si una degradación de la IA resultó maliciosa. |
| RA2-06 | Generador de problemas. | Ordena la cola de revisión por valor informativo: sin veredicto, desacuerdo IA↔reglas, cercanía a umbrales. |
| RA2-07 | ATT&CK agregado, sin re-mapear. | Agrega las técnicas que reportó el flujo y exporta una capa de ATT&CK Navigator. |
| RA2-08 | API para la interfaz. | Endpoints de lectura; la única escritura (veredicto) exige token bearer. |
| RA2-09 | Aporte medible del Agente 1. | Recalcula el puntaje sin los hallazgos `a1_*` con el mismo algoritmo del flujo (paridad verificada) e informa en cuántos reportes el Agente 1 cambió el veredicto de reglas. |
| RA2-10 | Caracterización de actores y campañas. | Agrupa reportes maliciosos o no entregados que comparten IP de origen, Reply-To, dominio (excluidos propios, gratuitos y plataformas masivas), adjunto o destino de pago (sólo como huella del Agente 1); explica cada agrupamiento con sus vínculos; sin atribución nominal; un veredicto humano LEGITIMO excluye al reporte. |
| RA2-11 | Aprendizaje sobre el decisor IA. | Con los veredictos humanos estima qué proporción de las degradaciones de la IA fueron maliciosas (intervalo de Wilson 95 %); ese riesgo aprendido reduce el margen de tolerancia del supervisor y produce una recomendación con evidencia sobre el guardrail del flujo. |
| RA2-12 | Evidencia reproducible de aprendizaje. | Curva de costo en casos reservados (umbrales aprendidos con n veredictos vs vigentes, repetida con particiones al azar): experimento controlado con población sintética declarada y, con suficientes veredictos reales, la misma curva sobre datos reales. |

## Interfaz (RI)

| ID | Requerimiento | Criterio de aceptación |
|---|---|---|
| RI-01 | Cola del investigador priorizada. | Consume RA2-06. |
| RI-02 | Detalle del reporte. | Veredicto final y de reglas, motivos, IA, puntaje por categoría, hallazgos por severidad y fuente, IOCs defanged, ATT&CK y aporte del Agente 1. |
| RI-03 | Registro de veredicto humano. | Formulario con token; muestra el historial. |
| RI-04 | Métricas. | Matriz de confusión, detección, costo, desacuerdos IA↔reglas, latencia. |
| RI-05 | Calibración. | Umbrales actuales vs propuestos y curva de costo. |
| RI-06 | Supervisión de la IA. | Meta-alertas y dimensiones del decisor. |
| RI-07 | ATT&CK. | Técnicas agregadas y descarga de la capa Navigator. |
| RI-08 | Base técnica. | Estructura de `pro-inves-frontend` (registro de módulos, cliente API, polling, tema). |
| RI-09 | Actores y campañas. | Lista de actores con sus vínculos, indicadores (defanged), período, veredictos y técnicas reportadas por el flujo (RA2-10). |
| RI-10 | Evidencia de aprendizaje. | Confiabilidad de las degradaciones de la IA con su recomendación y curva de aprendizaje, indicando si es experimento sintético o datos reales (RA2-11, RA2-12). |

## No funcionales (RNF)

| ID | Requerimiento | Criterio de aceptación |
|---|---|---|
| RNF-01 | Pruebas por requerimiento. | Todo RG/RA1/RA2 tiene implementación referenciada y al menos un test; `scripts/trazabilidad.py` falla si alguno no lo tiene. |
| RNF-02 | Despliegue en contenedores separados. | `docker-compose.yml` levanta n8n, la IA local, el Agente 1, el Agente 2 y la interfaz cada uno en su contenedor, con imagen, salud, límites y permisos propios; los agentes montan los reportes del flujo en solo lectura; n8n no depende de los agentes (RG-04). |
| RNF-03 | Secretos por entorno. | Token, API keys y rutas por variables de entorno; se versiona `.env.example`, nunca `.env`. Ninguna clave aparece en los reportes del flujo ni en lo que recibe el dashboard. |
| RNF-04 | Preparación y levantado reproducibles. | `scripts/preparar_maquina.sh` verifica herramientas, recursos y puertos e indica (o ejecuta) la instalación; `scripts/levantar.sh` deja todo sano de forma idempotente: genera secretos, importa y publica el flujo por comando, espera la salud de cada servicio y comprueba los webhooks. Versiones de imágenes fijas, puertos publicados sólo en 127.0.0.1 por defecto y fin de línea normalizado. |
| RNF-05 | Verificación de extremo a extremo con evidencia. | `scripts/verificar_e2e.sh` envía cada muestra con `scripts/analizar.sh` y comprueba, contra hipótesis declaradas antes de correr (`samples/esperados.json`): respuesta del flujo, patrón identificado, reporte persistido, análisis y traza del Agente 1, percepción del Agente 2 en un ciclo autónomo y llegada al dashboard. Registra entorno (commit, versiones, imágenes, configuración sin secretos, hashes de entradas) y resultados en `evidencias/`. |

## Cambios de criterio

| Fecha | ID | Antes | Ahora | Por qué |
|---|---|---|---|---|
| 2026-09-17 | RG-01 | `resources/centinela.json` intacto; integración como copia generada por `parchear_flujo.py`. | El generador del flujo incluye el nodo del agente sin cambios salvo la guarda de canal. | En v2 Pablo integró el nodo en `workflow/build_workflow.py`; lo que hay que proteger es que el nodo del agente no se altere y que el JSON esté sincronizado. |
| 2026-09-17 | RNF-03 | Token y rutas por entorno. | Además, ninguna clave en reportes ni dashboard. | Se detectó que el flujo copiaba las API keys al reporte (`config`) y se agregó DeepSeek como IA opcional. |
| 2026-09-17 | RNF-02 | Compose de agentes propio, sin tocar el de n8n. | Un solo `docker-compose.yml` con un contenedor por componente. | Se pidió que una máquina nueva levante todo el ecosistema con un comando; los contenedores siguen separados y n8n sigue sin depender de los agentes. |

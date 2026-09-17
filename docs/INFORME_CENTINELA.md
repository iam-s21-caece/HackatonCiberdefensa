# CENTINELA — Informe técnico

**Triage automático de correos de phishing con inteligencia artificial, ejecutado íntegramente dentro de la red de la organización.**

| | |
|---|---|
| Hackathon | Ciberdefensa · Ejército Argentino |
| Eje temático | Inteligencia artificial para la defensa |
| Equipo | Pablo Bernal · Elian |
| Mentores | Lucas · Daniel Briter |
| Fecha | 16 de septiembre de 2026 |
| Estado | Prototipo funcional, verificado de punta a punta |
| Stack | n8n 2.39 · Ollama (Llama 3.2) · Docker |

---

## 1. Resumen ejecutivo

CENTINELA recibe cada correo que entra a una organización, lo desarma pieza por pieza, envía cada pieza a la fuente de inteligencia de amenazas que sabe de esa pieza, consolida la evidencia y le pide a una IA local que decida qué hacer con el mensaje: bloquearlo, entregarlo o derivarlo a un investigador humano.

El objetivo de esta primera versión es **limpiar y filtrar el tráfico malicioso de forma automática**, de modo que los analistas del SOC sólo dediquen tiempo a los casos que realmente requieren criterio humano. Cada decisión queda documentada con la evidencia que la sostiene: qué se encontró, en qué fuente, con qué peso, y por qué se resolvió así.

Tres propiedades lo distinguen de un filtro antispam tradicional:

- **Soberanía de datos.** El correo nunca sale de la red. La IA es un modelo open-source ejecutado en un servidor propio. Hacia internet sólo viajan hashes, dominios e IPs para consultar reputación, nunca el contenido.
- **Señales que las firmas no ven.** Antigüedad del dominio, certificados TLS recién emitidos, imitaciones del dominio institucional, incoherencias entre remitente y dirección de respuesta, temática militar desde dominios externos. Son las marcas del *spear-phishing* dirigido, que por definición no tiene firma previa.
- **La IA propone, las reglas tienen veto.** Un motor de reglas determinístico y auditable puntúa la evidencia; la IA interpreta y explica; un conjunto de *guardrails* impide que un modelo se equivoque en la dirección peligrosa. Lo dudoso va a un humano. Nada se pierde.

## 2. El problema

El phishing sigue siendo el vector de entrada número uno en incidentes contra organismos estatales y fuerzas armadas: una credencial robada abre la puerta a la red interna, al espionaje y al ransomware. Un SOC institucional recibe miles de correos por día. Analizar uno a mano —leer cabeceras, verificar SPF/DKIM/DMARC, buscar cada dominio, calcular el hash de cada adjunto y consultarlo, mirar quién registró el dominio y cuándo— lleva entre diez y veinte minutos a un analista con experiencia. No escala.

Las herramientas comerciales resuelven el problema de volumen, pero con dos costos que pesan especialmente en defensa: el correo se procesa en nubes de terceros, y la detección depende de firmas y listas negras que un atacante dirigido conoce y evita. Un correo que imita a la Jefatura de Sistemas desde un dominio registrado ayer no figura en ninguna lista.

## 3. Qué hace la herramienta

Para cada correo, CENTINELA produce un veredicto, una acción y un reporte.

| Veredicto | Acción |
|---|---|
| `VERDADERO_POSITIVO` | Phishing, malware o fraude confirmado. Se retiene en cuarentena y se alerta al SOC con los indicadores de compromiso y las técnicas MITRE ATT&CK involucradas. |
| `ESCALAR` | Evidencia insuficiente o contradictoria. El correo queda retenido y se abre un caso en la cola del investigador con lo que hay que revisar y por qué se escaló. |
| `FALSO_POSITIVO` | Correo legítimo. Se entrega al destinatario y se deja traza en la bitácora para auditoría y para ajustar los pesos con el tiempo. |

El reporte de cada correo incluye la lista completa de hallazgos ordenados por severidad, el puntaje y su desglose por categoría, el estado de cada fuente consultada, la respuesta íntegra de la IA, el veredicto final con su justificación, y los indicadores de compromiso en formato *defanged* (`hxxp://mercadopago-reembolsos[.]click`) para que puedan pegarse en un ticket o un chat sin riesgo de clic accidental.

## 4. Cómo funciona

El flujo está construido en n8n, una plataforma de automatización de código abierto que se ejecuta en Docker. Tiene 27 nodos organizados en cinco etapas:

1. **Entrada.** Un webhook recibe el correo desde el gateway (JSON o `.eml` completo). Alternativa: lectura directa de una casilla por IMAP.
2. **Desarmado** (< 1 s). Un parser MIME propio descompone el mensaje en cabeceras, autenticación, IPs, dominios, URLs, adjuntos con hash y cuerpo.
3. **Análisis en paralelo** (5–15 s). Diez analizadores reciben las piezas y consultan, cada uno, la fuente que le corresponde. Ninguno bloquea a los demás; si una fuente falla, informa "sin datos" y sigue.
4. **Decisión** (IA: 25–130 s en CPU). Se consolida la evidencia, se calcula el puntaje, se aplican reglas duras, decide la IA local y actúan los guardrails.
5. **Acción** (< 1 s). Se responde al gateway, se guarda el reporte y se ejecuta la acción del veredicto: cuarentena y alerta, cola del investigador, o entrega.

Los diez analizadores: **Cabeceras y SPF/DKIM/DMARC** y **Heurísticas de cuerpo, URLs y adjuntos** (análisis local, sin consultas externas); VirusTotal, AbuseIPDB, crt.sh, RDAP/WHOIS, URLhaus, MalwareBazaar, ThreatFox y DNS (MX/SPF/DMARC). Sin ninguna API key, el sistema funciona con los dos analizadores locales más crt.sh, RDAP y DNS.

## 5. Qué piezas se analizan y contra qué

| Pieza | Qué se revisa | Fuentes |
|---|---|---|
| **Remitente** | From vs. Reply-To vs. Return-Path; nombre visible que contradice la dirección real; cuenta gratuita con nombre institucional; Punycode; suplantación del dominio propio. | Cabeceras, DNS |
| **Autenticación** | Resultado y alineación de SPF, DKIM y DMARC; dominio DKIM distinto del From; políticas publicadas por el dominio (¿tiene MX? ¿publica SPF? ¿DMARC en `reject`?). | Cabeceras, DNS |
| **IPs de la cadena de envío** | Reputación, reportes de abuso, nodos Tor, hosting/VPS en lugar de infraestructura de correo, país y proveedor. | VirusTotal, AbuseIPDB, ThreatFox |
| **Dominios** | Detecciones y categoría; fecha de registro (menos de 30 días: crítico); fecha del primer certificado TLS; subdominios con nombres de captura; dominio inexistente. | VirusTotal, RDAP, crt.sh, ThreatFox, DNS |
| **URLs** | Detecciones y redirecciones; texto del enlace que muestra un dominio y apunta a otro; IP literal; acortadores; TLD abusados; hosting gratuito; `@` en la URL; puertos raros; palabras de captura de credenciales en la ruta. | VirusTotal, URLhaus, heurísticas |
| **Adjuntos** | SHA-256 y MD5 contra muestras conocidas; ejecutables y scripts; doble extensión (`.pdf.exe`); documentos con macros; ISO/IMG/LNK/OneNote; HTML y SVG (*HTML smuggling*); caracteres Unicode invisibles en el nombre; tipo MIME que no coincide con la extensión. | VirusTotal, MalwareBazaar, heurísticas |
| **Cuerpo y HTML** | Lenguaje de urgencia, pedido de credenciales, temática financiera, amenazas legales o disciplinarias, temática militar desde dominios externos; formularios y campos de contraseña embebidos; scripts, iframes, texto oculto, píxeles de rastreo; falsos hilos "RE:" sin conversación previa. | Heurísticas |
| **Lookalikes** | Distancia de edición y normalización de homoglifos (`rn→m`, `0→o`, `1→l`) contra los dominios propios y contra marcas frecuentemente suplantadas en Argentina: ARCA/AFIP, ANSES, PAMI, Mercado Pago, bancos, Correo Argentino, Microsoft, Google. | Heurísticas |

Cada analizador devuelve hallazgos en un formato común: categoría, tipo, valor, severidad (info, baja, media, alta, crítica), peso numérico y explicación en lenguaje de analista. Ejemplo real de una prueba: *"El texto del enlace muestra intranet.ejercito.mil.ar pero apunta a portal-ejercito-argentina.com.ar"* (alta, 20 puntos).

## 6. La decisión: reglas, IA y guardrails

### Motor de reglas

Suma los pesos de los hallazgos con **rendimientos decrecientes por categoría** (el primer hallazgo de una categoría vale el 100 %, el segundo el 70 %, el tercero el 50 %, los siguientes el 30 %) y un tope por categoría. Así, diez palabras de urgencia no pesan lo mismo que un hash de malware conocido. Las señales a favor restan: un remitente del dominio propio con SPF y DKIM válidos y sin enlaces ni adjuntos descuenta 25 puntos. El resultado es un puntaje de 0 a 100:

| 0 – 29 | 30 – 64 | 65 – 100 |
|---|---|---|
| FALSO_POSITIVO | ESCALAR | VERDADERO_POSITIVO |

Además, ciertas evidencias son **reglas duras** que deciden por sí solas, sin importar el puntaje: adjunto identificado como malware conocido, indicador confirmado por una fuente de inteligencia, ejecutable adjunto, campo de contraseña embebido en el HTML, dominio remitente inexistente, o imitación del dominio propio combinada con fallo de autenticación.

El motor es determinístico: el mismo correo produce siempre el mismo puntaje y el mismo desglose. Eso lo hace auditable, un requisito para cualquier sistema que tome decisiones sobre comunicaciones de una fuerza armada.

### IA local

La evidencia consolidada se envía a un modelo de lenguaje ejecutado en Ollama, dentro del mismo Docker (`llama3.2:3b` por defecto; intercambiable por Qwen 2.5 o Llama 3.1 8B con GPU). El *system prompt* lo posiciona como analista senior de un SOC de ciberdefensa, le prohíbe inventar datos, le indica bajar la confianza cuando faltan fuentes y le exige responder únicamente en JSON con un esquema fijo: veredicto, confianza (0–1), tipo de amenaza, resumen para el analista, indicadores clave, acciones recomendadas, técnicas MITRE ATT&CK y un mensaje en lenguaje simple para el destinatario.

El valor de la IA no es reemplazar al motor de reglas sino **interpretar y explicar**: convertir treinta hallazgos en dos oraciones que un analista lee en cinco segundos, y en una frase que un suboficial sin formación técnica entiende ("No hagas clic en el enlace y no proporciones tus credenciales").

### Guardrails

La IA propone; las reglas tienen veto. Antes de emitir el veredicto final se aplican estas verificaciones, en orden:

| Condición | Resultado |
|---|---|
| Hay una regla dura activada | → VERDADERO_POSITIVO |
| La IA dice "limpio" pero el puntaje es 55 o más | → ESCALAR |
| La IA dice "malicioso" con puntaje menor a 20 y sin reglas duras | → ESCALAR |
| Confianza de la IA menor a 0,55 | → ESCALAR |
| Dos o menos fuentes disponibles y el correo no es claramente limpio | → ESCALAR |
| La IA no responde o devuelve algo inválido | → decide el motor de reglas |

Dos consecuencias prácticas: la IA nunca puede "perdonar" un malware conocido, y el sistema nunca bloquea un correo sin evidencia concreta. Y si el modelo se cae, el flujo sigue funcionando con el motor de reglas. Los identificadores MITRE que devuelve el modelo se validan por formato; un correo legítimo no lleva técnica de ataque.

## 7. Resultados de las pruebas

Se probó el flujo completo (webhook → n8n → Ollama → archivos) con cuatro correos simulados, construidos a partir de patrones reales de campañas contra organismos argentinos. Sin API keys cargadas: sólo análisis local, crt.sh, RDAP y DNS.

| Correo de prueba | Veredicto | Puntaje | Hallazgos | IA | Tiempo |
|---|---|---|---|---|---|
| "Mesa de Ayuda – Ejército Argentino" desde `ejercito-mil.ar`, Reply-To en Gmail, enlace con texto engañoso, SPF y DMARC fail | VERDADERO_POSITIVO | 100 | 30 | Coincide · conf. 0,8 · T1566.002 | 141 s |
| Falso Mercado Pago en `.eml` crudo: reembolso de $45.900, dominio `.online`, link a `.click`, adjunto `Comprobante.pdf.exe` | VERDADERO_POSITIVO | 100 | 24 | Coincide · conf. 0,8 | 142 s |
| "Tesorería – Liquidación de haberes" con adjunto cuyo hash es el archivo de prueba EICAR | VERDADERO_POSITIVO | 100 | 14 | Motor de reglas (prueba local) | 4 s |
| Boletín semanal desde `comunicaciones@ejercito.mil.ar`, SPF/DKIM/DMARC pass, sin enlaces ni adjuntos | FALSO_POSITIVO | 0 | 5 (info) | Coincide · conf. 0,8 | 23 s |

En los tres casos maliciosos el motor de reglas y la IA coincidieron. En el correo en formato `.eml` se verificó el parser completo: decodificación de asunto RFC 2047, cuerpo *quoted-printable*, adjunto base64 con hash SHA-256 calculado, y detección de la doble extensión. El correo legítimo obtuvo puntaje cero gracias a las señales a favor y fue entregado. Los tiempos corresponden a una PC sin GPU; el 90 % es inferencia del modelo. Con GPU baja a pocos segundos por correo.

Los reportes de estas corridas están en `data/reports/` y las decisiones en `data/bitacora/VERDADERO_POSITIVO.jsonl`. Las ejecuciones también pueden verse en la pestaña *Executions* de n8n, con los datos que pasaron por cada nodo.

## 8. Por qué es relevante para la defensa

- **Reduce la carga del SOC donde más duele.** El triage inicial de correos sospechosos es repetitivo y consume horas de analistas escasos. Automatizar lo claro y documentar lo dudoso deja a las personas para lo que sólo las personas hacen.
- **Detecta el ataque dirigido, no sólo el masivo.** Las señales de infraestructura (dominio de tres días, primer certificado ayer, sin MX) y de identidad (Reply-To externo, nombre institucional desde freemail) aparecen aunque el atacante haya escrito un correo impecable y use un dominio que nadie vio antes.
- **No exporta información.** Un correo interno puede contener información sensible. CENTINELA no lo envía a ningún servicio externo; sólo consulta reputación de indicadores técnicos, y puede operar totalmente aislado si se deshabilitan esas consultas.
- **Es explicable y auditable.** Cada veredicto tiene una cadena de evidencia. Un oficial puede leer el reporte y entender por qué se bloqueó un correo, y un investigador puede revertir la decisión con fundamento.
- **Es adaptable a la organización.** Los dominios propios, las marcas a proteger, los pesos y los umbrales son parámetros. Cada unidad puede tener su perfil.

## 9. Datos utilizados

- **Correos:** simulados, escritos para las pruebas. Reproducen suplantación institucional, falsos avisos de Mercado Pago, liquidación de haberes con adjunto y un boletín interno legítimo. Los dominios de los remitentes maliciosos fueron inventados y no existen.
- **Inteligencia de amenazas:** fuentes públicas. VirusTotal, AbuseIPDB y abuse.ch (URLhaus, MalwareBazaar, ThreatFox) con claves gratuitas; Certificate Transparency (crt.sh), RDAP (IANA y NIC Argentina) y DNS público sin clave. El único hash de malware de las pruebas es el del archivo EICAR, el estándar inofensivo para probar antivirus.
- **IA:** Llama 3.2 3B (Meta, licencia abierta), ejecutado localmente con Ollama. No se envía nada a proveedores de IA.

## 10. Requisitos y puesta en marcha

Docker Desktop y, opcionalmente, una GPU NVIDIA. Todo el despliegue es un archivo `docker-compose.yml`:

```bash
cp .env.example .env            # API keys (opcionales)
docker compose up -d            # n8n + Ollama
docker exec centinela-ollama ollama pull llama3.2:3b
docker exec centinela-n8n n8n import:workflow --input=/workflow/centinela_workflow.json
docker exec centinela-n8n n8n update:workflow --id=CentinelaPhish01 --active=true
docker restart centinela-n8n

.\scripts\analizar.ps1 .\samples\phishing_reembolso.eml   # probar
```

El repositorio contiene el flujo exportado, el código de cada nodo como archivo `.js` independiente (legible y versionable), un generador del flujo, un *harness* que ejecuta la cadena sin n8n para depuración, las muestras y los scripts de prueba.

## 11. Limitaciones actuales

- La acción "cuarentena" del prototipo registra y alerta; el movimiento físico del correo requiere el conector al gateway de cada organización (Exchange/Graph, Postfix milter), que está previsto pero no implementado.
- Sin GPU, la inferencia del modelo tarda entre uno y dos minutos por correo. Es aceptable para una cola de triage, no para línea de entrega en tiempo real; con GPU el problema desaparece.
- Las cuotas gratuitas de VirusTotal (4 consultas por minuto) obligan a limitar la cantidad de artefactos consultados por correo. Con clave institucional se elimina el límite.
- Los pesos de las heurísticas fueron calibrados con criterio de analista y con las pruebas realizadas, no con un conjunto de datos etiquetado grande. La bitácora está diseñada para permitir esa calibración con datos reales.
- No analiza imágenes ni códigos QR (*quishing*), ni detona adjuntos en sandbox.

## 12. Próximos pasos

1. Conector a Microsoft Graph / Exchange y a Postfix para cuarentena real y lectura automática de casillas.
2. Panel web de la cola del investigador, con botones "confirmar" / "era legítimo" que retroalimentan los pesos.
3. Detonación de adjuntos en sandbox local (CAPE) como fuente adicional.
4. Modelo multimodal local para analizar imágenes y QR embebidos.
5. Ajuste fino del modelo con las decisiones validadas por los analistas de la propia fuerza.

## 13. Glosario

- **SPF / DKIM / DMARC** — Los tres mecanismos con que un dominio declara qué servidores pueden enviar en su nombre (SPF), firma criptográficamente sus mensajes (DKIM) y establece qué hacer cuando algo falla (DMARC). Un correo que los falla está usando un dominio que no lo autoriza.
- **IOC** — Indicador de compromiso: una IP, dominio, URL o hash asociado a actividad maliciosa.
- **Defanged** — Indicador escrito de forma que no sea clickeable (`hxxp://`, `[.]`), para compartirlo con seguridad.
- **MITRE ATT&CK** — Catálogo estándar de técnicas de ataque. `T1566.001` es phishing con adjunto; `T1566.002`, phishing con enlace.
- **Lookalike / homoglifo** — Dominio que imita a otro cambiando o intercalando caracteres parecidos (`ejercito-mil.ar`, `rnil.ar`).
- **Human-in-the-loop** — Diseño en el que el sistema automatiza lo claro y deriva lo dudoso a una persona, en lugar de decidir todo solo.

---

*CENTINELA · Hackathon de Ciberdefensa del Ejército Argentino · Septiembre de 2026.*

# CENTINELA — explicación para el equipo

Chicos, esto es lo que tenemos armado, cómo funciona paso a paso, qué falta y qué tenemos que decidir entre todos antes del jueves 20:00.

## En una frase

Es un sistema que agarra cada mail que entra, lo desarma en pedazos (remitente, links, adjuntos, IPs, cabeceras), investiga cada pedazo contra fuentes de inteligencia de amenazas, junta todo, y una IA que corre **en nuestra propia máquina** decide: ¿es phishing (bloquear), es legítimo (entregar) o no está claro (que lo mire una persona)?

Está hecho en **n8n** (una herramienta de flujos visuales, tipo "cajitas conectadas") corriendo en Docker, con **Ollama** para la IA. Todo local, nada en la nube.

## Cómo funciona, paso a paso

Si abren n8n (`http://localhost:5678`) ven el flujo con estas cajitas, de izquierda a derecha:

**1. Webhook: recibir correo.** La puerta de entrada. Le mandás un mail por HTTP (como JSON o como archivo `.eml` completo) y arranca. Abajo hay un nodo **IMAP** apagado: si le cargamos una casilla, lee solo los mails no leídos.

**2. Configuración.** Junta las API keys, la URL de Ollama y la lista de "dominios propios" (`ejercito.mil.ar`, `mil.ar`, `argentina.gob.ar`). Todo eso sale de un archivo `.env`.

**3. Desarmar correo.** El corazón. Es un parser que escribimos nosotros: entiende el formato MIME de los mails (multipart, base64, adjuntos) y separa:
- quién lo manda (From), a quién responde (Reply-To), de dónde rebota (Return-Path), cada uno con su dominio
- si pasó SPF / DKIM / DMARC (los tres chequeos que dicen "este servidor tiene permiso de mandar en nombre de este dominio")
- las IPs por las que pasó el mail
- todos los links, con el texto que ve el usuario y adónde apuntan de verdad
- los adjuntos: nombre, extensión, tamaño y hash SHA-256
- el texto del cuerpo

**4. Diez analizadores en paralelo.** Todos reciben lo mismo y cada uno mira su parte:

| Nodo | Qué hace |
|---|---|
| Cabeceras y autenticación | ¿SPF/DKIM/DMARC ok? ¿From, Reply-To y Return-Path son del mismo dominio? ¿Dice "Ejército" pero manda desde Gmail? |
| Heurísticas | Palabras de urgencia / pedido de contraseña / plata / amenazas; links engañosos; dominios parecidos a los nuestros (`ejercito-mil.ar`); adjuntos peligrosos (`.exe`, `.pdf.exe`, macros, ISO); formularios en el HTML |
| VirusTotal | Reputación de IPs, dominios, URLs y hashes (~70 antivirus) — **necesita key** |
| AbuseIPDB | ¿Las IPs tienen denuncias de abuso? ¿Son Tor? — **necesita key** |
| crt.sh | ¿El dominio tiene certificados TLS con historial o el primero es de ayer? — gratis |
| RDAP / WHOIS | ¿Cuándo se registró el dominio? Menos de 30 días = muy sospechoso — gratis |
| URLhaus | ¿La URL ya repartió malware? — **necesita key** (gratis) |
| MalwareBazaar | ¿El hash del adjunto es malware conocido? — **necesita key** (gratis) |
| ThreatFox | ¿El dominio/IP es un IOC de botnet/C2? — **necesita key** (gratis) |
| DNS | ¿El dominio existe? ¿Puede recibir mails (MX)? ¿Publica SPF/DMARC? — gratis |

Cada uno devuelve una lista de **hallazgos** con severidad (info / baja / media / alta / crítica) y un **peso** en puntos. Si una fuente no responde o no tiene key, dice "sin datos" y el flujo sigue igual.

**5. Unir inteligencia.** Espera a los 10 y junta todo.

**6. Consolidar evidencia y puntuar.** Suma los pesos y saca un **score de 0 a 100** (con truco: el segundo hallazgo de la misma categoría vale 70 %, el tercero 50 %… así 10 palabras de "urgente" no pesan como un hash de malware). También marca **reglas duras**: cosas que solas deciden (malware conocido, ejecutable adjunto, dominio remitente que no existe, campo de contraseña dentro del mail).

- 0–29 → falso positivo · 30–64 → escalar · 65–100 → verdadero positivo

**7. IA: decisión (Ollama local).** Le manda toda la evidencia a `llama3.2:3b` corriendo en Docker y le pide que responda en JSON: veredicto, confianza, tipo de amenaza, resumen para el analista, técnicas MITRE ATT&CK, y un mensaje simple para el usuario ("no hagas clic en el enlace"). Tarda ~2 min en CPU, segundos con GPU.

**8. Interpretar veredicto IA + guardrails.** La IA propone, las reglas tienen veto:
- hay regla dura → verdadero positivo sí o sí (la IA no puede "perdonar" un malware)
- la IA dice "limpio" pero el score es ≥ 55 → escalar
- la IA dice "malicioso" con score < 20 → escalar (no bloqueamos sin evidencia)
- confianza baja o la IA se cayó → escalar / decide el motor de reglas

**9. Responder al webhook + Guardar reporte.** Devuelve el resultado a quien mandó el mail y guarda el reporte completo en `data/reports/<id>.json`.

**10. Enrutar por veredicto.** Un switch con 3 salidas:
- **VERDADERO POSITIVO** → cuarentena + alerta al SOC (arma la alerta con los IOCs "defanged", o sea `hxxp://malo[.]com` para que nadie haga clic; si hay un webhook de Slack/Discord configurado, la manda)
- **ESCALAR** → cola del investigador (crea un caso con "qué revisar y por qué se escaló")
- **FALSO POSITIVO** → entregar y registrar

**11. Bitácora.** Cada decisión queda como una línea en `data/bitacora/VERDADERO_POSITIVO.jsonl` (o ESCALAR / FALSO_POSITIVO). Sirve para auditoría y para ajustar los pesos después.

## Ejemplo real (lo probé hoy)

Mail falso de Mercado Pago ("tenés un reembolso de $45.900"), desde `notificaciones-mercadopago.online`, Reply-To en Yandex, link que dice `mercadopago.com.ar` pero va a `mercadopago-reembolsos.click`, y un adjunto `Comprobante_Reembolso.pdf.exe`.

Resultado: **VERDADERO POSITIVO, score 100, 24 hallazgos**. Reglas duras: ejecutable adjunto + dominio remitente inexistente. La IA dijo lo mismo con confianza 0,8 y escribió: *"No haga clic en el enlace ni proporcione información personal"*.

Y el mail legítimo (boletín interno desde `comunicaciones@ejercito.mil.ar` con SPF/DKIM/DMARC ok) dio **FALSO POSITIVO, score 0**. O sea, no bloquea por bloquear.

## Qué está hecho

- Flujo completo (27 nodos) funcionando en Docker, probado de punta a punta con 4 mails
- Parser MIME propio (lee `.eml` reales)
- 10 analizadores, motor de reglas, IA local, guardrails, 3 acciones, reportes y bitácora
- README, informe técnico, muestras de prueba y scripts para probar
- Todo el código de cada nodo en archivos `.js` separados, así se puede leer y modificar

## Qué falta terminar

1. **API keys.** Hay que registrarse (gratis) en VirusTotal, AbuseIPDB y abuse.ch y pegar las keys en `.env`. Sin eso funcionan 5 fuentes; con eso, las 10. Es 20 minutos de trabajo.
2. **Cuarentena "de verdad".** Hoy registra y alerta pero no mueve el mail a ningún lado. Para eso hace falta conectarse al servidor de correo (Exchange/Postfix). Podemos dejarlo como roadmap o simularlo moviendo el mail a una carpeta por IMAP.
3. **Alerta al SOC.** Probar el webhook con un Discord o Slack nuestro, queda lindo para la demo.
4. **Más mails de prueba.** Tenemos 4; sumar 3 o 4 más: falso jefe pidiendo transferencia (BEC), falso Microsoft 365, uno con QR, uno "dudoso" para que salga ESCALAR y se vea el camino del investigador.
5. **Calibrar los pesos** con esos mails nuevos (que lo dudoso escale y lo claro no).
6. **La demo.** Guion, quién muestra qué, y resolver el tema de que la IA tarda 2 minutos en CPU.
7. **Entrega.** README final, subir el repo a hacki antes del jueves 20:00.

## Para discutir entre nosotros

1. **¿Demo en vivo o grabada?** En vivo impacta más pero la IA tarda ~2 min por mail. Mi propuesta: en vivo con un mail, y mientras la IA piensa contamos el flujo; video de respaldo por si algo falla. ¿Alguien tiene PC con GPU NVIDIA? Ahí baja a segundos.
2. **¿Modelo más grande?** `llama3.2:3b` funciona bien pero es chico. Con GPU podemos usar `llama3.1:8b` o `qwen2.5:7b`, que explican mejor. ¿Vale la pena?
3. **Umbrales.** 65 para bloquear y 30 para escalar. ¿Nos parece muy agresivo? ¿Muy permisivo? Para una fuerza armada yo iría a bloquear menos y escalar más (falso positivo = un mail demorado; falso negativo = un incidente).
4. **¿Qué hacemos con lo escalado?** Hoy es un archivo `.jsonl`. Opciones: dejarlo así, o armar un mini panel web donde el investigador ve la cola y marca "era phishing / era legítimo". Suma mucho para la demo pero son horas.
5. **Cuarentena:** ¿roadmap o simulada por IMAP? (ver punto 2 de arriba)
6. **Reparto de tareas:** keys / mails de prueba / presentación / README y entrega / panel (si va). Propongo repartir hoy y cerrar todo el jueves al mediodía para tener margen.
7. **Nombre del equipo y logo**, si queremos ponerle algo al README y a las diapositivas.

## Cómo probarlo en tu máquina

Necesitás Docker Desktop. Clonás el repo y:

```bash
cp .env.example .env
docker compose up -d
docker exec centinela-ollama ollama pull llama3.2:3b
docker exec centinela-n8n n8n import:workflow --input=/workflow/centinela_workflow.json
docker exec centinela-n8n n8n update:workflow --id=CentinelaPhish01 --active=true
docker restart centinela-n8n
```

Y para mandar un mail de prueba:

```bash
.\scripts\analizar.ps1 .\samples\phishing_reembolso.eml
```

Te imprime el veredicto con todos los hallazgos. Los otros mails de prueba están en `samples/`. Para verlo animado en n8n: botón "Execute workflow" y mandás el mail a `http://localhost:5678/webhook-test/centinela/analizar`.

Cualquier duda me escriben y lo vemos juntos.

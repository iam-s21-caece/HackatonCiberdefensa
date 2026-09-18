# CENTINELA · despliegue y verificación reproducibles

Cómo llevar una máquina nueva a tener **todo el ecosistema corriendo**: flujo n8n, IA local, Agente 1,
Agente 2 y dashboard. También cómo **comprobar, con evidencia, que la cadena completa funciona**.
Requerimientos: RNF-02, RNF-03, RNF-04 y RNF-05 ([REQUERIMIENTOS.md](REQUERIMIENTOS.md)).

La corrida se trata como un experimento. Las versiones están fijas, las hipótesis se declaran antes de
correr y cada verificación deja registrados el entorno exacto y los resultados, para que otra persona la
repita y compare.

---

## 1. Qué se levanta

Un contenedor por componente, todos en la red del proyecto Compose (`docker-compose.yml`):

```
analizar.sh ──POST /webhook/centinela/{analizar|whatsapp|sms}──> n8n ──POST /analizar──> agente-identidad (Agente 1)
                                                                  │ └──/api/chat──> ollama (IA local)
                                                                  └── ./data/reports/<id>.json
                                                                          │ solo lectura
                                              agente-aprendizaje (Agente 2) <┘   agente-identidad (aprende relaciones)
navegador ──> interfaz (nginx) ──/api──> agente-aprendizaje     ──/agente1/salud──> agente-identidad
```

| Servicio | Imagen | Puerto (127.0.0.1) | Datos | Salud | Límites y permisos |
|---|---|---|---|---|---|
| `n8n-importar` | `docker.n8n.io/n8nio/n8n:2.39.7` | — | `n8n_data`, `./workflow` (ro) | termina con código 0 | corre una vez, antes de n8n |
| `n8n` | `docker.n8n.io/n8nio/n8n:2.39.7` | `5678` | `n8n_data`, `./data` | `GET /healthz/readiness` | 2 GB · no-new-privileges |
| `ollama` | `ollama/ollama:0.34.1` | `11434` | `ollama_models` | `ollama list` | no-new-privileges |
| `ollama-modelo` | `ollama/ollama:0.34.1` | — | (usa `ollama`) | termina con código 0 | baja `OLLAMA_MODEL` una vez |
| `agente-identidad` | `centinela/agente-identidad:1.0.0` (build) | `8101` | `agente1-datos`; reportes y `agente2-datos` en ro | `GET /salud` | 512 MB · fs de solo lectura · sin capabilities |
| `agente-aprendizaje` | `centinela/agente-aprendizaje:1.0.0` (build) | `8102` | `agente2-datos`; reportes y `agente1-datos` en ro | `GET /api/salud` | 512 MB · fs de solo lectura · sin capabilities |
| `interfaz` | `centinela/interfaz:0.1.0` (build) | `8088` | — | `GET /healthz` | 128 MB · no-new-privileges |

Decisiones:

- **El flujo versionado es la fuente de verdad.** `n8n-importar` importa `workflow/centinela_workflow.json`
  y lo publica en cada `up`, antes de que arranque n8n. Los cambios hechos en la UI de n8n se pierden al
  volver a levantar: hay que editar `workflow/nodes/*.js`, correr `python workflow/build_workflow.py` y
  levantar de nuevo.
- **n8n no depende de los agentes ni de la IA** (RG-04). Si un agente no responde, el flujo decide igual y
  el reporte lo registra.
- **Puertos sólo en 127.0.0.1.** Los webhooks no tienen autenticación y el perfil de demo confía en lo que
  se sube (ver § 5). `levantar.sh` se niega a publicar en otra interfaz con esa confianza activa.
- **Versiones fijas.** Hoy, `n8n:latest` es 2.39.7 y `ollama:latest` es 0.34.1 (mismo digest): quedan
  congeladas. Son variables controladas del experimento (`N8N_VERSION` y `OLLAMA_VERSION`).

## 2. Requisitos

| Herramienta | Versión mínima | Para qué | Ubuntu / Debian | macOS | Windows 10/11 |
|---|---|---|---|---|---|
| Docker Engine + Compose v2 | Compose 2.24 | todos los componentes | `curl -fsSL https://get.docker.com \| sudo sh` y `sudo usermod -aG docker "$USER"` ([docs](https://docs.docker.com/engine/install/)) | [Docker Desktop](https://docs.docker.com/desktop/setup/install/mac-install/) o `brew install --cask docker` | [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) (WSL 2) o `winget install -e --id Docker.DockerDesktop` |
| Git (en Windows incluye Git Bash) | 2.x | clonar; bash para los scripts | `sudo apt-get install -y git` | `brew install git` | `winget install -e --id Git.Git` |
| curl | 7.76 | los scripts hablan HTTP | `sudo apt-get install -y curl` | incluido | incluido en Git Bash |
| jq | 1.6 | los scripts leen JSON | `sudo apt-get install -y jq` | `brew install jq` | `winget install -e --id jqlang.jq` |

Recursos para contenedores (en Docker Desktop: *Settings → Resources*):

| | Con IA local | Sin IA (`--sin-ia`) |
|---|---|---|
| Memoria | 6 GB o más | 3 GB |
| Disco | 15 GB (imágenes ≈ 9 GB + modelo 2 GB) | 6 GB |
| CPU | 4 o más (en CPU, la IA tarda 1-2 min por muestra) | 2 |

Puertos libres: 5678, 11434, 8101, 8102 y 8088. Cualquiera se cambia en `.env` (`N8N_PUERTO`, etc.).

`bash scripts/preparar_maquina.sh` verifica todo esto y dice qué falta y cómo instalarlo. Con
`--instalar` ejecuta la instalación con apt, dnf o pacman (vía sudo), brew o winget. Docker Desktop en
Windows se instala a mano: requiere reiniciar.

## 3. Paso a paso

En Windows, todos los comandos se escriben en **Git Bash** (no en PowerShell ni en WSL). Para quien
prefiere PowerShell, `.\scripts\levantar_todo.ps1` ejecuta el mismo `levantar.sh`.

```bash
# 1. Clonar (la rama con el ecosistema integrado)
git clone -b branchTest https://github.com/iam-s21-caece/HackatonCiberdefensa.git
cd HackatonCiberdefensa

# 2. Verificar la máquina (no cambia nada). Si falta algo, instalarlo y repetir.
bash scripts/preparar_maquina.sh            # o: bash scripts/preparar_maquina.sh --instalar

# 3. Levantar todo (la primera vez baja ~9 GB de imágenes y el modelo de 2 GB)
bash scripts/levantar.sh                    # o: bash scripts/levantar.sh --sin-ia
```

`levantar.sh` hace, en orden:

1. Verifica requisitos.
2. Crea `.env` desde `.env.example`, genera `AGENTE2_TOKEN` y la contraseña del administrador de n8n
   (en `.env` queda sólo su hash bcrypt; la contraseña se muestra una vez).
3. Controla la exposición de puertos.
4. Prepara `./data`.
5. Baja las imágenes fijas y construye las de los agentes y la interfaz.
6. Levanta los contenedores.
7. Espera la salud de cada servicio y la descarga del modelo.
8. Comprueba que los tres webhooks estén publicados.

Se puede volver a correr en cualquier momento.

```bash
# 4. Probar una muestra con el script de Pablo
bash scripts/analizar.sh samples/phishing_credenciales.json
bash scripts/analizar.sh samples/phishing_reembolso.eml
bash scripts/analizar.sh samples/whatsapp_secuestro_cuenta.json     # la puerta sale del nombre del archivo

# 5. Verificación completa con evidencia (§ 6). Cerrar el dashboard mientras corre.
bash scripts/verificar_e2e.sh
bash scripts/verificar_e2e.sh --registrar-verdad    # además carga la verdad de cada muestra como veredicto humano

# 6. Abrir el dashboard y n8n
#    http://localhost:8088   (dashboard)
#    http://localhost:5678   (n8n: usuario admin@centinela.local, contraseña mostrada en el paso 3)

# 7. Apagar o eliminar
docker compose stop                          # conserva todo
bash scripts/eliminar.sh                     # contenedores, red, volúmenes e imágenes del proyecto
bash scripts/eliminar.sh --todo              # además ./data, .env, ./evidencias e imágenes base del build
```

## 4. Cómo llega el flujo a n8n

**Automático, por comando.** Lo hace el servicio `n8n-importar` en cada `docker compose up`:

```bash
n8n import:workflow --input=/workflow/centinela_workflow.json   # lo deja sin publicar
n8n publish:workflow --id=CentinelaPhish01                      # lo activa (webhooks)
```

En n8n 2.x, `update:workflow --active=true` quedó deprecado y fue reemplazado por `publish:workflow`.
Como el importador corre antes que n8n, no hace falta reiniciarlo. Para confirmarlo:
`docker compose logs n8n | grep Activated` muestra
`Activated workflow "CENTINELA - Triage de phishing con IA"`.

**A mano, por comando** (por ejemplo, con n8n ya corriendo y un flujo modificado):

```bash
python workflow/build_workflow.py
docker compose exec n8n n8n import:workflow --input=/workflow/centinela_workflow.json
docker compose exec n8n n8n publish:workflow --id=CentinelaPhish01
docker compose restart n8n
```

**A mano, por la interfaz de n8n** (sin scripts):

1. Abrir `http://localhost:5678` e ingresar con el administrador. Si `N8N_OWNER_DESDE_ENTORNO=false`,
   crearlo en ese momento.
2. *Overview → Create workflow → menú ⋯ → Import from File…* y elegir
   `workflow/centinela_workflow.json`.
3. *Publish* (arriba a la derecha).
4. Verificar: `curl http://localhost:5678/webhook/centinela/analizar` responde "not registered for GET".
   Eso indica que el webhook POST está publicado.

## 5. Configuración (`.env`)

Todo es opcional salvo lo que `levantar.sh` genera. Las variables más importantes:

| Variable | Valor por defecto | Qué controla |
|---|---|---|
| `N8N_VERSION`, `OLLAMA_VERSION` | 2.39.7, 0.34.1 | versiones fijas (cambiarlas es cambiar el experimento) |
| `CENTINELA_BIND` | 127.0.0.1 | interfaz donde se publican los puertos |
| `*_PUERTO` | 5678, 11434, 8101, 8102, 8088 | puertos en la máquina |
| `VT_API_KEY`, `ABUSEIPDB_API_KEY`, `ABUSECH_API_KEY` | vacías | fuentes de inteligencia externas del flujo |
| `IA_PROVEEDOR` | auto | `ollama`, `deepseek` o `auto` (DeepSeek si `DEEPSEEK_API_KEY` tiene valor; si no, Ollama). Con DeepSeek no se levanta Ollama y `levantar.sh` valida la key contra `/models` |
| `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL`, `DEEPSEEK_URL` | vacía, deepseek-chat, https://api.deepseek.com | IA externa. **La evidencia de cada mensaje (remitente, asunto, cuerpo, URLs) sale hacia DeepSeek.** La key la lee sólo el nodo HTTP de n8n desde el entorno: no entra en el ítem ni en el reporte |
| `OLLAMA_MODEL` | llama3.2:3b | modelo de la IA local |
| `ORIGENES_CONFIABLES` | imap,eml_crudo,json_estructurado | **perfil demo**: el Agente 1 confía en las cabeceras `Received` de lo que sube `analizar.sh` desde esta máquina. En producción, sólo `imap` |
| `AGENTE2_TOKEN` | (generado) | token Bearer para registrar veredictos desde el dashboard |
| `N8N_OWNER_EMAIL`, `N8N_OWNER_PASSWORD_HASH` | admin@centinela.local, (generado) | administrador de n8n creado desde el entorno |

`.env` está en `.gitignore`. Nunca se versiona.

## 6. Verificación de extremo a extremo (el experimento)

`bash scripts/verificar_e2e.sh` corre cada muestra de `samples/` con `scripts/analizar.sh`, es decir,
el mismo camino que usa un analista. Contrasta cada resultado con las hipótesis de
[`samples/esperados.json`](../samples/esperados.json), escritas **antes** de correr a partir de la
verdad de cada muestra y de las reglas documentadas.

| # | Comprobación | Qué demuestra |
|---|---|---|
| C1 | n8n responde con un `report_id` | el flujo recibe por la puerta del canal (correo, WhatsApp o SMS) |
| C2 | veredicto dentro de lo aceptado y reglas duras requeridas presentes | **el flujo identifica el patrón**. Lo aceptado respeta los guardrails: un malicioso nunca se entrega y un legítimo nunca se bloquea |
| C3 | `data/reports/<id>.json` escrito y sin el valor de ninguna clave de `.env` | el reporte queda para los agentes y no expone secretos |
| C4 | correo: el Agente 1 analizó (`ok`/`parcial`), su conclusión es la esperada y tiene traza propia (`/trazas/<id>`); WhatsApp/SMS: `NO_APLICA` y sin traza | **el Agente 1 actuó por su cuenta**: eligió acciones, consultó DNS y concluyó. En mensajería, la guarda de canal evita llamarlo |
| C5 | la traza del Agente 2 (`ciclos.jsonl`) registra el reporte en un ciclo con `motivo=autonomo`, y su API lo sirve | **el Agente 2 lo percibió solo**, en su propio ciclo: nadie se lo pidió |
| C6 | el mismo reporte llega por nginx (`:8088/api/reportes/<id>`), con la traza del Agente 1 si es correo y sin claves | **el dashboard recibe todo** |

Además guarda lo que el dashboard recibe de cada endpoint: cola, métricas, calibración, supervisión,
actores, aprendizaje, ATT&CK y la capa Navigator. Con `--registrar-verdad` carga la verdad de cada
muestra como veredicto humano a través del dashboard (con token), lo que cierra el bucle de aprendizaje
de los dos agentes.

**Evidencia** en `evidencias/<fecha UTC>-<commit>/`:

| Archivo | Contenido |
|---|---|
| `resumen.md` | tabla por muestra (veredicto, score, reglas, IA, Agente 1, Agente 2, C1–C6, segundos) y totales |
| `resumen.json`, `resultados.jsonl` | lo mismo, legible por máquina |
| `entorno.json` | commit y cambios sin commit, SO, Docker/Compose, id y digest de cada imagen, versión de n8n, modelo de IA con digest, configuración efectiva de cada contenedor (secretos enmascarados) y SHA-256 del flujo, de las hipótesis y de cada muestra |
| `respuestas/` | respuesta completa de n8n por muestra |
| `agente1/` | traza de cada análisis del Agente 1 y su estado antes y después |
| `agente2/` | ciclo del Agente 2 que percibió cada reporte y su detalle |
| `interfaz/` | lo que recibe el dashboard |

**Condiciones controladas y amenazas a la validez** (para comparar corridas):

- **No abrir el dashboard mientras corre.** Sus consultas disparan ciclos del Agente 2 y la percepción
  deja de quedar atribuida al ciclo autónomo (C5 fallaría).
- **La IA no es determinística** (temperatura 0,1), y con DeepSeek el proveedor puede cambiar el modelo
  detrás del mismo nombre: `entorno.json` registra el proveedor. Por eso C2 acepta lo que garantizan los
  guardrails y el resumen informa aparte cuántas muestras coincidieron con el veredicto ideal.
  `--sin-ia` elimina esa fuente de variación.
- **DNS público:** `legitimo.json` depende del SPF real de ejercito.mil.ar y `phishing_credenciales.json`
  de que ejercito-mil.ar siga sin registrarse (`depende_de` en las hipótesis).
- **API keys:** con claves de VirusTotal, AbuseIPDB o abuse.ch el puntaje puede subir (más evidencia).
  `entorno.json` registra si estaban configuradas.
- **Hipótesis que fallan:** no se editan las hipótesis para que pasen sin documentar por qué cambiaron.

## 7. Solución de problemas

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| `$'\r': command not found` al correr un `.sh` | checkout de Windows anterior a `.gitattributes` | `rm scripts/*.sh && git checkout -- scripts/` o volver a clonar |
| `n8n-importar: exited:1` | JSON del flujo inválido o base de n8n corrupta | `docker compose logs n8n-importar`; regenerar con `python workflow/build_workflow.py` |
| webhook "not registered" | el flujo no quedó publicado | `docker compose logs n8n \| grep -i activ`; volver a correr `levantar.sh` |
| `IA: no disponible` en todos los reportes | modelo sin bajar, poca memoria o `--sin-ia` | `docker compose logs ollama-modelo`; dar más memoria a Docker |
| `Agente 1: no disponible` | contenedor caído | `docker compose ps`; `docker compose logs agente-identidad` |
| C5 falla con `motivo "consulta"` | dashboard abierto durante la verificación | cerrarlo y repetir |
| n8n no escribe `data/reports` (Linux) | permisos de la carpeta (n8n es uid 1000) | `levantar.sh` los ajusta; a mano: `sudo chown -R 1000:1000 data` |
| puerto ocupado | otro servicio en la máquina | cambiar `*_PUERTO` en `.env` |
| log de n8n: `Failed to start Python task runner` | la imagen de n8n no trae Python | inofensivo: el flujo sólo usa nodos Code en JavaScript |
| `curl` o `jq` no encuentran archivos en Git Bash | versión de scripts anterior al arreglo de rutas | actualizar `scripts/_comun.sh` |

## 8. En una VPS (Linux)

Los mismos pasos de § 3, más estas especificaciones:

- **Usuario:** con permiso de Docker (`groups` muestra `docker`) o root.
- **n8n previo en la máquina:** si ya hay otro n8n escuchando en 5678, cambiar `N8N_PUERTO` en `.env`.
  CENTINELA levanta el suyo, con su propia base, y no toca el existente. Lo mismo vale para cualquier
  puerto que `preparar_maquina.sh` marque como ocupado.
- **Acceso desde tu computadora:** los puertos quedan en 127.0.0.1 de la VPS y no se exponen a
  Internet. Se usan con un túnel SSH:

  ```bash
  ssh -N -L 8088:127.0.0.1:8088 -L 5678:127.0.0.1:5678 -L 8102:127.0.0.1:8102 usuario@IP_DE_LA_VPS
  # y en el navegador local: http://localhost:8088 (dashboard) y http://localhost:5678 (n8n)
  ```

- **No abrir** 5678, 8101, 8102, 8088 ni 11434 en el firewall. Para exponer el dashboard a terceros hace
  falta un proxy con TLS y autenticación delante, y `ORIGENES_CONFIABLES=imap`. Es otro perfil, fuera
  del alcance de la demo.
- **Permisos de `./data`:** n8n escribe como uid 1000. `levantar.sh` lo detecta y ajusta los permisos
  con un contenedor, sin sudo.
- **Recursos:** con la IA local en CPU, cada muestra tarda 1-2 min (8 muestras ≈ 15 min). Con
  `--sin-ia`, segundos.

## 9. Verificado en

Registro de lo que se probó, en qué máquina y con qué resultado.

**Windows 11 + Docker Desktop 29.3 (Compose 5.1), Git Bash · 2026-09-17**, proyecto aislado
(`COMPOSE_PROJECT_NAME=centinela-verif`, puertos alternativos):

| Qué | Resultado |
|---|---|
| `levantar.sh` desde cero (imágenes, build, modelo de 2 GB) | ✔ código 0 en 6 min: 5 servicios sanos, `n8n-importar` y `ollama-modelo` con código 0, 3 webhooks publicados |
| `levantar.sh` por segunda vez (idempotencia) | ✔ código 0 en 61 s; no regeneró secretos; reimportó y publicó el flujo |
| n8n importa y publica el flujo por comando | ✔ log `Activated workflow "CENTINELA - Triage de phishing con IA"` |
| Administrador de n8n creado desde `.env` (hash bcrypt) | ✔ log `Owner was set up successfully` |
| Agentes con sistema de archivos de solo lectura, sin capabilities | ✔ sanos |
| Webhook de correo con IA local (`legitimo.json`) | ✔ HTTP 200 con el reporte completo en 73 s; reporte escrito en `data/reports` |
| Pruebas: Agente 1, Agente 2 (31), contratos entre agentes (4), despliegue (8, con control negativo) | ✔ |
| Errores de los scripts encontrados en esta máquina | salida CRLF de `jq.exe` y conversión de rutas para `curl.exe` (exclusivos de Git Bash): corregidos en `scripts/_comun.sh` |
| IA por DeepSeek (`DEEPSEEK_API_KEY`) | ✔ prueba unitaria del nodo 13 del flujo generado (respuesta DeepSeek, respuesta Ollama, error 401 → motor de reglas, claves enmascaradas en el reporte); ✘ **pendiente** la llamada real (requiere la key) |
| macOS | no probado |

**VPS Linux · 2026-09-17** (prueba del equipo, desde cero con los pasos de § 3 y § 8):

| Qué | Resultado |
|---|---|
| `preparar_maquina.sh` | ✔ detectó un n8n previo que ocupaba el puerto 5678; se detuvo ese contenedor |
| `levantar.sh` | ✔ todos los servicios sanos, flujo importado y publicado |
| `analizar.sh` y `verificar_e2e.sh` | ✔ el flujo, los dos agentes y el dashboard respondieron en la cadena completa |
| Hallazgo | el control de webhooks de `levantar.sh` daba OK con el flujo sin publicar (buscaba "GET", presente en las dos respuestas de n8n): ahora exige `not registered for GET`, verifica que el puerto lo publique el n8n de CENTINELA y muestra el diagnóstico si no. Un puerto ocupado por otro servicio pasó de aviso a error |

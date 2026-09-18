# Interfaz de CENTINELA

Panel del investigador sobre los dos agentes. Esta etapa es **la base** (RI-08): shell, navegación,
cliente de la API, estado de los agentes y despliegue. Los módulos están registrados y cada uno
verifica en vivo su endpoint, pero sus vistas todavía no están construidas (RI-01 a RI-07, RI-09 y
RI-10 en [docs/REQUERIMIENTOS.md](../docs/REQUERIMIENTOS.md)).

## Qué hay

| Pieza | Archivo | Qué hace |
|---|---|---|
| Shell | `src/App.jsx` | Barra lateral, encabezado del módulo activo y tema. Sin lógica de negocio |
| Registro de módulos | `src/modules/registry.js` | Un módulo = una entrada (identidad, requerimientos, endpoint, vista) |
| Cliente | `src/api/client.js` | URL relativa, sin caché, errores tipados con el `detail` de la API |
| Endpoints | `src/api/centinela.js` | Única lista de rutas del frontend (contrato RA2-08) |
| Polling | `src/hooks/usePolling.js` | El dato viejo sobrevive a un error; refresco al montar y cada 10 s |
| Estado de agentes | `src/hooks/useSalud.js` | Agente 1 y Agente 2, independientes entre sí |
| Módulo pendiente | `src/components/ModuloPendiente.jsx` | Muestra requerimiento, endpoint y la respuesta real del agente |
| Convenciones | `src/utils/format.js` | Los veredictos del flujo se muestran como acciones: Bloquear / Escalar / Entregar |

Estructura portada de `pro-inves-frontend` (registro de módulos, cliente, polling). La identidad
visual es propia de CENTINELA y está bloqueada en [`design.md`](design.md) (tokens en
[`tokens.css`](tokens.css)), diseñada con la skill Hallmark:

- **Tema "expediente técnico"**: papel claro como principal (se lee en proyector) y variante oscura
  "guardia nocturna"; acento celeste sólo como marca. Contraste WCAG verificado en los dos temas.
- **Tipografía empaquetada localmente** (`@fontsource`): Big Shoulders Display, IBM Plex Sans e IBM Plex
  Mono. El navegador del analista no le pide nada a terceros.
- **Firmas del sistema**: sellos de veredicto (forma + palabra, nunca sólo color), trama rayada para lo
  no verificado o en preparación, procedencia en cada dato y colofón con el contexto del torneo.
- **Sin pantalla de ingreso.** Un login que no valida nada sugiere una seguridad que no existe. La única
  escritura (veredicto humano) exige el token del Agente 2; la autenticación del analista es una
  decisión pendiente del proyecto.
- **Cada módulo lee sus datos sólo mientras está abierto.** El shell sólo lee el estado de los agentes.

## Rutas

El navegador nunca habla directo con los agentes. Pide todo a su propio origen:

| Ruta | Destino | Por qué |
|---|---|---|
| `/api/*` | Agente 2 (`:8102`) | Es la API de la interfaz |
| `/agente1/salud` | Agente 1 (`:8101/salud`) | Sólo el estado. `/analizar` es para n8n y no se expone |

En desarrollo las enruta el proxy de Vite (`vite.config.js`); en el contenedor, nginx
(`nginx/default.conf.template`), con las mismas rutas.

## Ejecutar

```bash
# 1) agentes (desde la raíz del repo, con el .venv)
cd 1AgenteModelosObjetivos && ORIGENES_CONFIABLES=imap,eml_crudo uvicorn --factory agente_identidad.api:crear_app --port 8101
cd 2AgenteAprendizaje && CENTINELA_REPORTES_DIR=<reportes del flujo> AGENTE2_TOKEN=<token> uvicorn --factory agente_aprendizaje.api:crear_app --port 8102

# 2) interfaz
cd interfaz
npm install
npm run dev          # http://localhost:5173
npm run lint && npm run build
```

Todo el ecosistema en contenedores (n8n, IA, agentes e interfaz): `bash scripts/levantar.sh` desde la
raíz ([docs/DESPLIEGUE.md](../docs/DESPLIEGUE.md)). La interfaz queda en `http://localhost:8088`.

## Verificado en esta etapa

- `npm run lint` sin advertencias y `npm run build` correcto (234 KB de JS, 74 KB con gzip; fuentes como
  archivos locales).
- Contra los dos agentes reales con los 42 reportes de demo: las rutas responden a través del proxy;
  `POST /agente1/analizar` da 404 (no expuesto).
- En navegador sin interfaz gráfica (puppeteer), temas claro y oscuro, a 320 · 375 · 414 · 768 · 1280 ·
  1366 · 1920 px: sin scroll horizontal, ningún texto clicable en dos líneas, ítems de navegación de
  44 px, las tres fuentes cargadas, **cero pedidos a terceros** y sin errores de consola.
- Slop-test de Hallmark (57 gates): las fallas encontradas en la primera pasada (gates 24, 26, 33, 38,
  44, 48, 49, 55 y tamaño táctil) se corrigieron y se volvieron a medir.
- Imagen Docker (nginx con los estáticos) construida y sana dentro del ecosistema completo (`docker-compose.yml`),
  en Windows con Docker Desktop y en una VPS Linux. Recibe por nginx todos los endpoints del Agente 2 y el estado del
  Agente 1 (comprobación C6 de `scripts/verificar_e2e.sh`).

## Cómo se construye un módulo

1. Crear `src/modules/<modulo>/<Modulo>Module.jsx`, que recibe `{ modulo }` y lee con
   `usePolling(modulo.lectura)`.
2. En `registry.js`, reemplazar `Component: ModuloPendiente` por el componente nuevo.
   Leer antes [`design.md`](design.md): la familia de estructura de cada módulo, sellos, trama y
   procedencia ya están definidos; un módulo que se aparta del sistema lo enmienda ahí primero.
3. Citar su `RI-xx` en el componente: la matriz de trazabilidad no cuenta el registro ni el módulo
   pendiente como implementación.

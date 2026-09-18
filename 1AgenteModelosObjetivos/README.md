# Agente 1 · Identidad del remitente

Agente **basado en modelos y orientado a objetivos** (Russell & Norvig) que responde una sola
pregunta: *¿el remitente es quien dice ser?* Lo responde **recalculando** SPF, DKIM y DMARC en vez
de leerlos de las cabeceras, que cualquiera puede escribir.

Se integra al flujo n8n de CENTINELA como un analizador más (el número 11), con el mismo formato
de salida que los otros diez. No mapea MITRE ATT&CK: eso lo hace el flujo.

Requerimientos: `RA1-01` a `RA1-13` en [docs/REQUERIMIENTOS.md](../docs/REQUERIMIENTOS.md).

## Por qué existe

El flujo toma SPF/DKIM/DMARC de la cabecera `Authentication-Results` del propio mensaje. Un
atacante que agrega **una línea** con `spf=pass dkim=pass dmarc=pass` a un correo que dice venir de
`@ejercito.mil.ar` obtiene puntos a favor y la regla dura `interno_autenticado_limpio`, que fuerza
la entrega.

Resultado medido con el código real del workflow (`tests/test_integracion_flujo.py`):

| Muestra | IA | Flujo original | Flujo + Agente 1 |
|---|---|---|---|
| BEC con cabecera forjada | caída | score 7 · **entrega** | score 100 · bloquea |
| BEC con cabecera forjada | dice "legítimo" | score 7 · **entrega** | score 100 · escala |
| BEC sin cabecera forjada | dice "legítimo" | score 42 · **entrega** | score 100 · escala |
| Boletín interno legítimo | coincide | score 2 · entrega | score 2 · entrega |
| Phishing de reembolso | coincide | score 100 · bloquea | score 100 · bloquea |

## Diseño

**Modelo del mundo** (lo que un correo aislado no muestra):
- `ModeloOrganizacion`: dominios propios y MX de confianza. Los MX se aprenden del DNS de los
  dominios propios; para `ejercito.mil.ar` hoy es `mx4.ejercito.mil.ar`.
- `ModeloRelaciones`: quién le escribió antes a quién. Sólo aprende de correos con veredicto humano
  legítimo, o entregados con identidad verificada. Un atacante al que le entregaron un correo no se
  convierte en contacto conocido.

**Objetivo**: concluir `IDENTIDAD_VERIFICADA`, `SUPLANTACION_CONFIRMADA` o `NO_VERIFICABLE` y
evaluar el patrón BEC. **Acciones** (en cada paso se elige, entre las aplicables, la de mayor valor):

| Acción | Precondición | Valor | Para qué |
|---|---|---|---|
| `identificar_origen` | origen desconocido | 100 | IP que entregó el correo a un MX propio |
| `verificar_dkim` | hay `.eml` crudo y firma | 90 | prueba criptográfica, independiente de la ruta |
| `consultar_politica_dmarc` | hay dominio en el From | 80 | qué exige el dueño del dominio |
| `recalcular_spf` | origen confiable, política conocida, **DKIM no alcanza ya** | 70 | ¿la IP está autorizada? |
| `evaluar_dmarc` | no queda SPF ni DKIM pendiente | 60 | alineación con el From |
| `concluir_identidad` | DMARC evaluado | 50 | primera parte del objetivo |
| `consultar_relacion` | — | 40 | ¿primer contacto? |
| `evaluar_patron_bec` | identidad concluida | 30 | segunda parte del objetivo |

La precondición de `recalcular_spf` es la parte orientada a objetivos que se ve en acción: si una
firma DKIM alineada ya prueba la identidad, el agente no gasta hasta 10 consultas DNS en SPF.

**Rigor**: sólo se afirma `fail` cuando ninguna vía pudo pasar. Si el correo trae firma DKIM y no
llegó el `.eml` crudo, esa firma podría ser válida: el resultado es `NO_VERIFICABLE`, nunca
suplantación. Ante una falla DNS el estado es `parcial` y no se emiten hallazgos sobre lo que no se
verificó.

## Hallazgos que agrega

Todos con prefijo `a1_`, en categorías que ya existen en el motor de puntaje y con pesos dentro de
sus topes. Un recálculo que coincide con lo que el flujo ya leyó no suma puntaje; verificar la
identidad tampoco resta, porque una cuenta interna comprometida también pasa DMARC.

| Tipo | Categoría | Peso | Cuándo |
|---|---|---|---|
| `a1_autenticacion_forjada` | autenticacion | 40 | lo declarado dice pass y el recálculo lo refuta |
| `a1_spf_recalculado_fail` / `_softfail` | autenticacion | 20 / 10 | SPF recalculado difiere de lo declarado |
| `a1_dkim_firma_invalida` | autenticacion | 18 | firma presente que no verifica |
| `a1_dmarc_recalculado_fail_{reject,quarantine,none}` | autenticacion | 25 / 18 / 8 | DMARC recalculado falla |
| `a1_suplantacion_dominio_propio` | identidad | 40 | From propio sin SPF ni DKIM que lo respalden |
| `a1_suplantacion_dominio_externo` | identidad | 30 | From externo con DMARC reject/quarantine incumplido |
| `a1_patron_bec_primer_contacto` / `a1_patron_bec` | contexto | 20 / 15 | autoridad + pago + identidad no verificada |
| `a1_instruccion_pago` | contexto | 8 | CBU/CVU válido o alias, sin el resto del patrón |
| `a1_identidad_verificada`, `a1_origen_no_verificable` | — | 0 | informativos |

El CBU/CVU se valida con los dígitos verificadores del BCRA y se enmascara en trazas y resultados.
Para que el Agente 2 correlacione campañas que piden transferir al mismo destino, sólo se expone una
huella (`bec.destinos_hash`): el número en claro no sale del Agente 1.

## Integración con n8n

El workflow original (`resources/centinela.json`) **no se toca**. Se genera una copia:

```bash
python integracion_n8n/parchear_flujo.py
# -> integracion_n8n/centinela_con_agente1.json
```

La copia agrega un nodo Code (`nodo_agente1.js` + las utilidades compartidas del flujo), lo conecta
desde "Desarmar correo" y pasa "Unir inteligencia" de 10 a 11 entradas. Nada más.

> **En este repositorio la integración ya está hecha:** el generador del flujo (`workflow/build_workflow.py`)
> incluye este nodo con una guarda de canal (`workflow/nodes/17_agente1.js`, verificado por
> `test_rg_01_el_flujo_integra_el_nodo_del_agente1_sin_cambios_salvo_la_guarda_de_canal`) y
> `docker-compose.yml` levanta el agente en la misma red que n8n. Lo que sigue es para un flujo sin integrar.

En n8n:
1. Importar `centinela_con_agente1.json`.
2. Definir `AGENTE1_URL` en el entorno de n8n. Por defecto es `http://host.docker.internal:8101`;
   si el agente corre en la misma red de Docker, `http://agente-identidad:8101`.
3. Si el agente no responde, el nodo sale `con_error` sin hallazgos y el flujo decide igual que sin
   él (`test_rg_04_*`).

## Ejecutar

```bash
# local (desde la raíz del repo hay un .venv con las dependencias)
cd 1AgenteModelosObjetivos
ORIGENES_CONFIABLES=imap,eml_crudo uvicorn --factory agente_identidad.api:crear_app --port 8101

# docker
docker build -t centinela-agente1:1.0.0 .
docker run --rm -p 8101:8101 -e ORIGENES_CONFIABLES=imap,eml_crudo -v ./data:/data centinela-agente1:1.0.0
```

Endpoints: `POST /analizar` (contrato del flujo), `GET /salud` (modelo de la organización y estado
del aprendizaje), `GET /trazas/{report_id}` (razonamiento completo de un análisis).

Configuración: ver [.env.example](.env.example). La decisión de seguridad importante es
`ORIGENES_CONFIABLES`. Para la demo con muestras subidas al webhook hay que habilitar `eml_crudo`;
en producción, sólo si el que sube el `.eml` es un componente propio.

## Pruebas

```bash
pytest -m "not integracion"   # 51 pruebas unitarias, <1 s, sin red
pytest                        # + 11 de integración: corren el workflow real con Node.js (~3 min, usa red)
```

Los fixtures `parser_*.json` son la salida real del nodo "Desarmar correo" generada con
`herramientas/harness_flujo/harness.mjs` (ver [tests/fixtures/README.md](tests/fixtures/README.md)).

## Trazabilidad del razonamiento

Cada análisis agrega una línea a `data/agente1/trazas/AAAA-MM-DD.jsonl` con la entrada resumida,
cada paso (acción, propósito, candidatas, resultado, ms, consultas DNS), la conclusión y los
hallazgos. La conclusión y los pasos resumidos también viajan en el reporte del flujo, en
`fuentes.agente_identidad.resultados`.

## Límites declarados

- **SPF**: macros (`%{i}`) → `no_soportado`; `ptr` nunca coincide; no se aplica el límite de consultas vacías.
- **ARC**: no se evalúa. Un correo reenviado por una lista puede romper SPF/DKIM legítimamente;
  queda `NO_VERIFICABLE` o, si el dominio publica `p=reject`, suplantación.
- **DKIM** necesita el `.eml` crudo: por IMAP no llega, así que ahí la identidad depende del SPF.
- **Muestras de prueba propias**: un correo "interno legítimo" armado a mano tiene que salir desde
  una IP autorizada por el SPF real de `ejercito.mil.ar` (`179.51.212.118`, sus registros `a` o
  `mx`). Si no, el agente lo detecta como suplantación, y tendría razón.

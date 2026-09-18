# Agente 2 · Aprendizaje y supervisión

Agente **de aprendizaje** (Russell & Norvig). Su elemento de desempeño es la política de decisión
del flujo n8n: umbrales, IA y guardrails. Usa el **veredicto humano** como verdad externa para medir
esa política, proponer cómo mejorarla y vigilar al decisor IA. No analiza correos ni decide sobre
ellos, y no modifica el flujo.

Requerimientos: `RA2-01` a `RA2-12` en [docs/REQUERIMIENTOS.md](../docs/REQUERIMIENTOS.md).

## Componentes

| Componente R&N | Módulo | Qué hace |
|---|---|---|
| Percepción | `percepcion.py` | Lee `data/reports/*.json` de forma incremental y en solo lectura; registra veredictos humanos append-only |
| Crítico | `critico.py` | Compara la acción del flujo con la verdad bajo una matriz de costos configurable |
| Elemento de aprendizaje | `aprendizaje.py` | Barre umbrales y **propone** el par de menor costo, con el rango de empates; curva de aprendizaje en casos reservados |
| Generador de problemas | `generador.py` | Ordena la cola de revisión por valor informativo, con motivos |
| Supervisor del decisor IA | `supervisor.py` | Degradaciones, guardrails, caídas y latencia; **aprende de los veredictos cuánto riesgo tienen las degradaciones** y ajusta su sensibilidad |
| Caracterización de actores | `actores.py` | Agrupa correos maliciosos que comparten infraestructura en actores/campañas, sin atribución nominal |
| — | `attack_aporte.py` | ATT&CK agregado (sin re-mapear) + capa Navigator; aporte contrafáctico del Agente 1 |
| Ciclo | `bucle.py` | percibir → criticar → aprender → supervisar → caracterizar actores → generar problemas → trazar |

## Evidencia de que aprende

Se demuestra, no se declara. `experimentos/curva_aprendizaje.py` aprende umbrales con n veredictos y
mide el costo por correo en casos **reservados** contra los umbrales vigentes (30/65), con 40
particiones al azar. La población es sintética, está declarada como tal y los grupos se solapan a
propósito (70 % legítimos con un 8 % de boletines de puntaje medio; 30 % maliciosos, un tercio sutiles
tipo BEC):

```
    n |  costo reservado aprendido | vigente 30/65 |  mejora | no peor
   10 |       0.6680 ± 0.4708      |        0.5093 | -0.1587 | 50%
   20 |       0.7609 ± 0.5655      |        0.5159 | -0.2450 | 50%
   40 |       0.3596 ± 0.3192      |        0.5037 | +0.1441 | 82%
   80 |       0.2723 ± 0.2580      |        0.5111 | +0.2387 | 90%
  160 |       0.1834 ± 0.1575      |        0.5234 | +0.3399 | 98%
  320 |       0.1031 ± 0.0735      |        0.5161 | +0.4130 | 100%
```

Dos lecturas, las dos importan:
- **Aprende**: con más veredictos, el costo en correos que no vio baja a una quinta parte y la
  variabilidad se achica.
- **Con pocos veredictos empeora**: con 10 o 20 sobreajusta. Por eso `MUESTRA_MINIMA` es 40 (sale
  de esta tabla) y por eso el agente **propone y no aplica**.

Con veredictos reales suficientes (el doble de la muestra mínima), `GET /api/aprendizaje` calcula la
misma curva sobre datos reales.

Sobre la IA, aprende de los veredictos qué proporción de sus degradaciones resultó maliciosa (intervalo
de Wilson 95 %). Si ese riesgo supera la tolerancia (10 %), recomienda con evidencia el guardrail
monótono en el flujo y reduce el margen que tolera antes de alertar por aumento de degradaciones.

## Actores y campañas

Un actor es un conjunto de indicadores técnicos, no una organización con nombre (atribución técnica,
no política). Se unen correos maliciosos, o no entregados sin veredicto, que comparten **IP de origen**
(la del Agente 1 cuando la ruta es confiable), **Reply-To**, **dominio** (excluidos propios, gratuitos y
plataformas masivas), **adjunto** o **destino de pago**. El destino de pago llega como huella del
Agente 1; el CBU en claro nunca sale de ese agente. Cada actor explica sus vínculos, y un veredicto
humano LEGITIMO saca al correo del análisis.

### Convención de TP/FP

Los veredictos del flujo (`VERDADERO_POSITIVO`, `ESCALAR`, `FALSO_POSITIVO`) se tratan como
**acciones**: bloquear, escalar, entregar. TP/FP/FN/TN sólo existen al compararlas con el veredicto
humano, y se reportan con dos lecturas:
- **detección**: positivo = no entregar. Mide si algo malicioso llegó al usuario.
- **bloqueo automático**: positivo = bloquear. Mide cuánto resuelve el sistema sin un humano.

Costos por defecto: entregar un malicioso 20, bloquear un legítimo 1, escalar 0,2.

### Decisiones de diseño

- **Propone, no aplica.** Cambiar el umbral de bloqueo de una fuerza armada es una decisión humana.
  La propuesta informa el rango de empates: con pocos casos muchos pares cuestan lo mismo, y
  mostrar un único número sería sobreajustar.
- **La simulación es del motor de reglas.** La IA no se re-ejecuta sobre el pasado. Por eso se
  reportan en paralelo el costo del flujo final y el del motor de reglas solo: la diferencia es lo
  que aportan (o restan) la IA y los guardrails.
- **La réplica del puntaje verifica paridad** contra cada reporte antes de usarse. Un reporte que no
  coincide se excluye del aporte del Agente 1 en lugar de afirmar un contrafáctico dudoso.
- **La degradación de la IA** (proponer una acción menos severa que las reglas) es la dimensión
  vigilada, porque es la firma de una inyección de prompt. Si un humano confirma que una degradación
  era maliciosa, se emite alerta: crítica si el correo llegó al usuario.
- **Escritura mínima y autenticada.** Sólo `POST /api/reportes/{id}/veredicto`, con token Bearer.
  Sin `AGENTE2_TOKEN`, la escritura queda deshabilitada.

## API

| Método | Ruta | Uso |
|---|---|---|
| GET | `/api/salud` | estado, umbrales vigentes, si la escritura está habilitada |
| GET | `/api/reportes?veredicto=` | resúmenes con veredicto humano |
| GET | `/api/reportes/{id}` | reporte completo, historial de veredictos, aporte y traza del Agente 1, prioridad |
| POST | `/api/reportes/{id}/veredicto` | `{veredicto: MALICIOSO|LEGITIMO, analista, comentario}` + `Authorization: Bearer` |
| GET | `/api/cola` | cola priorizada con motivos |
| GET | `/api/metricas` | crítico (flujo final vs motor de reglas), dimensiones IA, aporte del Agente 1 |
| GET | `/api/calibracion` | propuesta de umbrales, rango óptimo y curvas de costo |
| GET | `/api/supervision` | línea base, ventana, umbral de degradación, meta-alertas |
| GET | `/api/actores` | actores/campañas con vínculos, indicadores, período, veredictos y técnicas |
| GET | `/api/aprendizaje` | confiabilidad de las degradaciones de la IA, curva real (si alcanza) y experimento controlado |
| GET | `/api/attack`, `/api/attack/navigator` | técnicas agregadas y capa para ATT&CK Navigator |

## Ejecutar

```bash
cd 2AgenteAprendizaje
CENTINELA_REPORTES_DIR=../herramientas/datos_demo/reports AGENTE2_TOKEN=cambiar \
  uvicorn --factory agente_aprendizaje.api:crear_app --port 8102

docker build -t centinela-agente2:1.0.0 .
docker run --rm -p 8102:8102 -e AGENTE2_TOKEN=cambiar \
  -v /ruta/a/n8n/data/reports:/centinela/reports:ro -v ./data:/data centinela-agente2:1.0.0
```

Configuración: [.env.example](.env.example).

## Pruebas

```bash
pytest                                   # pruebas del agente, sin red
python experimentos/curva_aprendizaje.py # regenera la evidencia de aprendizaje
```

Los fixtures son 42 reportes reales del flujo: 7 muestras × {flujo original, flujo con Agente 1} ×
IA {coincide, dice "legítimo", caída}, generados con `herramientas/generar_reportes.py`.
`fixtures/escenarios.json` registra la combinación y la verdad de cada uno. Las respuestas de la IA
son simuladas por el harness.

## Trazabilidad

- `data/agente2/trazas/ciclos.jsonl`: una línea por ciclo que percibió algo nuevo (qué percibió,
  costo del flujo y del motor de reglas, propuesta, alertas nuevas, cola).
- `data/agente2/meta_alertas.jsonl`: cada alerta una sola vez, con su evidencia.
- `data/agente2/veredictos.jsonl`: historial completo de veredictos humanos, nunca reescrito.

## Límites declarados

- Con pocos veredictos, la calibración demuestra el mecanismo pero no calibra: por eso exige
  `MUESTRA_MINIMA` con ambas clases y muestra el rango de empates.
- `UMBRAL_ESCALAR` / `UMBRAL_BLOQUEAR` tienen que coincidir con los del flujo; si no coinciden,
  la verificación de paridad lo delata.
- No re-mapea ATT&CK. Si el flujo reporta una técnica mal elegida, aparece tal cual.

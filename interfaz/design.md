# Design — CENTINELA · Panel del investigador

Sistema de diseño bloqueado de la interfaz. Todo módulo nuevo lee este archivo antes de escribir
código. No se regenera por módulo: si el sistema necesita crecer, se enmienda acá.

## Contexto

- **Proyecto**: CENTINELA, presentado al Hackatón Cyber.Ar 2026, eje *IA para la defensa de redes e
  infraestructura*. Detecta phishing por correo con un flujo n8n y dos agentes (identidad y aprendizaje).
- **Público**: analistas e investigadores de un CSIRT de la Fuerza; jurado técnico-militar.
- **Uso**: decidir y registrar un veredicto humano con evidencia verificable.
- **Tono**: técnico y austero. Un expediente de trabajo, no una demo de "hacker".
- **Identidad sin insignias**: el celeste da pertenencia nacional; no se usan escudos, logos ni
  marcas oficiales del Ejército o de la UNDEF.

## Genre

editorial, en registro técnico: filetes finos, jerarquía por peso y escala, sin tarjetas flotantes ni
sombras, asimetría a la izquierda.

## Macrostructure family

Todas las pantallas son pantallas de aplicación.

- **Base — Index-First.** La pantalla ES la lista de casos, con filetes entre filas. Cola y Reportes.
- **Map / Diagram**: permitido en Actores (grupos unidos por indicadores compartidos).
- **Stat-Led**: permitido en Métricas, Calibración y Aprendizaje, **sólo con cifras que devuelve la
  API**. Nunca una cifra inventada, redondeada a favor o sin fuente.

## Theme

Tema a medida. Vibe: *"expediente técnico, sala de situación, verificable, soberano"*.
Ejes: **light / display-condensed-bold / cool (celeste)**. Valores completos en `tokens.css`.

| Token | Expediente (claro, principal) | Guardia nocturna (oscuro) |
|---|---|---|
| `--color-paper` | `oklch(97% 0.008 240)` | `oklch(17% 0.012 240)` |
| `--color-paper-2` | `oklch(94% 0.010 240)` | `oklch(21% 0.014 240)` |
| `--color-ink` | `oklch(22% 0.014 245)` | `oklch(94% 0.008 240)` |
| `--color-ink-2` | `oklch(38% 0.014 245)` | `oklch(82% 0.010 240)` |
| `--color-muted` | `oklch(48% 0.012 245)` | `oklch(72% 0.012 240)` |
| `--color-rule` | `oklch(80% 0.012 240)` | `oklch(36% 0.012 240)` |
| `--color-accent` (celeste) | `oklch(58% 0.12 238)` | `oklch(70% 0.10 238)` |
| `--color-focus` | `oklch(52% 0.16 245)` | `oklch(76% 0.14 240)` |

El claro es el principal: se diferencia de los paneles oscuros habituales y se lee en un proyector.

### Señales de estado (enmienda al acento único)

Bloquear, Escalar y Entregar son **datos**, no decoración, y tienen tokens propios
(`--color-bloquear`, `--color-escalar`, `--color-entregar`). Reglas:

- nunca color solo: siempre **forma + palabra** (■ Bloquear · ▲ Escalar · ● Entregar);
- nunca como fondo de bloque: borde y texto del sello;
- contraste de texto ≥ 4,5:1 en los dos temas (verificado).

## Typography

- Display: **Big Shoulders Display**, 700–800, roman. Títulos de módulo, sellos y cifras.
- Body: **IBM Plex Sans**, 400/500/600.
- Mono: **IBM Plex Mono**, 400/500. IDs, hashes, IOCs, endpoints, técnicas ATT&CK y procedencia.
- Las tres familias van **empaquetadas con `@fontsource`**: el navegador del analista no le pide nada
  a terceros (misma regla de soberanía que los agentes, RG-05).
- Display en mayúsculas sólo en sellos y en la marca; los títulos de módulo en tipo oración.
- Cifras en columnas: `font-variant-numeric: tabular-nums`.

## Spacing

Escala de 4 pt con nombres (`--space-3xs` … `--space-3xl`). Ningún valor crudo en los estilos.

## Motion

- Sin librería. Sólo `opacity` y `transform`, 120–220 ms, `--ease-out`.
- Sin revelado al cargar, sin animaciones infinitas (ni anillos girando en estados vacíos).
- `prefers-reduced-motion`: todo movimiento se anula.

## Microinteractions stance

- Éxito silencioso: registrar un veredicto actualiza la fila; nada de brindis celebratorios.
- Foco visible e instantáneo (`:focus-visible`, anillo de 2 px con `--color-focus`).
- Todo control con sus 8 estados: reposo, hover, foco, activo, deshabilitado, cargando, error, éxito.
- Nada que sólo aparezca con hover.

## CTA voice

- Botones de texto con filete (sin píldoras, sin rellenos de acento), radio de 3 px, verbo concreto:
  *Actualizar*, *Registrar veredicto*, *Ver respuesta del agente*.
- La acción destructiva no existe en la interfaz: los veredictos son append-only.

## Firmas del sistema (lo que lo hace CENTINELA)

1. **Sellos de veredicto**: rectángulo con filete, forma + palabra en mayúsculas condensadas.
2. **Trama de incertidumbre**: rayado diagonal para *no verificable*, *muestra insuficiente* y vistas en
   preparación. Lo que no se sabe se ve distinto de lo que es cero.
3. **Procedencia en cada dato**: línea en monoespaciada con requerimiento, agente, endpoint y hora.
4. **Cadena de custodia**: el razonamiento de un agente se muestra como secuencia numerada de pasos.
5. **Colofón**: cierre en monoespaciada con contexto del torneo y la garantía de procesamiento local.

## Navegación y pie

- **Nav: N3 Side-rail** (izquierda, 17,5 rem, indicador numerado por orden de trabajo). Banda con la
  marca rotada. En pantallas angostas pasa a barra superior con botón *Módulos*.
- **Footer: Ft4 Dense typographic** (colofón en monoespaciada).
- Activo en la nav: banda `--color-accent-wash` + cuadrado celeste. Nunca franja lateral gruesa.

## Per-page allowances

- Ningún módulo usa ilustraciones, fotos ni fondos decorativos: la función carga la pantalla.
- Sin tarjetas dentro de tarjetas, sin sombras, sin transparencias como color, sin degradés de fondo.

## What pages MUST share

- Marca, riel lateral, cabecera de módulo (título + procedencia) y colofón.
- Tokens de `tokens.css`, las tres familias tipográficas, sellos y trama.

## What pages MAY differ on

- Macroestructura dentro de la familia (Index-First / Map-Diagram / Stat-Led, según el módulo).
- Densidad de la lista y columnas visibles.

## Exports

### tokens.css

Ver [`tokens.css`](tokens.css) en la raíz de `interfaz/` (fuente de verdad).

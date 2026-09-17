/** Formateo y convenciones de dominio compartidas por los módulos — RI-08. */

/** Fecha ISO a hora local legible. Si no parsea, se devuelve el original (más útil que "Invalid Date"). */
export function fmtTime(iso) {
  if (!iso) return ''
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString()
}

/** Número con precisión adaptada a su magnitud. */
export function fmtNumber(value) {
  if (value == null || Number.isNaN(value)) return '—'
  const magnitude = Math.abs(value)
  if (magnitude >= 1000) return Math.round(value).toLocaleString()
  if (magnitude >= 10) return value.toFixed(1)
  return value.toFixed(2)
}

/** Proporción 0-1 como porcentaje entero, con espacio fino antes del signo. */
export function fmtPct(value) {
  return value == null || Number.isNaN(value) ? '—' : `${Math.round(value * 100)} %`
}

/**
 * Los veredictos del flujo se muestran como ACCIONES, con forma + palabra (design.md § Señales).
 *
 * El flujo n8n usa VERDADERO_POSITIVO / ESCALAR / FALSO_POSITIVO como veredictos, pero TP/FP/FN
 * sólo existen al comparar contra el veredicto humano (así los calcula el crítico del Agente 2).
 * La interfaz no renombra el contrato del flujo: traduce al mostrar.
 */
export const ACCION = {
  VERDADERO_POSITIVO: { etiqueta: 'Bloquear', tono: 'bloquear', forma: 'cuadrado' },
  ESCALAR: { etiqueta: 'Escalar', tono: 'escalar', forma: 'triangulo' },
  FALSO_POSITIVO: { etiqueta: 'Entregar', tono: 'entregar', forma: 'circulo' },
}

export const ORDEN_ACCIONES = ['VERDADERO_POSITIVO', 'ESCALAR', 'FALSO_POSITIVO']

export function accion(veredicto) {
  return ACCION[veredicto] ?? { etiqueta: veredicto ?? 'Sin dato', tono: 'neutro', forma: 'anillo' }
}

/** Hora corta para la procedencia (HH:MM:SS). */
export function fmtHora(date) {
  return date ? date.toLocaleTimeString('es-AR', { hour12: false }) : '—'
}

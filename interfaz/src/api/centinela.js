import { getAgente1, getJson, postJson } from './client'

/**
 * Endpoints de CENTINELA — contrato con la API del Agente 2 (RA2-08) y el estado del Agente 1.
 *
 * Es la única lista de rutas del frontend: si la API cambia, se cambia acá. Los módulos piden
 * `api.cola()` y no saben de URLs.
 */
const id = (reportId) => encodeURIComponent(reportId)

export const api = {
  salud: () => getJson('/api/salud'),
  saludAgente1: () => getAgente1('/salud'),

  cola: () => getJson('/api/cola'),
  reportes: (veredicto) => getJson(`/api/reportes${veredicto ? `?veredicto=${encodeURIComponent(veredicto)}` : ''}`),
  reporte: (reportId) => getJson(`/api/reportes/${id(reportId)}`),
  registrarVeredicto: (reportId, { veredicto, analista, comentario = '' }, token) =>
    postJson(`/api/reportes/${id(reportId)}/veredicto`, { veredicto, analista, comentario }, token),

  metricas: () => getJson('/api/metricas'),
  supervision: () => getJson('/api/supervision'),
  actores: () => getJson('/api/actores'),
  attack: () => getJson('/api/attack'),
  navigator: () => getJson('/api/attack/navigator'),
  calibracion: () => getJson('/api/calibracion'),
  aprendizaje: () => getJson('/api/aprendizaje'),
}

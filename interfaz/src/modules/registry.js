import { api } from '../api/centinela'
import { ModuloPendiente } from '../components/ModuloPendiente'

/**
 * Módulos de la interfaz, en el orden del trabajo del investigador.
 *
 * Patrón de pro-inves-frontend: sumar un módulo es una entrada acá; barra lateral, encabezado y
 * ruteo se acomodan solos. Cada entrada declara:
 *   id / label / hint / icon — identidad en la barra
 *   title / subtitle         — encabezado al abrirlo
 *   requisitos               — qué requerimientos de docs/REQUERIMIENTOS.md cumple (id + criterio)
 *   endpoint / lectura       — el contrato con la API del Agente 2
 *   resumir                  — una línea que confirma que la respuesta tiene sentido
 *   Component                — la vista. Hoy todos usan ModuloPendiente; cada módulo lo reemplaza
 *                              por su componente sin tocar el resto de la entrada.
 */
export const MODULES = [
  {
    id: 'cola',
    label: 'Cola',
    hint: 'qué revisar primero',
    icon: '☰',
    title: 'Cola del investigador',
    subtitle: 'Correos sin veredicto humano, priorizados por el generador de problemas del Agente 2',
    requisitos: [{ id: 'RI-01', criterio: 'Cola priorizada con motivos (consume RA2-06).' }],
    endpoint: '/api/cola',
    lectura: api.cola,
    resumir: (d) => `${d.length} correo(s) sin veredicto humano`,
    Component: ModuloPendiente,
  },
  {
    id: 'reportes',
    label: 'Reportes',
    hint: 'detalle y veredicto',
    icon: '✉',
    title: 'Reportes del flujo',
    subtitle: 'Detalle de cada análisis y registro del veredicto humano',
    requisitos: [
      { id: 'RI-02', criterio: 'Detalle: acción final y de reglas, motivos, IA, puntaje por categoría, hallazgos, IOCs defanged, ATT&CK y aporte del Agente 1.' },
      { id: 'RI-03', criterio: 'Registro del veredicto humano con token, mostrando el historial.' },
    ],
    endpoint: '/api/reportes',
    lectura: () => api.reportes(),
    resumir: (d) => `${d.length} reporte(s), ${d.filter((r) => r.veredicto_humano).length} con veredicto humano`,
    Component: ModuloPendiente,
  },
  {
    id: 'metricas',
    label: 'Métricas',
    hint: 'crítico',
    icon: '▦',
    title: 'Métricas contra el veredicto humano',
    subtitle: 'Detección, bloqueo automático, costo, desacuerdos IA↔reglas y aporte del Agente 1',
    requisitos: [{ id: 'RI-04', criterio: 'Matriz de confusión, detección, costo, desacuerdos IA↔reglas, latencia.' }],
    endpoint: '/api/metricas',
    lectura: api.metricas,
    resumir: (d) => `${d.critica.n_etiquetados} de ${d.critica.n_reportes} reportes con veredicto humano`,
    Component: ModuloPendiente,
  },
  {
    id: 'supervision',
    label: 'Supervisión IA',
    hint: 'decisor del flujo',
    icon: '◉',
    title: 'Supervisión del decisor IA',
    subtitle: 'Degradaciones, guardrails, caídas y meta-alertas',
    requisitos: [{ id: 'RI-06', criterio: 'Meta-alertas y dimensiones del decisor IA.' }],
    endpoint: '/api/supervision',
    lectura: api.supervision,
    resumir: (d) => `${d.meta_alertas.length} meta-alerta(s) · degradación global ${Math.round((d.global.degradacion ?? 0) * 100)} %`,
    Component: ModuloPendiente,
  },
  {
    id: 'actores',
    label: 'Actores',
    hint: 'campañas',
    icon: '⌖',
    title: 'Actores y campañas',
    subtitle: 'Correos maliciosos agrupados por infraestructura compartida · sin atribución nominal',
    requisitos: [{ id: 'RI-09', criterio: 'Actores con vínculos, indicadores defanged, período, veredictos y técnicas del flujo (RA2-10).' }],
    endpoint: '/api/actores',
    lectura: api.actores,
    resumir: (d) => `${d.n_actores} actor(es), ${d.n_con_varios_reportes} con varios correos`,
    Component: ModuloPendiente,
  },
  {
    id: 'attack',
    label: 'ATT&CK',
    hint: 'mapeo del flujo',
    icon: '⬡',
    title: 'Técnicas MITRE ATT&CK',
    subtitle: 'Lo que reportó el flujo n8n, agregado · exportable a ATT&CK Navigator',
    requisitos: [{ id: 'RI-07', criterio: 'Técnicas agregadas y descarga de la capa Navigator.' }],
    endpoint: '/api/attack',
    lectura: api.attack,
    resumir: (d) => `${d.tecnicas.length} técnica(s) reportadas por el flujo`,
    Component: ModuloPendiente,
  },
  {
    id: 'calibracion',
    label: 'Calibración',
    hint: 'umbrales',
    icon: '⇅',
    title: 'Calibración de umbrales',
    subtitle: 'Propuesta del elemento de aprendizaje · no se aplica sola',
    requisitos: [{ id: 'RI-05', criterio: 'Umbrales actuales vs propuestos y curva de costo.' }],
    endpoint: '/api/calibracion',
    lectura: api.calibracion,
    resumir: (d) => `estado: ${d.estado} · ${d.n} veredicto(s) humano(s)`,
    Component: ModuloPendiente,
  },
  {
    id: 'aprendizaje',
    label: 'Aprendizaje',
    hint: 'evidencia',
    icon: '◈',
    title: 'Evidencia de aprendizaje',
    subtitle: 'Confianza aprendida sobre la IA y curva en casos reservados',
    requisitos: [{ id: 'RI-10', criterio: 'Confiabilidad de las degradaciones de la IA y curva de aprendizaje, indicando si es sintética o real (RA2-11, RA2-12).' }],
    endpoint: '/api/aprendizaje',
    lectura: api.aprendizaje,
    resumir: (d) => `IA: ${d.confiabilidad_degradacion_ia.estado} · curva real: ${d.evidencia_real.estado}`,
    Component: ModuloPendiente,
  },
]

export const DEFAULT_MODULE_ID = MODULES[0].id

import { useCallback } from 'react'
import { api } from '../api/centinela'
import { usePolling } from './usePolling'

/**
 * Estado de los dos agentes, leído por el shell — RI-08.
 *
 * Las dos lecturas son independientes a propósito, igual que los procesos reales: que el Agente 1
 * esté caído no impide trabajar con la cola del Agente 2, y viceversa. El shell sólo polea la
 * salud; cada módulo lee sus propios datos mientras está abierto, así diez módulos no generan
 * diez lecturas cada diez segundos.
 */
export function useSalud() {
  const agente2 = usePolling(useCallback(() => api.salud(), []))
  const agente1 = usePolling(useCallback(() => api.saludAgente1(), []))
  return {
    agente2: { ...agente2, live: vivo(agente2) },
    agente1: { ...agente1, live: vivo(agente1) },
  }
}

/** neutro = todavía no se leyó; ok = la última lectura salió bien; err = falló. */
export function vivo({ error, lastUpdated }) {
  if (error) return 'err'
  return lastUpdated ? 'ok' : 'idle'
}

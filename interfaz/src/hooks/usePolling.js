import { useCallback, useEffect, useRef, useState } from 'react'
import { REFRESH_MS } from '../api/client'

/**
 * Polling con refresco manual — portado de pro-inves-frontend (RI-08).
 *
 * Tres decisiones que se conservan a propósito:
 *
 *  1. **El dato viejo sobrevive al error.** Si un refresco falla, se muestra el banner pero
 *     NO se borra lo último que se leyó bien. Vaciar la pantalla ante un corte de red haría
 *     parecer que la cola quedó vacía, que es exactamente lo contrario de lo que pasó.
 *  2. **`lastUpdated` se sella siempre**, haya salido bien o mal, porque responde "¿cuándo
 *     fue el último intento?" — que es lo que un operador mira para saber si el panel está
 *     vivo.
 *  3. **Refresco inmediato al montar**, y recién después el intervalo.
 *
 * @param {() => Promise<any>} fetcher lectura a repetir; debe ser estable (useCallback)
 * @param {{enabled?: boolean, intervalMs?: number}} options
 */
export function usePolling(fetcher, { enabled = true, intervalMs = REFRESH_MS } = {}) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)
  const [loading, setLoading] = useState(true)

  // El fetcher se guarda en una ref para que el intervalo no se reprograme cuando el
  // llamador reconstruye la función: reprogramarlo reiniciaría el reloj en cada render y el
  // refresco real nunca ocurriría en un componente que renderiza seguido.
  //
  // Se sincroniza en un efecto y no durante el render porque escribir una ref mientras se
  // renderiza es un efecto secundario: con StrictMode o con render concurrente, el render
  // puede descartarse y la ref quedaría apuntando a una versión que nunca se montó. El valor
  // inicial ya lo pone `useRef`, así que el primer ciclo tiene el fetcher correcto igual.
  const fetcherRef = useRef(fetcher)
  useEffect(() => {
    fetcherRef.current = fetcher
  }, [fetcher])

  // Evita que una respuesta lenta de un fetch ya obsoleto pise a una posterior.
  const runIdRef = useRef(0)

  const refresh = useCallback(async () => {
    const runId = ++runIdRef.current
    try {
      const result = await fetcherRef.current()
      if (runId !== runIdRef.current) return
      setData(result)
      setError(null)
    } catch (err) {
      if (runId !== runIdRef.current) return
      setError(err)
    } finally {
      if (runId === runIdRef.current) {
        setLoading(false)
        setLastUpdated(new Date())
      }
    }
  }, [])

  useEffect(() => {
    if (!enabled) return undefined
    refresh()
    const timer = setInterval(refresh, intervalMs)
    return () => clearInterval(timer)
  }, [enabled, intervalMs, refresh])

  return { data, error, lastUpdated, loading, refresh }
}

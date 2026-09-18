import { useCallback, useEffect, useState } from 'react'

/** Clave propia de CENTINELA: no hereda la preferencia de otro panel del mismo origen. */
const STORAGE_KEY = 'centinela-tema'

/**
 * Tema dark/light persistido, aplicado como `data-theme` en el `<html>`.
 *
 * Se escribe en el elemento raíz y no en un contexto de React porque las variables de color
 * viven en CSS (`[data-theme="light"] { ... }`). Que el estado lo lleve React y el efecto lo
 * aplique el DOM mantiene una sola fuente de verdad para el color: la hoja de estilos.
 */
export function useTheme() {
  const [theme, setTheme] = useState(() => {
    try {
      // Expediente (claro) es el tema principal (design.md § Theme); la guardia nocturna es opcional.
      return localStorage.getItem(STORAGE_KEY) === 'dark' ? 'dark' : 'light'
    } catch {
      // Modo privado o storage bloqueado: el tema deja de recordarse, no de funcionar.
      return 'light'
    }
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    try {
      localStorage.setItem(STORAGE_KEY, theme)
    } catch {
      /* sin persistencia; el tema vale para esta sesión */
    }
  }, [theme])

  const toggle = useCallback(
    () => setTheme((current) => (current === 'light' ? 'dark' : 'light')),
    [],
  )

  return { theme, toggle }
}

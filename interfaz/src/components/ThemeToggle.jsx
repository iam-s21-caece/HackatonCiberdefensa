/**
 * Cambio de tema: botón de texto dentro del riel (no un botón flotante con emoji).
 * Dice a qué tema lleva, no cuál está activo: el verbo es la acción.
 *
 * @param {{theme: 'light'|'dark', onToggle: () => void}} props
 */
export function ThemeToggle({ theme, onToggle }) {
  // Rótulo corto a propósito: un botón nunca se parte en dos líneas (el riel mide 13 rem útiles).
  const destino = theme === 'dark' ? 'claro' : 'oscuro'
  return (
    <button
      type="button"
      className="boton boton--compacto"
      onClick={onToggle}
      title={theme === 'dark' ? 'Tema expediente' : 'Tema guardia nocturna'}
    >
      Usar tema {destino}
    </button>
  )
}

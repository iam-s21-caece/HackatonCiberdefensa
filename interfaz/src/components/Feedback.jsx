/**
 * Los dos estados que no son "hay datos": el error y el vacío.
 * Si falló la lectura, aviso con el motivo real; si salió bien y no había nada, un vacío quieto
 * (el agente está vigilando, no roto). Sin animaciones infinitas.
 */

/** @param {{error: Error & {status?: number}, hint?: string}} props */
export function Banner({ error, hint }) {
  if (!error) return null
  const detalle = error.status ? `HTTP ${error.status} · ${error.message}` : error.message || 'sin conexión'
  return (
    <div className="aviso" role="alert">
      <p className="aviso__titulo">El agente no respondió ({detalle}).</p>
      {hint && <p className="aviso__pista">{hint}</p>}
    </div>
  )
}

/** @param {{message: string, detail?: string}} props */
export function EmptyState({ message, detail }) {
  return (
    <div className="vacio">
      <p>{message}</p>
      {detail && <p className="vacio__detalle">{detail}</p>}
    </div>
  )
}

/**
 * Franja de resumen. La comparten los dos módulos.
 *
 * Es el mismo componente para alertas y para aprendizaje porque la franja del dashboard
 * original ya era genérica: una grilla de valor + rótulo con un filo de color opcional. Lo
 * único que cambia entre módulos son las cifras, y esas las deriva cada módulo de sus propios
 * datos — nunca de un endpoint aparte, para que el resumen no pueda contradecir a la lista
 * que tiene debajo.
 *
 * @param {{items: Array<{key: string, value: number|string, label: string, tone?: string, title?: string}>}} props
 */
export function StatStrip({ items }) {
  return (
    <section className="stats">
      {items.map((item) => (
        <div
          key={item.key}
          className={`stat${item.tone ? ` sev-${item.tone}` : ''}`}
          title={item.title}
        >
          <span className="stat-value">{item.value}</span>
          <span className="stat-label">{item.label}</span>
        </div>
      ))}
    </section>
  )
}

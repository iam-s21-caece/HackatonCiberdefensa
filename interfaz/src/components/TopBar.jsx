import { fmtHora } from '../utils/format'

/**
 * Cabecera del módulo: título, bajada y línea de procedencia — RI-08.
 *
 * La procedencia es una firma del sistema: dice qué requerimiento cumple el módulo, de qué agente y
 * endpoint sale el dato, y cuándo se leyó por última vez. Va DEBAJO del título, nunca como etiqueta
 * al costado.
 *
 * @param {{title: string, subtitle: string, requisitos: string[], endpoint: string,
 *          live: 'idle'|'ok'|'err', lastUpdated: Date|null, onRefresh?: () => void}} props
 */
export function TopBar({ title, subtitle, requisitos, endpoint, live, lastUpdated, onRefresh }) {
  const estado = live === 'ok' ? 'agente en línea' : live === 'err' ? 'agente sin respuesta' : 'leyendo'

  return (
    <header className="cabecera">
      <h1 className="cabecera__titulo">{title}</h1>
      <p className="cabecera__bajada">{subtitle}</p>
      <div className="cabecera__pie">
        <p className="procedencia">
          <span>{requisitos.join(' · ')}</span>
          <span className="procedencia__sep" aria-hidden="true">/</span>
          <span>Agente 2 · GET {endpoint}</span>
          <span className="procedencia__sep" aria-hidden="true">/</span>
          <span className="num">leído {fmtHora(lastUpdated)}</span>
        </p>
        <span className={`estado estado--${live}`}>{estado}</span>
        {onRefresh && (
          <button type="button" className="boton boton--compacto" onClick={onRefresh}>
            Actualizar
          </button>
        )}
      </div>
    </header>
  )
}

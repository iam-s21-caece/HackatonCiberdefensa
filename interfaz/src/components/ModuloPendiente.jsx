import { useCallback } from 'react'
import { usePolling } from '../hooks/usePolling'
import { ORDEN_ACCIONES } from '../utils/format'
import { Banner } from './Feedback'
import { Sello } from './Sello'

/**
 * Ficha de un módulo todavía no construido.
 *
 * No es decorativa: declara qué requerimiento va a cumplir el módulo, qué endpoint consume, y
 * VERIFICA en vivo que ese endpoint responde. La banda rayada es la trama de incertidumbre del
 * sistema: la vista todavía no existe, y eso se ve distinto de un dato vacío.
 *
 * Si la respuesta es una lista de reportes, muestra el desglose REAL por acción del flujo con los
 * sellos del sistema. Ninguna cifra sale de acá: todas vienen del agente.
 *
 * Declarar un módulo acá no lo implementa: `scripts/trazabilidad.py` no cuenta este componente ni
 * el registro como implementación de un RI.
 *
 * @param {{modulo: {title: string, requisitos: Array<{id: string, criterio: string}>,
 *          endpoint: string, lectura: () => Promise<any>, resumir: (data: any) => string}}} props
 */
export function ModuloPendiente({ modulo }) {
  const lectura = usePolling(useCallback(() => modulo.lectura(), [modulo]))
  const crudo = lectura.data ? JSON.stringify(lectura.data, null, 2) : ''
  const desglose = desglosePorAccion(lectura.data)
  const live = lectura.error ? 'err' : lectura.data ? 'ok' : 'idle'

  return (
    <section className="ficha" aria-labelledby={`ficha-${modulo.endpoint}`}>
      <p className="ficha__banda trama">Vista en preparación · el contrato con el agente ya está verificado</p>

      <div className="ficha__cuerpo">
        <div className="ficha__seccion">
          <h2 className="ficha__titulo" id={`ficha-${modulo.endpoint}`}>
            Qué va a cumplir
          </h2>
          <ul className="requisitos">
            {modulo.requisitos.map((req) => (
              <li key={req.id} className="requisito">
                <code className="requisito__id">{req.id}</code>
                <span>{req.criterio}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="ficha__seccion">
          <h2 className="ficha__titulo">Qué responde el agente</h2>
          <div className="contrato">
            <p className="contrato__endpoint">GET {modulo.endpoint}</p>
            <span className={`estado estado--${live}`}>
              {live === 'ok' ? 'responde' : live === 'err' ? 'sin respuesta' : 'leyendo'}
            </span>
            {lectura.data && <p className="contrato__resumen">{modulo.resumir(lectura.data)}</p>}
          </div>

          {desglose && (
            <ul className="desglose" aria-label="Acción del flujo por correo">
              {ORDEN_ACCIONES.map((v) => (
                <li key={v} className="desglose__item">
                  <span className="desglose__cifra">{desglose[v] ?? 0}</span>
                  <Sello veredicto={v} />
                </li>
              ))}
            </ul>
          )}

          <Banner error={lectura.error} hint="Revisá que el Agente 2 esté levantado (interfaz/README.md)." />

          {crudo && (
            <details className="crudo">
              <summary>Ver respuesta del agente ({Math.max(1, Math.round(crudo.length / 1024))} KB)</summary>
              <pre>{crudo.length > 6000 ? `${crudo.slice(0, 6000)}\n…` : crudo}</pre>
            </details>
          )}
        </div>
      </div>
    </section>
  )
}

/** Cuenta reportes por acción del flujo, sólo si la respuesta es una lista de reportes. */
function desglosePorAccion(data) {
  if (!Array.isArray(data) || !data.length || !('veredicto_final' in data[0])) return null
  return data.reduce((cuenta, r) => ({ ...cuenta, [r.veredicto_final]: (cuenta[r.veredicto_final] ?? 0) + 1 }), {})
}

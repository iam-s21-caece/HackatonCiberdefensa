import { accion } from '../utils/format'

/**
 * Sello de veredicto — firma del sistema (design.md § Firmas).
 *
 * Forma + palabra + color de estado: se lee en blanco y negro, en un proyector lavado y con
 * daltonismo. El color refuerza; nunca es la única señal.
 *
 * @param {{veredicto: string}} props valor del flujo (VERDADERO_POSITIVO | ESCALAR | FALSO_POSITIVO)
 */
export function Sello({ veredicto }) {
  const a = accion(veredicto)
  return (
    <span className={`sello sello--${a.tono}`}>
      <span className="sello__forma" data-forma={a.forma} aria-hidden="true" />
      {a.etiqueta}
    </span>
  )
}

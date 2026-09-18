import { useState } from 'react'
import { MODULES } from '../modules/registry'
import { ThemeToggle } from './ThemeToggle'

/**
 * Riel lateral (Hallmark N3 · izquierda · numerado) — RI-08.
 *
 * Numerado porque el orden ES el flujo de trabajo del investigador (revisar la cola primero,
 * aprender al final). Cada ítem es una sola línea: un enlace de navegación nunca se parte en dos
 * (Hallmark gate 49); la pista del módulo queda como `title`. Desde 60 rem queda fijo con la marca rotada en su banda; en pantallas
 * angostas es una barra superior con el botón Módulos.
 *
 * El estado de los agentes vive acá y no en la cabecera porque es del sistema, no del módulo
 * abierto: quien mira ATT&CK tiene que ver igual que el Agente 1 se cayó.
 *
 * @param {{
 *   activeId: string,
 *   onSelect: (id: string) => void,
 *   cuentas: Record<string, number|null>,
 *   agentes: Array<{nombre: string, live: 'idle'|'ok'|'err', estado: string, detalle: string}>,
 *   theme: 'light'|'dark', onToggleTheme: () => void,
 * }} props
 */
export function Sidebar({ activeId, onSelect, cuentas = {}, agentes = [], theme, onToggleTheme }) {
  const [abierto, setAbierto] = useState(false)

  const elegir = (id) => {
    onSelect(id)
    setAbierto(false)
  }

  return (
    <nav className="riel" aria-label="Módulos" data-abierto={abierto}>
      <p className="riel__marca-banda" aria-hidden="true">
        Centinela
      </p>

      <div className="riel__cuerpo">
        <div className="riel__cabeza">
          <div className="marca">
            <p className="marca__nombre">Centinela</p>
            <p className="marca__contexto">
              Hackatón Cyber.Ar 2026
              <br />
              IA para la defensa de redes e infraestructura
            </p>
          </div>
          <button
            type="button"
            className="boton boton--compacto riel__boton-menu"
            aria-expanded={abierto}
            aria-controls="riel-lista"
            onClick={() => setAbierto((v) => !v)}
          >
            {abierto ? 'Cerrar' : 'Módulos'}
          </button>
        </div>

        <ol className="riel__lista" id="riel-lista">
          {MODULES.map((module, index) => {
            const activo = module.id === activeId
            const cuenta = cuentas[module.id]
            return (
              <li key={module.id}>
                <button
                  type="button"
                  className="riel__item"
                  title={module.hint}
                  onClick={() => elegir(module.id)}
                  aria-current={activo ? 'page' : undefined}
                >
                  <span className="riel__num" aria-hidden="true">
                    {String(index + 1).padStart(2, '0')}
                  </span>
                  <span className="riel__label">{module.label}</span>
                  {cuenta != null && (
                    <span className="riel__cuenta" aria-label={`${cuenta} pendientes`}>
                      {cuenta}
                    </span>
                  )}
                </button>
              </li>
            )
          })}
        </ol>

        <div className="riel__pie">
          {agentes.map((agente) => (
            <p key={agente.nombre} className="agente" title={agente.detalle}>
              <span>{agente.nombre}</span>
              <span className={`estado estado--${agente.live}`}>{agente.estado}</span>
            </p>
          ))}
          <ThemeToggle theme={theme} onToggle={onToggleTheme} />
        </div>
      </div>
    </nav>
  )
}

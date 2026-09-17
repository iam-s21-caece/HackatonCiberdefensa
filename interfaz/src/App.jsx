import { useCallback, useState } from 'react'
import { Sidebar } from './components/Sidebar'
import { TopBar } from './components/TopBar'
import { usePolling } from './hooks/usePolling'
import { useSalud } from './hooks/useSalud'
import { useTheme } from './hooks/useTheme'
import { DEFAULT_MODULE_ID, MODULES } from './modules/registry'
import './App.css'

/**
 * Shell de la interfaz de CENTINELA — RI-08. Sistema de diseño: interfaz/design.md.
 *
 * El shell decide QUÉ se muestra; los módulos deciden CÓMO. No hay lógica de negocio acá.
 *
 * Sin pantalla de ingreso: un login que no valida nada sugiere una seguridad que no existe. La
 * única operación que escribe (el veredicto humano) exige el token del Agente 2; cómo se
 * autentica al analista es una decisión pendiente del proyecto.
 */
export default function App() {
  const { theme, toggle } = useTheme()
  const [activeId, setActiveId] = useState(DEFAULT_MODULE_ID)
  const salud = useSalud()

  const active = MODULES.find((module) => module.id === activeId) ?? MODULES[0]
  // La cabecera muestra cuándo se leyó el dato del módulo abierto, no la salud del sistema.
  const lecturaModulo = usePolling(useCallback(() => active.lectura(), [active]))

  const s2 = salud.agente2.data
  const pendientes = s2 ? s2.reportes - s2.etiquetados : null

  const agentes = [
    {
      nombre: 'Agente 1 · identidad',
      live: salud.agente1.live,
      estado: textoEstado(salud.agente1.live),
      detalle: salud.agente1.error
        ? `No responde: ${salud.agente1.error.message}`
        : salud.agente1.data
          ? `MX de confianza: ${salud.agente1.data.organizacion.mx_confiables.join(', ') || 'ninguno'}`
          : 'leyendo',
    },
    {
      nombre: 'Agente 2 · aprendizaje',
      live: salud.agente2.live,
      estado: textoEstado(salud.agente2.live),
      detalle: salud.agente2.error
        ? `No responde: ${salud.agente2.error.message}`
        : s2
          ? `${s2.reportes} reportes · ${s2.etiquetados} con veredicto · escritura ${s2.escritura_habilitada ? 'habilitada' : 'deshabilitada'}`
          : 'leyendo',
    },
  ]

  return (
    <div className="shell">
      <Sidebar
        activeId={active.id}
        onSelect={setActiveId}
        cuentas={{ cola: pendientes }}
        agentes={agentes}
        theme={theme}
        onToggleTheme={toggle}
      />

      <main className="trabajo">
        <TopBar
          title={active.title}
          subtitle={active.subtitle}
          requisitos={active.requisitos.map((r) => r.id)}
          endpoint={active.endpoint}
          live={lecturaModulo.error ? 'err' : lecturaModulo.lastUpdated ? 'ok' : 'idle'}
          lastUpdated={lecturaModulo.lastUpdated}
          onRefresh={lecturaModulo.refresh}
        />

        {/* `key` remonta el módulo al cambiar: cada uno arranca su propia lectura desde cero. */}
        <active.Component key={active.id} modulo={active} />

        <footer className="colofon">
          CENTINELA — proyecto para el Hackatón Cyber.Ar 2026, eje IA para la defensa de redes e infraestructura.
          Correos analizados por el flujo n8n; identidad del remitente verificada por el Agente 1; veredictos,
          métricas y actores del Agente 2. Procesamiento local: ni los correos ni los veredictos salen de la
          infraestructura propia, y esta interfaz no le pide recursos a terceros. Los reportes del flujo se leen en
          solo lectura; el único dato que se escribe desde acá es el veredicto humano, con token.
        </footer>
      </main>
    </div>
  )
}

function textoEstado(live) {
  return live === 'ok' ? 'en línea' : live === 'err' ? 'sin respuesta' : 'leyendo'
}

/**
 * Transporte HTTP de la interfaz — RI-08.
 *
 * Un solo lugar decide cómo se arma la URL, cómo se evita la caché y cómo se tipa un error. Los
 * adaptadores (centinela.js) sólo nombran endpoints; no vuelven a resolver nada de esto.
 */

/** Vacío = rutas relativas, que resuelven el proxy de Vite (dev) o nginx (contenedor). */
const API_BASE = import.meta.env.VITE_API_BASE ?? ''
const AGENTE1_BASE = import.meta.env.VITE_AGENTE1_BASE ?? '/agente1'

export const REFRESH_MS = Number(import.meta.env.VITE_REFRESH_MS) || 10000

/**
 * Error de red o de protocolo con el status a la vista.
 * status 0 = no hubo respuesta (agente caído, proxy sin destino). El resto, el código HTTP; el
 * `detail` de FastAPI viaja en el mensaje para que el banner diga el motivo real.
 */
export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function pedir(url, opciones = {}) {
  let response
  try {
    const sep = url.includes('?') ? '&' : '?'
    const destino = opciones.method && opciones.method !== 'GET' ? url : `${url}${sep}t=${Date.now()}`
    response = await fetch(destino, { cache: 'no-store', ...opciones })
  } catch (cause) {
    throw new ApiError(cause.message || 'sin conexión', 0)
  }
  if (!response.ok) {
    let detalle = `HTTP ${response.status}`
    try {
      const cuerpo = await response.json()
      if (cuerpo?.detail) detalle = typeof cuerpo.detail === 'string' ? cuerpo.detail : JSON.stringify(cuerpo.detail)
    } catch {
      /* respuesta sin JSON: queda el código */
    }
    throw new ApiError(detalle, response.status)
  }
  try {
    return await response.json()
  } catch {
    // Típico de un proxy mal enrutado: devuelve el index.html de la SPA con 200 en vez del agente.
    throw new ApiError('la respuesta no es JSON (¿ruta del proxy?)', response.status)
  }
}

/** GET de la API del Agente 2. */
export function getJson(path) {
  return pedir(`${API_BASE}${path}`)
}

/** GET del estado del Agente 1 (única ruta suya expuesta a la interfaz). */
export function getAgente1(path) {
  return pedir(`${AGENTE1_BASE}${path}`)
}

/**
 * POST autenticado. El token NO se guarda en este módulo: lo provee quien llama, así la decisión
 * de dónde vive (memoria, sesión, proveedor de identidad) queda en un solo lugar de la interfaz.
 */
export function postJson(path, body, token) {
  return pedir(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify(body),
  })
}

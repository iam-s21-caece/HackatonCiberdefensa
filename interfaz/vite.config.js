import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

/**
 * Proxy de desarrollo hacia los agentes — RI-08.
 *
 * El navegador aplica same-origin, así que la interfaz nunca habla directo con los agentes: pide
 * `/api/...` y `/agente1/salud` a su propio origen y el proxy los enruta. En producción hace lo
 * mismo nginx (nginx/default.conf.template), con las MISMAS rutas: el frontend no tiene una sola
 * URL absoluta adentro.
 *
 *   /api/*          -> Agente 2 (aprendizaje), que ya sirve bajo /api. Es la API de la interfaz.
 *   /agente1/salud  -> Agente 1 (identidad), sólo su estado. Nada más del Agente 1 se expone:
 *                      su /analizar es para el flujo n8n, no para el navegador.
 */
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const agente2 = env.VITE_AGENTE2_TARGET || 'http://localhost:8102'
  const agente1 = env.VITE_AGENTE1_TARGET || 'http://localhost:8101'

  return {
    plugins: [react()],
    server: {
      proxy: {
        '/api': { target: agente2, changeOrigin: true },
        // El query string es parte de la ruta que ve el proxy (el cliente agrega ?t= para evitar caché).
        '^/agente1/salud(\\?.*)?$': {
          target: agente1,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/agente1/, ''),
        },
      },
    },
  }
})

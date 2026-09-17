// =====================================================================
//  NODO: Agente 1 · identidad del remitente (servicio externo)
//  Envía la salida de "Desarmar correo" (y el .eml crudo si llegó por el webhook) al Agente 1,
//  que recalcula SPF/DKIM/DMARC en vez de leerlos de las cabeceras. Devuelve el mismo formato que
//  los demás analizadores. Si el agente no responde, sale "con_error" sin hallazgos y el flujo
//  decide igual que sin él.
// =====================================================================
const d = $input.first().json;
const F = 'agente_identidad';

let raw = null;
try {
  const b = $('Webhook: recibir correo').first().json.body;
  raw = typeof b === 'string' ? b : (b && (b.raw || b.eml)) || null;
} catch (e) { raw = null; } // entrada por IMAP: no hay .eml crudo

let base = 'http://host.docker.internal:8101';
try { if ($env.AGENTE1_URL) base = $env.AGENTE1_URL; } catch (e) { /* acceso a $env bloqueado: se usa el valor por defecto */ }

const r = await httpJson({ method: 'POST', url: String(base).replace(/\/$/, '') + '/analizar', body: { parseado: d, raw_eml: raw }, timeout: 8000 });
if (r.ok && r.data && r.data.fuente === F) return [{ json: r.data }];
return salida(F, 'con_error', {}, [], { nota: 'Agente 1 no disponible: ' + (r.error || ('HTTP ' + r.status)) });

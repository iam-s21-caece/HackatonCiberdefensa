// =====================================================================
//  CENTINELA - utilidades compartidas
//  (build_workflow.py inyecta este bloque al inicio de cada nodo Code)
// =====================================================================
const __helpers = this.helpers;

// Límite de artefactos por tipo que se consultan a cada fuente externa
// (VirusTotal free = 4 req/min; evitamos quemar la cuota en un solo correo)
const LIM = { ips: 5, dominios: 6, urls: 6, hashes: 5 };

// Marcas frecuentemente suplantadas en Argentina + institucionales
const MARCAS = ['mercadopago', 'mercadolibre', 'galicia', 'santander', 'bbva', 'banconacion', 'bna', 'macro',
  'afip', 'arca', 'anses', 'pami', 'correoargentino', 'andreani', 'oca', 'microsoft', 'office365', 'outlook',
  'google', 'gmail', 'apple', 'icloud', 'netflix', 'paypal', 'dhl', 'fedex', 'whatsapp', 'facebook', 'instagram',
  'ejercito', 'fuerzasarmadas', 'mindef', 'argentina', 'gob', 'armada', 'fuerzaaerea', 'gendarmeria', 'prefectura'];

// Sufijos de segundo nivel: para que "mail.ejercito.mil.ar" -> "ejercito.mil.ar"
const SLD2 = new Set(['com.ar', 'gob.ar', 'gov.ar', 'mil.ar', 'org.ar', 'net.ar', 'edu.ar', 'tur.ar', 'int.ar',
  'co.uk', 'org.uk', 'ac.uk', 'gov.uk', 'com.br', 'gov.br', 'com.mx', 'gob.mx', 'com.co', 'gov.co', 'com.pe', 'gob.pe',
  'com.uy', 'gub.uy', 'com.cl', 'gob.cl', 'com.au', 'co.jp', 'co.nz', 'com.es', 'com.ve', 'gob.ve', 'com.bo', 'gob.bo',
  'com.py', 'gov.py', 'com.ec', 'gob.ec', 'co.za', 'com.tr', 'com.cn', 'co.in']);

// Proveedores gratuitos: no se enriquecen como "infraestructura" (crt.sh/RDAP/DNS) porque sólo meten ruido
const FREEMAIL = new Set(['gmail.com', 'googlemail.com', 'outlook.com', 'hotmail.com', 'hotmail.com.ar', 'live.com', 'msn.com', 'yahoo.com', 'yahoo.com.ar',
  'ymail.com', 'protonmail.com', 'proton.me', 'icloud.com', 'me.com', 'aol.com', 'gmx.com', 'gmx.net', 'mail.com', 'yandex.com', 'yandex.ru', 'zoho.com', 'fibertel.com.ar', 'speedy.com.ar', 'arnet.com.ar']);
function esFreemail(d) { return FREEMAIL.has(String(d || '').toLowerCase()); }

// User-Agent explícito: rdap.org y otros devuelven 403 al UA por defecto de Node
const UA = { 'User-Agent': 'CENTINELA-phishing-analyzer/1.0 (+hackathon ciberdefensa)' };

function registrable(host) {
  const p = String(host || '').toLowerCase().replace(/\.$/, '').split('.').filter(Boolean);
  if (p.length <= 2) return p.join('.');
  const last2 = p.slice(-2).join('.');
  if (SLD2.has(last2) && p.length >= 3) return p.slice(-3).join('.');
  return last2;
}

// Parser de URL propio: el sandbox del runner de n8n NO expone la clase global URL
function parseUrl(u) {
  const m = /^([a-z][a-z0-9+.-]*):\/\/(?:([^@\/?#]*)@)?(\[[^\]]*\]|[^:\/?#]+)(?::(\d+))?([^?#]*)(\?[^#]*)?(#.*)?$/i.exec(String(u || '').trim());
  if (!m) return null;
  return { protocol: m[1].toLowerCase() + ':', username: m[2] ? m[2].split(':')[0] : '', hostname: m[3].toLowerCase().replace(/^\[|\]$/g, ''),
    port: m[4] || '', pathname: m[5] || '/', search: m[6] || '', hash: m[7] || '' };
}

// Códigos de país E.164 (los de 3 dígitos primero para que el prefijo más largo gane)
const PAISES = [['598', 'Uruguay'], ['595', 'Paraguay'], ['591', 'Bolivia'], ['593', 'Ecuador'], ['380', 'Ucrania'], ['234', 'Nigeria'],
  ['972', 'Israel'], ['971', 'Emiratos Árabes'], ['966', 'Arabia Saudita'], ['54', 'Argentina'], ['55', 'Brasil'], ['56', 'Chile'],
  ['57', 'Colombia'], ['58', 'Venezuela'], ['51', 'Perú'], ['52', 'México'], ['53', 'Cuba'], ['34', 'España'], ['44', 'Reino Unido'],
  ['49', 'Alemania'], ['33', 'Francia'], ['39', 'Italia'], ['48', 'Polonia'], ['90', 'Turquía'], ['91', 'India'], ['92', 'Pakistán'],
  ['86', 'China'], ['84', 'Vietnam'], ['62', 'Indonesia'], ['63', 'Filipinas'], ['27', 'Sudáfrica'], ['20', 'Egipto'],
  ['7', 'Rusia/Kazajistán'], ['1', 'EE.UU./Canadá']];

// Analiza un remitente de WhatsApp/SMS: número E.164, código corto o ID alfanumérico
function parseTelefono(n, paisPropio, numerosPropios) {
  const s = String(n || '').trim().replace(/^whatsapp:/i, '');
  const digitos = s.replace(/\D/g, '');
  const alfanumerico = /[a-z]/i.test(s);
  const e164 = /^\+\d{7,15}$/.test(s) || /^00\d{7,15}$/.test(s);
  let codigo_pais = null, pais = null;
  if (!alfanumerico && (e164 || digitos.length >= 10)) {
    const dd = digitos.replace(/^00/, '');
    for (const [code, nombre] of PAISES) if (dd.startsWith(code)) { codigo_pais = code; pais = nombre; break; }
  }
  const propio = (numerosPropios || []).some(p => p && (p === digitos || (digitos.endsWith(p) && p.length >= 8) || p.toLowerCase() === s.toLowerCase()));
  return { original: s, digitos, alfanumerico, e164, codigo_corto: !alfanumerico && digitos.length > 0 && digitos.length <= 6,
    codigo_pais, pais, extranjero: codigo_pais ? codigo_pais !== String(paisPropio || '54') : null, movil_ar: codigo_pais === '54' && /^549/.test(digitos), propio };
}

function esIp(s) { return /^\d{1,3}(\.\d{1,3}){3}$/.test(String(s || '')); }

function esIpPrivada(ip) {
  const p = String(ip).split('.').map(Number);
  if (p.length !== 4 || p.some(n => isNaN(n) || n > 255)) return true;
  return p[0] === 10 || p[0] === 127 || p[0] === 0 || p[0] >= 224 ||
    (p[0] === 172 && p[1] >= 16 && p[1] <= 31) || (p[0] === 192 && p[1] === 168) ||
    (p[0] === 169 && p[1] === 254) || (p[0] === 100 && p[1] >= 64 && p[1] <= 127);
}

// IOC "defanged": hxxp://ejemplo[.]com  (no clickeable en tickets / chats del SOC)
function defang(s) { return String(s || '').replace(/http/gi, 'hxxp').replace(/\./g, '[.]'); }

// Hallazgo normalizado. severidad: info | baja | media | alta | critica. peso: aporte al score 0-100
function H(categoria, tipo, valor, severidad, peso, detalle, fuente) {
  return { categoria, tipo, valor: String(valor == null ? '' : valor), severidad, peso, detalle, fuente };
}

// HTTP tolerante: nunca lanza excepción, devuelve { ok, status, data, error }
async function httpJson(opts) {
  try {
    const res = await __helpers.httpRequest(Object.assign(
      { json: true, timeout: 20000, returnFullResponse: true, ignoreHttpStatusErrors: true }, opts));
    let data = res.body;
    if (typeof data === 'string') { try { data = JSON.parse(data); } catch (e) { /* respuesta de texto */ } }
    return { ok: res.statusCode >= 200 && res.statusCode < 300, status: res.statusCode, data };
  } catch (e) {
    return { ok: false, status: 0, error: String((e && e.message) || e) };
  }
}

function salida(fuente, estado, resultados, hallazgos, extra) {
  return [{ json: Object.assign({ fuente, estado, resultados, hallazgos, n_hallazgos: hallazgos.length }, extra || {}) }];
}

function uniq(arr) { return Array.from(new Set(arr.filter(Boolean))); }
// =====================================================================

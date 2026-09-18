// =====================================================================
//  NODO: Desarmar correo
//  Recibe el correo (webhook JSON, .eml crudo o IMAP) y lo "desmiembra"
//  en piezas analizables: cabeceras, autenticación, IPs, dominios, URLs,
//  adjuntos (con hashes), cuerpo. Todo lo que sigue trabaja sobre esto.
// =====================================================================
const item = $input.first();
const j = item.json || {};
const notas = [];

// ---------- configuración (viene del nodo "Configuración") ----------
const cfg = {
  vt_api_key: j.vt_api_key || '',
  abuseipdb_api_key: j.abuseipdb_api_key || '',
  abusech_api_key: j.abusech_api_key || '',
  ollama_url: (j.ollama_url || 'http://ollama:11434').replace(/\/$/, ''),
  ollama_model: j.ollama_model || 'llama3.2:3b',
  // IA_PROVEEDOR: ollama | deepseek | auto (DeepSeek si DEEPSEEK_API_KEY está definida). La key no se copia acá.
  ia_proveedor: (() => { const p = String(j.ia_proveedor || 'auto').toLowerCase(); return p === 'auto' ? (String(j.deepseek_configurada) === 'true' ? 'deepseek' : 'ollama') : p; })(),
  deepseek_url: String(j.deepseek_url || 'https://api.deepseek.com').replace(/\/$/, ''),
  deepseek_model: j.deepseek_model || 'deepseek-chat',
  dominios_propios: String(j.dominios_propios || '').split(',').map(s => s.trim().toLowerCase()).filter(Boolean),
  numeros_propios: String(j.numeros_propios || '').split(',').map(s => s.trim()).filter(Boolean).map(s => /[a-z]/i.test(s) ? s : s.replace(/\D/g, '')),
  pais_propio: String(j.pais_propio || '54').replace(/\D/g, '') || '54',
  soc_webhook_url: j.soc_webhook_url || ''
};

// ---------- ¿de dónde viene el mensaje? ----------
let src = j;
if (j.body !== undefined && (j.headers !== undefined || j.params !== undefined || j.query !== undefined)) src = j.body; // Webhook n8n
let raw = null;
if (typeof src === 'string') raw = src;
else if (src && typeof src.raw === 'string') raw = src.raw;
else if (src && typeof src.eml === 'string') raw = src.eml;
if (!src || typeof src !== 'object') src = {};

// ---------- canal: email | whatsapp | sms ----------
// Se decide por la puerta de entrada (webhook /whatsapp o /sms), por el campo "canal" del JSON,
// o por la forma del payload (Meta WhatsApp Cloud API / Twilio).
function detectarCanal(s) {
  const url = String(j.webhookUrl || '').toLowerCase();
  if (/\/centinela\/whatsapp/.test(url)) return 'whatsapp';
  if (/\/centinela\/sms/.test(url)) return 'sms';
  const c = String(s.canal || s.channel || '').toLowerCase();
  if (['whatsapp', 'wa'].includes(c)) return 'whatsapp';
  if (['sms', 'mensaje', 'texto'].includes(c)) return 'sms';
  if (s.object === 'whatsapp_business_account') return 'whatsapp';
  if (typeof s.Body === 'string' && s.From) return /^whatsapp:/i.test(String(s.From)) ? 'whatsapp' : 'sms';
  return 'email';
}
// Normaliza los tres formatos de mensaje a una sola estructura
function normalizarMensaje(s) {
  let de = '', para = '', nombre = '', texto = '', fecha = '', id = '', adj = [], proveedor = 'generico', tipo = 'text';
  if (s.object === 'whatsapp_business_account') {                       // Meta WhatsApp Cloud API
    const ch = (((s.entry || [])[0] || {}).changes || [])[0]; const v = (ch && ch.value) || {};
    const m = (v.messages || [])[0] || {}; const ct = (v.contacts || [])[0] || {};
    de = m.from ? '+' + String(m.from).replace(/^\+/, '') : '';
    para = v.metadata && v.metadata.display_phone_number ? '+' + String(v.metadata.display_phone_number).replace(/^\+/, '') : '';
    nombre = (ct.profile && ct.profile.name) || ''; tipo = m.type || 'text';
    texto = (m.text && m.text.body) || (m.button && m.button.text) || (m[tipo] && m[tipo].caption) || '';
    if (m.timestamp) fecha = new Date(Number(m.timestamp) * 1000).toISOString();
    id = m.id || '';
    for (const t of ['image', 'document', 'audio', 'video', 'sticker']) if (m[t]) adj.push({ filename: m[t].filename || (t + '.' + (String(m[t].mime_type || '').split('/')[1] || 'bin')), contentType: m[t].mime_type || '', sha256: m[t].sha256 || null });
    proveedor = 'meta_cloud_api';
  } else if (typeof s.Body === 'string' && s.From) {                     // Twilio (SMS o WhatsApp)
    de = String(s.From).replace(/^whatsapp:/i, ''); para = String(s.To || '').replace(/^whatsapp:/i, '');
    nombre = s.ProfileName || ''; texto = s.Body; id = s.MessageSid || s.SmsMessageSid || '';
    const n = parseInt(s.NumMedia || '0', 10) || 0;
    for (let i = 0; i < n; i++) adj.push({ filename: 'media_' + i + '.' + (String(s['MediaContentType' + i] || '').split('/')[1] || 'bin'), contentType: s['MediaContentType' + i] || '', url: s['MediaUrl' + i] || '' });
    proveedor = 'twilio';
  } else {                                                               // JSON genérico
    de = s.de || s.from || s.numero || s.remitente || ''; para = s.para || s.to || s.destino || '';
    nombre = s.nombre || s.nombre_contacto || s.contacto || s.name || ''; texto = s.texto || s.text || s.mensaje || s.body || '';
    fecha = s.fecha || s.date || ''; id = s.id || s.id_mensaje || s.messageId || ''; adj = s.adjuntos || s.attachments || []; tipo = s.tipo || 'text';
  }
  return { de: String(de).trim(), para: String(para).trim(), nombre: String(nombre).trim(), texto: String(texto || ''), fecha, id, adjuntos: adj, proveedor, tipo };
}
const canal = detectarCanal(src);
const msg = canal === 'email' ? null : normalizarMensaje(src);
if (msg) raw = null;

const Buf = (typeof Buffer !== 'undefined') ? Buffer : null;
let crypto = null; try { crypto = require('crypto'); } catch (e) { }
if (!Buf) notas.push('Buffer no disponible: no se decodifican adjuntos base64');
if (!crypto) notas.push('crypto no disponible: no se calculan hashes (revisar NODE_FUNCTION_ALLOW_BUILTIN)');

function sha(algo, buf) { if (!crypto || !buf) return null; try { return crypto.createHash(algo).update(buf).digest('hex'); } catch (e) { return null; } }

// ---------- decodificadores MIME ----------
function b64ToBuf(s) { if (!Buf) return null; try { return Buf.from(String(s).replace(/[^A-Za-z0-9+/=]/g, ''), 'base64'); } catch (e) { return null; } }
function qpToBuf(s) {
  s = String(s).replace(/=\r?\n/g, ''); const out = [];
  for (let i = 0; i < s.length; i++) {
    if (s[i] === '=' && /^[0-9A-Fa-f]{2}$/.test(s.substr(i + 1, 2))) { out.push(parseInt(s.substr(i + 1, 2), 16)); i += 2; }
    else out.push(s.charCodeAt(i) & 0xff);
  }
  return Buf ? Buf.from(out) : out;
}
function strToBuf(s) { return Buf ? Buf.from(String(s), 'utf8') : String(s); }
function bufToStr(buf, cs) {
  if (buf == null) return '';
  if (typeof buf === 'string') return buf;
  if (Buf && Buf.isBuffer(buf)) return buf.toString(/utf-?8/i.test(cs || 'utf-8') ? 'utf8' : 'latin1');
  try { return String.fromCharCode.apply(null, buf); } catch (e) { return ''; }
}
function decodeWords(s) {
  if (!s) return '';
  return String(s).replace(/\?=\s+=\?/g, '?==?').replace(/=\?([^?]+)\?([BbQq])\?([^?]*)\?=/g, (m, cs, enc, txt) => {
    try { return enc.toUpperCase() === 'B' ? bufToStr(b64ToBuf(txt), cs) : bufToStr(qpToBuf(txt.replace(/_/g, ' ')), cs); } catch (e) { return m; }
  });
}
function parseHeaders(block) {
  const out = [];
  for (const l of String(block).split('\n')) {
    if (/^[ \t]/.test(l) && out.length) out[out.length - 1][1] += ' ' + l.trim();
    else { const i = l.indexOf(':'); if (i > 0) out.push([l.slice(0, i).trim().toLowerCase(), l.slice(i + 1).trim()]); }
  }
  const map = {}; for (const [k, v] of out) (map[k] = map[k] || []).push(v);
  return map;
}
function param(v, name) {
  const m = new RegExp(name + '\\s*=\\s*("([^"]*)"|([^;\\s]+))', 'i').exec(v || '');
  return m ? (m[2] !== undefined ? m[2] : m[3]) : null;
}

// ---------- parser MIME recursivo (para .eml crudo) ----------
function parseMime(rawPart, acc, depth) {
  const nl = rawPart.indexOf('\n\n');
  const hb = nl < 0 ? rawPart : rawPart.slice(0, nl);
  const body = nl < 0 ? '' : rawPart.slice(nl + 2);
  const h = parseHeaders(hb);
  const ct = (h['content-type'] || ['text/plain'])[0];
  const cte = ((h['content-transfer-encoding'] || [''])[0]).toLowerCase().trim();
  const cd = (h['content-disposition'] || [''])[0];
  const mime = ct.split(';')[0].trim().toLowerCase();
  const charset = param(ct, 'charset') || 'utf-8';
  if (mime.startsWith('multipart/') && depth < 8) {
    const b = param(ct, 'boundary');
    if (b) {
      const parts = body.split('--' + b);
      for (let i = 1; i < parts.length; i++) {
        let p = parts[i]; if (p.startsWith('--')) break;
        parseMime(p.replace(/^\r?\n/, ''), acc, depth + 1);
      }
      return;
    }
  }
  if (mime === 'message/rfc822' && depth < 8) { acc.correos_anidados++; parseMime(body, acc, depth + 1); return; }
  let buf;
  if (cte === 'base64') buf = b64ToBuf(body);
  else if (cte === 'quoted-printable') buf = qpToBuf(body);
  else buf = strToBuf(body);
  let fname = param(cd, 'filename\\*') || param(cd, 'filename') || param(ct, 'name\\*') || param(ct, 'name');
  if (fname && /^[^']*'[^']*'/.test(fname)) { try { fname = decodeURIComponent(fname.replace(/^[^']*'[^']*'/, '')); } catch (e) { } }
  fname = decodeWords(fname || '');
  const esAdjunto = /attachment/i.test(cd) || (fname && !/^text\/(plain|html)$/.test(mime)) || (!/^text\//.test(mime) && mime !== 'multipart/alternative');
  if (esAdjunto) {
    acc.adjuntos.push({
      nombre: fname || ('sin_nombre.' + (mime.split('/')[1] || 'bin')), mime,
      tamano: buf && buf.length != null ? buf.length : null,
      sha256: sha('sha256', buf), md5: sha('md5', buf),
      content_id: (h['content-id'] || [null])[0], inline: /inline/i.test(cd)
    });
    return;
  }
  const txt = bufToStr(buf, charset);
  if (mime === 'text/html') acc.html += txt; else acc.text += txt;
}

// ---------- construir estructura unificada ----------
let hdr = {}, text = '', html = '', adjuntos = [], correos_anidados = 0;
let from = '', to = '', subject = '', date = '', replyTo = '', returnPath = '', messageId = '';

if (raw) {
  raw = raw.replace(/\r\n/g, '\n');
  const nl = raw.indexOf('\n\n');
  hdr = parseHeaders(nl < 0 ? raw : raw.slice(0, nl));
  const acc = { text: '', html: '', adjuntos: [], correos_anidados: 0 };
  parseMime(raw, acc, 0);
  text = acc.text; html = acc.html; adjuntos = acc.adjuntos; correos_anidados = acc.correos_anidados;
} else if (msg) {
  // Mensaje de WhatsApp / SMS ya normalizado
  text = msg.texto; html = '';
  for (const a of (msg.adjuntos || [])) {
    const buf = a.contentBase64 ? b64ToBuf(a.contentBase64) : null;
    adjuntos.push({
      nombre: a.filename || a.name || a.nombre || 'sin_nombre',
      mime: (a.contentType || a.mime || 'application/octet-stream').toLowerCase(),
      tamano: a.size != null ? a.size : (buf ? buf.length : null),
      sha256: (a.sha256 || sha('sha256', buf) || null), md5: (a.md5 || sha('md5', buf) || null),
      content_id: null, inline: false, url_media: a.url || null
    });
  }
} else {
  // Entrada estructurada (JSON del webhook o salida del nodo IMAP)
  const hIn = src.headers || (src.metadata && src.metadata.headers) || {};
  if (typeof hIn === 'string') hdr = parseHeaders(hIn.replace(/\r\n/g, '\n'));
  else if (Array.isArray(hIn)) for (const x of hIn) { if (x && x.name) (hdr[String(x.name).toLowerCase()] = hdr[String(x.name).toLowerCase()] || []).push(String(x.value)); }
  else for (const k of Object.keys(hIn)) { const v = hIn[k]; (hdr[k.toLowerCase()] = hdr[k.toLowerCase()] || []).push(...(Array.isArray(v) ? v.map(String) : [String(v)])); }
  text = String(src.text || src.textPlain || src.body_text || '');
  html = String(src.html || src.textHtml || src.body_html || '');
  for (const a of (src.attachments || [])) {
    let buf = a.contentBase64 ? b64ToBuf(a.contentBase64) : null;
    adjuntos.push({
      nombre: a.filename || a.name || a.nombre || 'sin_nombre',
      mime: (a.contentType || a.mime || 'application/octet-stream').toLowerCase(),
      tamano: a.size != null ? a.size : (buf ? buf.length : null),
      sha256: (a.sha256 || sha('sha256', buf) || null), md5: (a.md5 || sha('md5', buf) || null),
      content_id: a.contentId || null, inline: !!a.inline
    });
  }
  // Adjuntos binarios del nodo IMAP
  if (item.binary) {
    for (const key of Object.keys(item.binary)) {
      const b = item.binary[key]; let buf = null;
      try { buf = await __helpers.getBinaryDataBuffer(0, key); } catch (e) { notas.push('No se pudo leer binario ' + key); }
      adjuntos.push({ nombre: b.fileName || key, mime: (b.mimeType || 'application/octet-stream').toLowerCase(), tamano: buf ? buf.length : null, sha256: sha('sha256', buf), md5: sha('md5', buf), content_id: null, inline: false });
    }
  }
}
const h1 = k => decodeWords((hdr[k] || [''])[0]);
from = decodeWords(src.from || h1('from'));
to = decodeWords(src.to || h1('to'));
subject = decodeWords(src.subject || h1('subject'));
date = src.date || h1('date');
replyTo = decodeWords(src.replyTo || src.reply_to || h1('reply-to'));
returnPath = src.returnPath || src.return_path || h1('return-path');
messageId = src.messageId || src.message_id || h1('message-id');

function parseAddr(s) {
  s = String(s || '').trim();
  const m = /<([^>]+)>/.exec(s);
  const addr = (m ? m[1] : (/[\w.+-]+@[\w.-]+/.exec(s) || [''])[0]).trim().toLowerCase();
  let name = m ? s.slice(0, m.index).trim().replace(/^"|"$/g, '').trim() : '';
  const domain = addr.includes('@') ? addr.split('@').pop() : '';
  return { raw: s, nombre: name, direccion: addr, dominio: domain, dominio_registrable: registrable(domain) };
}
let fromP = parseAddr(from), replyP = parseAddr(replyTo), rpP = parseAddr(returnPath);
let telefono = null;
if (msg) {
  // En WhatsApp/SMS el "remitente" es un número (o un ID alfanumérico); no hay dominio
  telefono = parseTelefono(msg.de, cfg.pais_propio, cfg.numeros_propios);
  fromP = { raw: msg.de + (msg.nombre ? ' (' + msg.nombre + ')' : ''), nombre: msg.nombre, direccion: telefono.original, dominio: '', dominio_registrable: '' };
  replyP = parseAddr(''); rpP = parseAddr('');
  to = msg.para; subject = ''; date = msg.fecha; messageId = msg.id;
}

// ---------- autenticación (SPF / DKIM / DMARC) ----------
const authRaw = (hdr['authentication-results'] || []).concat(hdr['arc-authentication-results'] || []).join(' | ');
const rspf = (hdr['received-spf'] || [''])[0];
const pick = re => { const m = re.exec(authRaw); return m ? m[1].toLowerCase() : null; };
const auth = msg ? { spf: 'no_aplica', dkim: 'no_aplica', dmarc: 'no_aplica', dkim_dominio: null, raw: '' } : {
  spf: pick(/\bspf=(\w+)/i) || (rspf ? rspf.split(/\s/)[0].toLowerCase() : null) || 'ausente',
  dkim: pick(/\bdkim=(\w+)/i) || (hdr['dkim-signature'] ? 'firmado_sin_verificar' : 'ausente'),
  dmarc: pick(/\bdmarc=(\w+)/i) || 'ausente',
  dkim_dominio: (/\bdkim=\w+[^;]*?header\.(?:d|i)=@?([\w.-]+)/i.exec(authRaw) || [null, null])[1],
  raw: authRaw
};

// ---------- cadena Received e IPs ----------
const received = (hdr['received'] || []).map(v => {
  const ipm = /\[(\d{1,3}(?:\.\d{1,3}){3})\]/.exec(v) || /\b(\d{1,3}(?:\.\d{1,3}){3})\b/.exec(v);
  const fromm = /^from\s+([^\s(]+)/i.exec(v);
  return { from: fromm ? fromm[1] : null, ip: ipm ? ipm[1] : null, raw: v.slice(0, 300) };
});
let ips = [];
for (const r of received) if (r.ip && esIp(r.ip) && !esIpPrivada(r.ip)) ips.push(r.ip);
for (const k of ['x-originating-ip', 'x-sender-ip', 'x-real-ip', 'x-client-ip']) for (const v of (hdr[k] || [])) { const m = /(\d{1,3}(?:\.\d{1,3}){3})/.exec(v); if (m && !esIpPrivada(m[1])) ips.push(m[1]); }

// ---------- URLs (texto + HTML con texto ancla) ----------
const urls = [];
const seen = new Set();
function addUrl(u, ancla) {
  u = String(u || '').trim().replace(/[)\]}>.,;:!?'"]+$/, '');
  if (!/^https?:\/\//i.test(u)) { if (/^www\./i.test(u)) u = 'http://' + u; else return; }
  const pu = parseUrl(u);
  if (!pu || !pu.hostname || !pu.hostname.includes('.')) return;
  const host = pu.hostname;
  if (seen.has(u)) { if (ancla) { const x = urls.find(q => q.url === u); if (x && !x.texto_ancla) x.texto_ancla = ancla; } return; }
  seen.add(u);
  urls.push({ url: u, host, dominio: esIp(host) ? host : registrable(host), es_ip: esIp(host), texto_ancla: ancla || '' });
}
const reA = /<a\b[^>]*?href\s*=\s*["']?([^"' >]+)["']?[^>]*>([\s\S]*?)<\/a>/gi; let m;
while ((m = reA.exec(html)) !== null) addUrl(m[1], m[2].replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim().slice(0, 120));
const reU = /\b(?:https?:\/\/|www\.)[^\s<>"'`]+/gi;
for (const s of [text, html.replace(/<[^>]+>/g, ' ')]) while ((m = reU.exec(s)) !== null) addUrl(m[0], '');
// En SMS/WhatsApp los enlaces suelen ir sin "http://" (correo-argentino-envios.click/pago): se detectan dominios "pelados"
if (msg) {
  const reD = /(?:^|[\s(:,])((?:[a-z0-9-]+\.)+(?:com|net|org|ar|click|link|xyz|top|online|site|info|app|io|co|me|ly|gl|ru|cn|tk|ml|ga|cf|gq|icu|buzz|live|shop|store|cc|tv|pw|su|work|rest|monster|cfd|sbs|lol|zip|mov|vip|pro|biz|cloud|page|digital)(?:\/[^\s<>"'`]*)?)(?=$|[\s)\]}>.,;:!?'"])/gi;
  while ((m = reD.exec(text)) !== null) addUrl('http://' + m[1], '');
}

// ---------- texto plano del cuerpo (para heurísticas e IA) ----------
function htmlToText(hh) {
  return String(hh).replace(/<style[\s\S]*?<\/style>/gi, ' ').replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<br\s*\/?>/gi, '\n').replace(/<\/(p|div|tr|li|h\d)>/gi, '\n').replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'")
    .replace(/[ \t]+/g, ' ').replace(/\n\s*\n+/g, '\n').trim();
}
const cuerpo = (text && text.trim()) ? text.trim() : htmlToText(html);

// ---------- adjuntos: extensión ----------
for (const a of adjuntos) {
  const n = String(a.nombre || '').toLowerCase();
  const parts = n.split('.'); a.ext = parts.length > 1 ? parts.pop() : '';
  a.doble_extension = parts.length > 1 && /^(pdf|doc|docx|xls|xlsx|jpg|jpeg|png|txt)$/.test(parts[parts.length - 1]) ? parts[parts.length - 1] + '.' + a.ext : null;
}

// ---------- dominios a enriquecer ----------
const dominios = uniq([fromP.dominio_registrable, replyP.dominio_registrable, rpP.dominio_registrable, auth.dkim_dominio ? registrable(auth.dkim_dominio) : null]
  .concat(urls.filter(u => !u.es_ip).map(u => u.dominio)));
ips = uniq(ips.concat(urls.filter(u => u.es_ip).map(u => u.host)));
const hashes = uniq(adjuntos.map(a => a.sha256));

const report_id = new Date().toISOString().replace(/[-:.TZ]/g, '').slice(0, 14) + '-' + Math.random().toString(36).slice(2, 8);

return [{
  json: {
    report_id,
    recibido_en: new Date().toISOString(),
    origen_entrada: raw ? 'eml_crudo' : (item.binary ? 'imap' : (msg ? 'mensaje_' + msg.proveedor : 'json_estructurado')),
    canal,
    mensaje: msg ? { canal, numero_origen: fromP.direccion, numero_destino: msg.para, nombre_contacto: msg.nombre, proveedor: msg.proveedor, tipo: msg.tipo, id: msg.id, telefono } : null,
    notas_parser: notas,
    config: cfg,
    correo: {
      from: fromP, reply_to: replyP, return_path: rpP, to, subject, date, message_id: messageId,
      auth, received, n_saltos: received.length,
      cabeceras: Object.fromEntries(Object.entries(hdr).map(([k, v]) => [k, v.map(x => String(x).slice(0, 500))])),
      cuerpo: cuerpo.slice(0, 20000), html_presente: !!html, html_muestra: html.slice(0, 20000), correos_anidados
    },
    artefactos: { ips, dominios, urls, adjuntos, hashes },
    resumen_artefactos: { ips: ips.length, dominios: dominios.length, urls: urls.length, adjuntos: adjuntos.length, hashes: hashes.length }
  }
}];

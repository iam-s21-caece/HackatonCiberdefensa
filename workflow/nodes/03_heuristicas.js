// =====================================================================
//  NODO: Heurísticas de cuerpo, URLs y adjuntos
//  Ingeniería social, lookalikes/homoglifos, URLs sospechosas,
//  adjuntos peligrosos, HTML malicioso. No depende de servicios externos.
// =====================================================================
const d = $input.first().json;
const c = d.correo, cfg = d.config, A = d.artefactos;
const hz = [];
const F = 'heuristicas';
const cuerpo = (c.cuerpo || '').toLowerCase();
const asunto = (c.subject || '').toLowerCase();
const todo = asunto + '\n' + cuerpo;

// --- 1) Ingeniería social (ES + EN) ---
const GRUPOS = {
  urgencia: { peso: 8, sev: 'media', kw: ['urgente', 'inmediato', 'inmediatamente', '24 horas', '48 horas', 'último aviso', 'ultimo aviso', 'suspendid', 'bloquead', 'vence hoy', 'expira', 'acción requerida', 'accion requerida', 'de inmediato', 'a la brevedad', 'urgent', 'immediately', 'final notice', 'suspended', 'expire', 'action required', 'last warning'] },
  credenciales: { peso: 14, sev: 'alta', kw: ['contraseña', 'contrasena', 'clave de acceso', 'usuario y contraseña', 'verifique su cuenta', 'verificar su cuenta', 'verificá tu cuenta', 'confirme su identidad', 'confirmá tu identidad', 'actualice sus datos', 'actualizá tus datos', 'iniciar sesión', 'inicie sesión', 'iniciá sesión', 'reactivar', 'validar cuenta', 'password', 'verify your account', 'confirm your identity', 'sign in', 'log in', 'login', 'credentials', 'token'] },
  financiero: { peso: 10, sev: 'media', kw: ['transferencia', 'cbu', 'alias bancario', 'tarjeta de crédito', 'tarjeta de credito', 'factura', 'pago pendiente', 'deuda', 'reembolso', 'premio', 'usted ganó', 'ganaste', 'herencia', 'bitcoin', 'cripto', 'gift card', 'tarjeta de regalo', 'invoice', 'payment', 'wire transfer', 'refund', 'you won', 'lottery', 'haberes', 'liquidación', 'liquidacion'] },
  amenaza: { peso: 8, sev: 'media', kw: ['sanción', 'sancion', 'sumario', 'multa', 'denuncia', 'citación', 'citacion', 'judicial', 'legal action', 'penalty', 'será dado de baja', 'baja definitiva', 'proceso disciplinario'] },
  institucional: { peso: 6, sev: 'baja', kw: ['orden del día', 'orden del dia', 'comando', 'estado mayor', 'jefatura', 'legajo', 'licencia', 'suboficial', 'oficial', 'ministerio de defensa', 'servicio militar', 'unidad militar', 'guarnición', 'guarnicion', 'cuartel', 'regimiento', 'batallón', 'batallon', 'brigada', 'personal militar', 'ascenso', 'destino'] },
  descarga: { peso: 8, sev: 'media', kw: ['descargue', 'descargá', 'descargar el archivo', 'abra el adjunto', 'abrir el adjunto', 'habilitar contenido', 'habilite las macros', 'enable content', 'enable macros', 'download the attachment', 'open the attached'] },
  // Smishing clásico argentino: paquete retenido, tasa aduanera, beneficio ANSES, cuenta de WhatsApp
  smishing: { peso: 8, sev: 'media', kw: ['paquete', 'encomienda', 'retenido', 'retenida', 'aduana', 'tasa aduanera', 'tasa pendiente', 'código de seguimiento', 'codigo de seguimiento', 'tu pedido', 'entrega fallida', 'no pudimos entregar', 'reprogramar', 'correo argentino', 'andreani', 'oca', 'sube', 'bono', 'subsidio', 'beneficio', 'reintegro', 'te llegó', 'te llego', 'hacé clic', 'hace clic', 'ingresá al link', 'ingresa al link', 'your package', 'delivery failed', 'customs fee'] },
  // Secuestro de cuenta de WhatsApp / estafa "cambié de número"
  secuestro_cuenta: { peso: 18, sev: 'alta', kw: ['código de verificación', 'codigo de verificacion', 'pasame el código', 'pasame el codigo', 'me llegó un código', 'me llego un codigo', 'te llegó un código', 'te llego un codigo', 'código de 6 dígitos', 'codigo de 6 digitos', 'cambié de número', 'cambie de numero', 'este es mi nuevo número', 'este es mi nuevo numero', 'guardá este número', 'guarda este numero', 'perdí el celular', 'perdi el celular', 'verification code', 'is your whatsapp code'] }
};
const kwHits = {};
for (const [g, def] of Object.entries(GRUPOS)) {
  const hits = def.kw.filter(k => todo.includes(k));
  if (hits.length) {
    kwHits[g] = hits;
    const peso = Math.min(def.peso + Math.max(0, hits.length - 1) * 2, def.peso * 2);
    hz.push(H('ingenieria_social', 'palabras_' + g, hits.slice(0, 6).join(', '), def.sev, peso, 'Lenguaje de ' + g + ' (' + hits.length + ' coincidencias)', F));
  }
}
// Combinaciones letales: credenciales + urgencia, institucional + remitente externo
if (kwHits.credenciales && kwHits.urgencia) hz.push(H('ingenieria_social', 'combo_credenciales_urgencia', '', 'alta', 12, 'Pide credenciales/verificación bajo presión de tiempo: patrón clásico de phishing', F));
const esMensaje = !!(d.canal && d.canal !== 'email');
const numeroPropio = !!(d.mensaje && d.mensaje.telefono && d.mensaje.telefono.propio);
const esPropio = esMensaje ? numeroPropio : cfg.dominios_propios.includes(c.from.dominio_registrable);
if (kwHits.institucional && !esPropio && c.from.dominio) hz.push(H('ingenieria_social', 'tematica_institucional_externa', c.from.dominio, 'alta', 12, 'Temática militar/institucional desde un dominio externo (' + c.from.dominio + '): indicio de spear-phishing dirigido', F));
if (kwHits.institucional && esMensaje && !numeroPropio) hz.push(H('ingenieria_social', 'tematica_institucional_por_mensaje', c.from.direccion, 'alta', 12, 'Temática militar/institucional por ' + d.canal + ' desde un número no registrado: la institución no comunica órdenes por este canal', F));
if (esMensaje && A.urls.length && !numeroPropio) hz.push(H('url', 'enlace_de_numero_desconocido', A.urls[0].url, 'alta', 12, 'Enlace en un ' + d.canal + ' de un número no registrado: vector principal del smishing', F));
if (esMensaje && kwHits.smishing && kwHits.urgencia) hz.push(H('ingenieria_social', 'combo_smishing_urgencia', '', 'alta', 10, 'Aviso de paquete/beneficio con presión de tiempo: patrón clásico de smishing', F));
if (kwHits.secuestro_cuenta && esMensaje) hz.push(H('ingenieria_social', 'intento_secuestro_cuenta', '', 'critica', 15, 'Pide un código de verificación o anuncia "cambio de número": intento de tomar control de la cuenta de WhatsApp o de suplantar a un contacto', F));
if (/^(re|fwd|fw|rv):/i.test(asunto) && !c.cabeceras['in-reply-to'] && !c.cabeceras['references']) hz.push(H('ingenieria_social', 'falso_hilo', c.subject, 'media', 6, 'Asunto simula respuesta/reenvío pero no hay hilo previo (In-Reply-To/References)', F));
if (!cuerpo.trim() && A.adjuntos.length) hz.push(H('ingenieria_social', 'cuerpo_vacio_con_adjunto', '', 'media', 8, 'Cuerpo vacío y adjunto presente: fuerza a abrir el archivo', F));
const ratioMayus = asunto.replace(/[^a-z]/gi, '').length ? (c.subject.replace(/[^A-Z]/g, '').length / c.subject.replace(/[^a-zA-Z]/g, '').length) : 0;
if (ratioMayus > 0.6 && c.subject.length > 8) hz.push(H('ingenieria_social', 'asunto_mayusculas', c.subject, 'baja', 3, 'Asunto en mayúsculas (alarmismo)', F));

// --- 2) Lookalike / homoglifos contra dominios propios y marcas ---
function norm(s) { return String(s).toLowerCase().replace(/rn/g, 'm').replace(/vv/g, 'w').replace(/0/g, 'o').replace(/1/g, 'l').replace(/3/g, 'e').replace(/5/g, 's').replace(/7/g, 't').replace(/[^a-z]/g, ''); }
function lev(a, b) {
  const m = a.length, n = b.length; if (!m) return n; if (!n) return m;
  let prev = Array.from({ length: n + 1 }, (_, i) => i);
  for (let i = 1; i <= m; i++) { const cur = [i]; for (let j = 1; j <= n; j++) cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1)); prev = cur; }
  return prev[n];
}
const dominiosMail = uniq([c.from.dominio_registrable, c.reply_to.dominio_registrable]);
const dominiosUrl = uniq(A.urls.filter(u => !u.es_ip).map(u => u.dominio));
function chequearLookalike(dom, contexto) {
  if (!dom) return;
  const etiqueta = dom.split('.')[0];
  if (/xn--/.test(dom)) hz.push(H('lookalike', 'punycode', dom, 'alta', 18, 'Dominio IDN/Punycode en ' + contexto + ' (homógrafo)', F));
  for (const dp of cfg.dominios_propios) {
    if (dom === dp || dom.endsWith('.' + dp)) continue;
    const ep = dp.split('.')[0];
    const dist = lev(norm(etiqueta), norm(ep));
    if (etiqueta === ep) hz.push(H('lookalike', 'dominio_propio_otro_tld', dom, 'alta', 22, contexto + ': mismo nombre que dominio propio ' + dp + ' con otra terminación', F));
    else if (ep.length >= 5 && dist > 0 && dist <= 2) hz.push(H('lookalike', 'dominio_propio_similar', dom, 'critica', 30, contexto + ': "' + dom + '" imita al dominio propio ' + dp + ' (distancia ' + dist + ')', F));
    else if (ep.length >= 5 && norm(dom).includes(norm(ep)) && dom !== dp) hz.push(H('lookalike', 'dominio_propio_embebido', dom, 'alta', 18, contexto + ': contiene el nombre institucional "' + ep + '" en un dominio ajeno', F));
  }
  // Si ya se marcó como imitación de dominio propio, no repetir el hallazgo por "marca"
  const yaPropio = hz.some(x => x.valor === dom && x.tipo.startsWith('dominio_propio'));
  for (const marca of MARCAS) {
    if (marca.length < 5 || yaPropio) continue;
    const nd = norm(dom.replace(/\.(com|net|org|ar|gob|gov|mil|es|io|co|app|info)$/g, ''));
    const oficial = new RegExp('^(www\\.)?' + marca + '\\.(com|com\\.ar|gob\\.ar|gov\\.ar|mil\\.ar|net|org|ar|es|io|app)$').test(dom);
    if (oficial) continue;
    if (nd.includes(marca) && dom.split('.')[0].replace(/[^a-z]/g, '') !== marca) hz.push(H('lookalike', 'marca_en_dominio', dom, 'alta', 16, contexto + ': el dominio incluye la marca "' + marca + '" sin ser el oficial', F));
    else if (lev(norm(etiqueta), marca) === 1 && etiqueta.length >= 5) hz.push(H('lookalike', 'marca_similar', dom, 'alta', 18, contexto + ': "' + etiqueta + '" es un typosquat de "' + marca + '"', F));
  }
}
for (const dm of dominiosMail) chequearLookalike(dm, 'remitente');
for (const du of dominiosUrl) chequearLookalike(du, 'enlace');

// --- 3) URLs ---
const ACORTADORES = ['bit.ly', 'tinyurl.com', 't.co', 'goo.gl', 'cutt.ly', 'rebrand.ly', 'is.gd', 'ow.ly', 'buff.ly', 'shorturl.at', 'rb.gy', 'tiny.cc', 'lnkd.in', 'acortar.link', 'n9.cl'];
const TLD_SOSP = ['zip', 'mov', 'xyz', 'top', 'click', 'tk', 'ml', 'ga', 'cf', 'gq', 'icu', 'buzz', 'work', 'country', 'link', 'live', 'monster', 'rest', 'cam', 'quest', 'sbs', 'cfd', 'lol', 'ru', 'su', 'cn', 'pw'];
const HOSTING_ABUSADO = ['weebly.com', 'wixsite.com', 'godaddysites.com', 'webflow.io', 'glitch.me', 'netlify.app', 'vercel.app', 'pages.dev', 'web.app', 'firebaseapp.com', 'github.io', 'blogspot.com', 'sites.google.com', 'forms.gle', 'docs.google.com', '000webhostapp.com', 'ngrok.io', 'ngrok-free.app', 'trycloudflare.com', 'r2.dev', 'ipfs.io', 'dweb.link'];
let urlsExternas = 0;
for (const u of A.urls) {
  const p = parseUrl(u.url); if (!p) continue;
  const esPropioUrl = cfg.dominios_propios.some(dp => u.dominio === dp || u.host.endsWith('.' + dp));
  if (!esPropioUrl) urlsExternas++;
  if (u.es_ip) hz.push(H('url', 'url_con_ip', u.url, 'alta', 18, 'Enlace directo a una IP en vez de un dominio', F));
  if (ACORTADORES.includes(u.dominio)) hz.push(H('url', 'acortador', u.url, 'media', 10, 'URL acortada: oculta el destino real', F));
  const tld = u.host.split('.').pop();
  if (TLD_SOSP.includes(tld)) hz.push(H('url', 'tld_sospechoso', u.url, 'media', 8, 'TLD .' + tld + ' con alta tasa de abuso', F));
  if (HOSTING_ABUSADO.some(h => u.host === h || u.host.endsWith('.' + h))) hz.push(H('url', 'hosting_gratuito', u.url, 'media', 8, 'Alojado en plataforma gratuita/temporal frecuentemente usada para phishing', F));
  if (p.username || u.url.includes('@')) hz.push(H('url', 'arroba_en_url', u.url, 'alta', 15, 'Credenciales/@ en la URL: el navegador ignora lo anterior al @', F));
  if (p.port && !['80', '443', ''].includes(p.port)) hz.push(H('url', 'puerto_no_estandar', u.url, 'media', 8, 'Puerto no estándar ' + p.port, F));
  if (p.protocol === 'http:' && !esPropioUrl) hz.push(H('url', 'http_sin_tls', u.url, 'baja', 3, 'Enlace sin HTTPS', F));
  if (u.host.split('.').length >= 5) hz.push(H('url', 'muchos_subdominios', u.url, 'media', 6, 'Exceso de subdominios (' + u.host + ')', F));
  if (u.url.length > 120) hz.push(H('url', 'url_larga', u.url.slice(0, 80) + '...', 'baja', 3, 'URL muy larga (' + u.url.length + ' caracteres)', F));
  if (/\.(exe|scr|msi|bat|cmd|ps1|vbs|js|jar|hta|iso|img|lnk|zip|rar|7z|apk)(\?|$)/i.test(p.pathname)) hz.push(H('url', 'descarga_ejecutable', u.url, 'alta', 18, 'Enlace a descarga de archivo potencialmente ejecutable', F));
  if (/(login|signin|sign-in|verify|verif|secure|account|cuenta|update|actualiz|confirm|password|clave|banking|wallet|recover|unlock|validar|ingres)/i.test(p.pathname + p.search + u.host) && !esPropioUrl)
    hz.push(H('url', 'palabras_phishing_en_url', u.url, 'media', 8, 'Palabras típicas de captura de credenciales en la URL', F));
  if (/^data:|javascript:/i.test(u.url)) hz.push(H('url', 'esquema_peligroso', u.url.slice(0, 60), 'alta', 15, 'Esquema data:/javascript: en enlace', F));
  // Texto ancla engañoso: dice un dominio y lleva a otro
  const anc = (u.texto_ancla || '').toLowerCase();
  const anclaUrl = /(?:https?:\/\/)?((?:[a-z0-9-]+\.)+[a-z]{2,})/i.exec(anc);
  if (anclaUrl && registrable(anclaUrl[1]) !== u.dominio && !u.es_ip) hz.push(H('url', 'ancla_enganosa', '"' + u.texto_ancla + '" -> ' + u.url, 'alta', 20, 'El texto del enlace muestra ' + anclaUrl[1] + ' pero apunta a ' + u.host, F));
  if (/xn--/.test(u.host)) { /* ya cubierto en lookalike */ }
}
if (urlsExternas >= 6) hz.push(H('url', 'muchas_urls', urlsExternas, 'baja', 3, urlsExternas + ' enlaces externos', F));

// --- 4) Adjuntos ---
const EXT_CRITICA = ['exe', 'scr', 'pif', 'com', 'bat', 'cmd', 'ps1', 'vbs', 'vbe', 'js', 'jse', 'wsf', 'wsh', 'hta', 'msi', 'msp', 'cpl', 'jar', 'lnk', 'reg', 'dll', 'apk'];
const EXT_ALTA = ['iso', 'img', 'vhd', 'vhdx', 'one', 'docm', 'xlsm', 'pptm', 'dotm', 'xltm', 'xll', 'chm', 'svg', 'html', 'htm', 'shtml', 'xhtml', 'mht', 'url', 'wim'];
const EXT_MEDIA = ['zip', 'rar', '7z', 'gz', 'tar', 'cab', 'ace', 'arj', 'bz2', 'xz', 'tgz'];
const EXT_BAJA = ['doc', 'xls', 'ppt', 'rtf', 'pdf', 'odt', 'ods'];
for (const a of A.adjuntos) {
  const ext = a.ext || '';
  if (EXT_CRITICA.includes(ext)) hz.push(H('adjunto', 'ejecutable', a.nombre, 'critica', 35, 'Adjunto ejecutable/script (.' + ext + ')', F));
  else if (EXT_ALTA.includes(ext)) hz.push(H('adjunto', 'contenedor_o_macro', a.nombre, 'alta', 22, 'Formato usado para entregar malware (.' + ext + ': imagen de disco, macro, HTML smuggling, SVG, OneNote)', F));
  else if (EXT_MEDIA.includes(ext)) hz.push(H('adjunto', 'archivo_comprimido', a.nombre, 'media', 10, 'Comprimido (.' + ext + '): puede ocultar ejecutables y evadir antivirus, más si tiene contraseña', F));
  else if (EXT_BAJA.includes(ext)) hz.push(H('adjunto', 'documento_ofimatico', a.nombre, 'baja', 4, 'Documento .' + ext + ' (posible macro/exploit, revisar hash)', F));
  if (a.doble_extension) hz.push(H('adjunto', 'doble_extension', a.nombre, 'critica', 30, 'Doble extensión (' + a.doble_extension + '): el usuario ve "' + a.doble_extension.split('.')[0] + '" pero ejecuta .' + ext, F));
  if (/\s{3,}/.test(a.nombre)) hz.push(H('adjunto', 'nombre_con_espacios', a.nombre, 'alta', 15, 'Espacios de relleno en el nombre para ocultar la extensión real', F));
  if (/[‮​‌‍⁠]/.test(a.nombre)) hz.push(H('adjunto', 'unicode_rtl', a.nombre, 'critica', 30, 'Caracteres Unicode invisibles/RTL override en el nombre del archivo', F));
  const mimeEsp = { pdf: 'application/pdf', zip: 'application/zip', docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg' };
  if (mimeEsp[ext] && a.mime && a.mime !== 'application/octet-stream' && a.mime !== mimeEsp[ext]) hz.push(H('adjunto', 'mime_inconsistente', a.nombre + ' (' + a.mime + ')', 'media', 8, 'El tipo MIME declarado no coincide con la extensión', F));
  if (a.tamano != null && a.tamano < 2000 && ['zip', 'rar', 'iso', 'docm', 'xlsm'].includes(ext)) hz.push(H('adjunto', 'tamano_minimo', a.nombre + ' (' + a.tamano + ' bytes)', 'media', 6, 'Archivo diminuto para su tipo: típico dropper/downloader', F));
  if (!a.sha256) hz.push(H('adjunto', 'sin_hash', a.nombre, 'info', 0, 'No se pudo calcular el hash del adjunto', F));
}

// --- 5) HTML ---
const hh = c.html_muestra || '';
if (hh) {
  if (/<form\b/i.test(hh)) hz.push(H('html', 'formulario_embebido', '', 'alta', 18, 'Formulario dentro del correo (captura de datos)', F));
  if (/type\s*=\s*["']?password/i.test(hh)) hz.push(H('html', 'campo_password', '', 'critica', 30, 'Campo de contraseña dentro del correo', F));
  if (/<script\b/i.test(hh)) hz.push(H('html', 'script', '', 'alta', 15, 'Contiene <script>', F));
  if (/<iframe\b|<object\b|<embed\b/i.test(hh)) hz.push(H('html', 'iframe_object', '', 'alta', 12, 'Contiene iframe/object/embed', F));
  if (/display\s*:\s*none|font-size\s*:\s*0|visibility\s*:\s*hidden|opacity\s*:\s*0(?![.\d])/i.test(hh)) hz.push(H('html', 'texto_oculto', '', 'media', 8, 'Texto/elementos ocultos (relleno para engañar filtros bayesianos)', F));
  if (/<img[^>]+(width\s*=\s*["']?1\b|height\s*=\s*["']?1\b)/i.test(hh)) hz.push(H('html', 'pixel_rastreo', '', 'baja', 3, 'Píxel de seguimiento 1x1', F));
  if (/javascript:/i.test(hh)) hz.push(H('html', 'javascript_href', '', 'alta', 12, 'href con javascript:', F));
  if (/data:text\/html|data:application/i.test(hh)) hz.push(H('html', 'data_uri', '', 'alta', 15, 'data: URI con HTML/aplicación embebida (HTML smuggling)', F));
  if (/<a\b[^>]*>\s*<img\b/i.test(hh) && !cuerpo.trim()) hz.push(H('html', 'imagen_unica_con_enlace', '', 'media', 8, 'El correo es sólo una imagen clickeable: evade filtros de texto', F));
  const urlsPropias = A.urls.filter(u => cfg.dominios_propios.some(dp => u.dominio === dp)).length;
  if (A.urls.length && urlsPropias === 0 && esPropio) hz.push(H('html', 'interno_sin_enlaces_propios', '', 'baja', 4, 'Correo "interno" cuyos enlaces son todos externos', F));
}

// Señales a favor (reducen score): sin URLs ni adjuntos y sin palabras de riesgo
if (!A.urls.length && !A.adjuntos.length && !kwHits.credenciales && !kwHits.financiero && !kwHits.secuestro_cuenta) hz.push(H('contexto', 'sin_vector', '', 'info', -10, 'Sin enlaces ni adjuntos ni pedido de datos: sin vector de ataque evidente', F));

return salida(F, 'ok', {
  palabras_clave: kwHits, urls_analizadas: A.urls.length, urls_externas: urlsExternas, adjuntos_analizados: A.adjuntos.length,
  dominios_remitente: dominiosMail, dominios_enlaces: dominiosUrl, html: !!hh
}, hz);

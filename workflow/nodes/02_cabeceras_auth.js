// =====================================================================
//  NODO: Cabeceras y autenticación (SPF / DKIM / DMARC)
//  Analiza la identidad del remitente: quién dice ser vs. quién es.
// =====================================================================
const d = $input.first().json;
const c = d.correo, cfg = d.config;
const hz = [];
const F = 'cabeceras';

// =====================================================================
//  WhatsApp / SMS: no hay cabeceras ni SPF/DKIM. La identidad es el número.
// =====================================================================
if (d.canal && d.canal !== 'email') {
  const m = d.mensaje || {}; const t = m.telefono || {};
  const propio = !!t.propio;
  const nombre = String(m.nombre_contacto || '').toLowerCase();
  const nombreSinEsp = nombre.replace(/[^a-z0-9]/g, '');
  const idSinEsp = String(m.numero_origen || '').toLowerCase().replace(/[^a-z0-9]/g, '');
  const CANAL = d.canal === 'whatsapp' ? 'WhatsApp' : 'SMS';
  if (propio) hz.push(H('identidad', 'numero_propio', m.numero_origen, 'info', -15, 'Remitente registrado como número/ID institucional', F));
  if (t.alfanumerico) hz.push(H('identidad', 'remitente_alfanumerico', m.numero_origen, 'media', 8, 'Remitente alfanumérico "' + m.numero_origen + '": el ID de texto lo define quien envía, no se puede responder ni verificar', F));
  else if (!t.e164 && !t.codigo_corto) hz.push(H('identidad', 'numero_no_verificable', m.numero_origen, 'baja', 3, 'Número en formato local (no E.164): no se puede determinar país ni operador', F));
  if (t.codigo_corto && !propio) hz.push(H('identidad', 'codigo_corto', m.numero_origen, 'info', -3, 'Código corto: canal A2P registrado ante operadores, más difícil de falsificar', F));
  if (t.extranjero === true && !propio) hz.push(H('identidad', 'numero_extranjero', m.numero_origen, 'media', 10, 'Número de ' + t.pais + ' (+' + t.codigo_pais + ') enviando ' + CANAL + ' a un destinatario argentino', F));
  const marca = MARCAS.find(mk => mk.length >= 4 && (nombreSinEsp.includes(mk) || (t.alfanumerico && idSinEsp.includes(mk))));
  if (marca && !propio) hz.push(H('identidad', 'marca_en_remitente_mensaje', m.nombre_contacto || m.numero_origen, 'alta', 14, 'Se presenta como "' + marca + '" pero el remitente no es un número/ID institucional registrado', F));
  const inst = /(ejercito|ej[eé]rcito|comando|jefatura|estado mayor|ministerio|defensa|banco|soporte|seguridad|rrhh|recursos humanos|sistemas|tesorer[ií]a|haberes|anses|afip|arca|mercado ?pago|correo|aduana|envios|env[ií]os|delivery)/i.test(nombre);
  if (inst && !propio && !marca) hz.push(H('identidad', 'nombre_institucional_mensaje', m.nombre_contacto, 'alta', 12, 'Nombre de perfil institucional ("' + m.nombre_contacto + '") en un número no registrado', F));
  for (const dp of cfg.dominios_propios) {
    const et = dp.split('.')[0];
    if (et.length >= 4 && nombreSinEsp.includes(et) && !propio) { hz.push(H('identidad', 'suplantacion_interna_mensaje', m.nombre_contacto, 'alta', 20, 'Se presenta como "' + m.nombre_contacto + '" (' + dp + ') desde un número que no es institucional', F)); break; }
  }
  // Grado militar en el nombre de perfil ("Cap. Gómez", "Tte. Cnel. López") desde un número extranjero o no registrado
  const grado = /(^|\s)(gral|grl|cnel|tcnl|tte\.? ?cnel|my|cap|tte|subtte|subof|sgto|sarg|cabo|sold|of\.|oficial|suboficial|general|coronel|mayor|capit[aá]n|teniente|sargento)\b\.?/i.test(nombre);
  if (grado && !propio && (t.extranjero === true || t.alfanumerico || !t.e164)) hz.push(H('identidad', 'grado_militar_en_perfil', m.nombre_contacto, 'alta', 12, 'Perfil con grado militar ("' + m.nombre_contacto + '") desde un número ' + (t.extranjero ? 'extranjero (' + t.pais + ')' : 'no verificable') + ': suplantación de un camarada', F));
  if (t.codigo_pais === '54' && !t.movil_ar && d.canal === 'whatsapp' && !t.alfanumerico && !t.codigo_corto) hz.push(H('identidad', 'numero_ar_no_movil', m.numero_origen, 'baja', 3, 'Número argentino sin el 9 de móvil: formato inusual para WhatsApp', F));
  if (m.tipo && m.tipo !== 'text' && !(c.cuerpo || '').trim()) hz.push(H('cabeceras', 'solo_adjunto_mensaje', m.tipo, 'media', 6, 'Mensaje sin texto, sólo ' + m.tipo + ': fuerza a abrir el contenido', F));
  if (!m.numero_origen) hz.push(H('identidad', 'sin_remitente', '', 'alta', 15, 'Mensaje sin remitente identificable', F));
  return salida(F, 'ok', { canal: d.canal, proveedor: m.proveedor, remitente: m.numero_origen, nombre_contacto: m.nombre_contacto, telefono: t, autenticacion: 'no_aplica' }, hz);
}

// --- Autenticación del remitente ---
const spf = c.auth.spf, dkim = c.auth.dkim, dmarc = c.auth.dmarc;
if (spf === 'fail' || spf === 'softfail') hz.push(H('autenticacion', 'spf_fail', spf, 'alta', 20, 'SPF ' + spf + ': el servidor emisor NO está autorizado por el dominio ' + c.from.dominio, F));
else if (spf === 'none' || spf === 'ausente') hz.push(H('autenticacion', 'spf_ausente', spf, 'media', 8, 'Sin verificación SPF disponible para el dominio remitente', F));
else if (spf === 'permerror' || spf === 'temperror') hz.push(H('autenticacion', 'spf_error', spf, 'baja', 4, 'Error evaluando SPF', F));

if (dkim === 'fail') hz.push(H('autenticacion', 'dkim_fail', dkim, 'alta', 18, 'Firma DKIM inválida: el mensaje fue alterado o la firma es falsa', F));
else if (dkim === 'none' || dkim === 'ausente') hz.push(H('autenticacion', 'dkim_ausente', dkim, 'media', 6, 'El mensaje no está firmado con DKIM', F));
else if (dkim === 'pass' && c.auth.dkim_dominio && registrable(c.auth.dkim_dominio) !== c.from.dominio_registrable)
  hz.push(H('autenticacion', 'dkim_dominio_distinto', c.auth.dkim_dominio, 'media', 10, 'DKIM firmado por ' + c.auth.dkim_dominio + ' pero el From es ' + c.from.dominio + ' (posible relay/ESP o suplantación)', F));

if (dmarc === 'fail') hz.push(H('autenticacion', 'dmarc_fail', dmarc, 'alta', 22, 'DMARC fail: la alineación de dominio falló — el From visible no está respaldado por SPF/DKIM', F));
else if (dmarc === 'none' || dmarc === 'ausente') hz.push(H('autenticacion', 'dmarc_ausente', dmarc, 'baja', 4, 'Sin evaluación DMARC', F));

// --- Coherencia de identidades ---
if (c.reply_to.direccion && c.reply_to.dominio_registrable !== c.from.dominio_registrable)
  hz.push(H('identidad', 'reply_to_distinto', c.reply_to.direccion, 'alta', 18, 'Reply-To (' + c.reply_to.dominio + ') difiere del From (' + c.from.dominio + '): las respuestas van a otro lado', F));
if (c.return_path.direccion && c.return_path.dominio_registrable !== c.from.dominio_registrable)
  hz.push(H('identidad', 'return_path_distinto', c.return_path.direccion, 'media', 10, 'Return-Path (' + c.return_path.dominio + ') difiere del From: envío por infraestructura ajena al dominio', F));

// Display name que contiene un email/dominio distinto al real ("juan@ejercito.mil.ar" <x@gmail.com>)
const nombre = (c.from.nombre || '').toLowerCase();
const emailEnNombre = /[\w.+-]+@([\w.-]+)/.exec(nombre);
if (emailEnNombre && registrable(emailEnNombre[1]) !== c.from.dominio_registrable)
  hz.push(H('identidad', 'display_name_con_otro_email', c.from.nombre, 'alta', 22, 'El nombre visible muestra una dirección distinta a la real (' + c.from.direccion + ')', F));

// Freemail haciéndose pasar por institución
const esFreemailFrom = esFreemail(c.from.dominio_registrable);
if (c.reply_to.direccion && esFreemail(c.reply_to.dominio_registrable) && !esFreemailFrom)
  hz.push(H('identidad', 'reply_to_freemail', c.reply_to.direccion, 'alta', 12, 'Reply-To en cuenta gratuita (' + c.reply_to.dominio + '): el atacante recibe las respuestas fuera de la organización', F));
const nombreInstitucional = /(ejercito|ej[eé]rcito|comando|jefatura|estado mayor|ministerio|defensa|gobierno|banco|soporte|seguridad|administraci[oó]n|rrhh|recursos humanos|mesa de ayuda|helpdesk|it |sistemas|tesorer[ií]a|haberes|anses|afip|arca|mercado ?pago)/i.test(nombre);
if (esFreemailFrom && nombreInstitucional)
  hz.push(H('identidad', 'freemail_institucional', c.from.direccion, 'alta', 20, 'Nombre visible institucional ("' + c.from.nombre + '") desde una cuenta gratuita ' + c.from.dominio, F));
else if (esFreemailFrom) hz.push(H('identidad', 'freemail', c.from.dominio, 'info', 2, 'Remitente desde proveedor gratuito', F));

// Nombre visible que menciona una marca cuyo dominio no coincide
const nombreSinEsp = nombre.replace(/[^a-z0-9]/g, '');
for (const marca of MARCAS) {
  if (marca.length >= 4 && nombreSinEsp.includes(marca) && !c.from.dominio_registrable.replace(/[^a-z0-9]/g, '').includes(marca)) {
    hz.push(H('identidad', 'nombre_marca_dominio_ajeno', c.from.nombre + ' <' + c.from.direccion + '>', 'media', 12, 'El nombre visible invoca "' + marca + '" pero el dominio real es ' + c.from.dominio, F));
    break;
  }
}

// Dominio propio en nombre visible pero From externo (suplantación interna)
for (const dp of cfg.dominios_propios) {
  const etiqueta = dp.split('.')[0];
  if (etiqueta.length >= 4 && nombreSinEsp.includes(etiqueta) && c.from.dominio_registrable !== dp && !c.from.dominio.endsWith('.' + dp)) {
    hz.push(H('identidad', 'suplantacion_interna', c.from.direccion, 'alta', 20, 'Se presenta como "' + c.from.nombre + '" (dominio propio ' + dp + ') pero envía desde ' + c.from.dominio, F));
    break;
  }
}
if (/xn--/.test(c.from.dominio)) hz.push(H('identidad', 'punycode_from', c.from.dominio, 'alta', 18, 'Dominio remitente con Punycode (posible homógrafo IDN)', F));

// --- Anomalías de cabeceras ---
if (!c.message_id) hz.push(H('cabeceras', 'sin_message_id', '', 'media', 8, 'Falta Message-ID (herramientas de envío masivo / scripts)', F));
else {
  const midDom = (/@([\w.-]+)>?$/.exec(c.message_id) || [null, ''])[1].toLowerCase();
  if (midDom && !esFreemailFrom && registrable(midDom) !== c.from.dominio_registrable && !/^[\d.]+$/.test(midDom))
    hz.push(H('cabeceras', 'message_id_dominio_distinto', c.message_id, 'baja', 5, 'Message-ID generado en ' + midDom + ', no en el dominio del From', F));
}
if (!c.date) hz.push(H('cabeceras', 'sin_fecha', '', 'baja', 4, 'Falta cabecera Date', F));
else { const t = Date.parse(c.date); if (!isNaN(t) && (t - Date.now()) > 3600e3 * 6) hz.push(H('cabeceras', 'fecha_futura', c.date, 'media', 6, 'Fecha del mensaje en el futuro', F)); }
const xm = ((c.cabeceras['x-mailer'] || c.cabeceras['user-agent'] || [''])[0]);
if (/phpmailer|swiftmailer|sendblaster|mass|bulk|python-?smtplib|nodemailer|go-?mail/i.test(xm)) hz.push(H('cabeceras', 'x_mailer_scripting', xm, 'media', 8, 'Cliente de envío automatizado/masivo', F));
if (c.cabeceras['x-priority'] && /^(1|2)/.test(c.cabeceras['x-priority'][0])) hz.push(H('cabeceras', 'prioridad_alta', c.cabeceras['x-priority'][0], 'baja', 3, 'Marcado como prioridad alta (presión al usuario)', F));
if (c.n_saltos === 0) hz.push(H('cabeceras', 'sin_received', '', 'media', 6, 'Sin cadena Received: origen no rastreable (o entrada sintética)', F));
if (c.n_saltos > 8) hz.push(H('cabeceras', 'muchos_saltos', c.n_saltos, 'baja', 3, 'Cadena Received inusualmente larga', F));
if (c.correos_anidados > 0) hz.push(H('cabeceras', 'correo_anidado', c.correos_anidados, 'baja', 4, 'Contiene correos adjuntos (message/rfc822), técnica para evadir filtros', F));
if (c.cabeceras['list-unsubscribe']) hz.push(H('cabeceras', 'lista_masiva', '', 'info', 1, 'Tiene List-Unsubscribe (envío masivo/newsletter)', F));
if (!c.from.direccion) hz.push(H('identidad', 'sin_from', '', 'alta', 15, 'Sin dirección From', F));

// Destinatario: ¿el To coincide con la bandeja o va a "undisclosed-recipients"?
if (/undisclosed|destinatarios? no revelados/i.test(c.to || '') || !c.to) hz.push(H('cabeceras', 'destinatarios_ocultos', c.to, 'media', 6, 'Destinatarios ocultos o ausentes (envío masivo BCC)', F));

// Correo interno legítimo (de dominio propio con SPF/DKIM pass) => señal a favor
if (cfg.dominios_propios.includes(c.from.dominio_registrable) && spf === 'pass' && dkim === 'pass')
  hz.push(H('identidad', 'interno_autenticado', c.from.direccion, 'info', -15, 'Remitente de dominio propio con SPF y DKIM válidos', F));
else if (spf === 'pass' && dkim === 'pass' && dmarc === 'pass')
  hz.push(H('autenticacion', 'auth_completa', c.from.dominio, 'info', -8, 'SPF, DKIM y DMARC en pass: la identidad del dominio es verificable', F));

return salida(F, 'ok', {
  spf, dkim, dmarc, dkim_dominio: c.auth.dkim_dominio,
  from: c.from.direccion, reply_to: c.reply_to.direccion || null, return_path: c.return_path.direccion || null,
  saltos: c.n_saltos, ips_en_cadena: d.artefactos.ips, x_mailer: xm || null, freemail: esFreemailFrom
}, hz);

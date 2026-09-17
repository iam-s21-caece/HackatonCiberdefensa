// =====================================================================
//  NODO: Consolidar evidencia y puntuar
//  Junta las 10 fuentes, calcula un score determinístico (0-100),
//  aplica reglas duras y arma el prompt para la IA.
// =====================================================================
const base = $('Desarmar correo').first().json;
const fuentes = {};
let hallazgos = [];
for (const it of $input.all()) {
  const f = it.json || {};
  if (!f.fuente) continue;
  fuentes[f.fuente] = { estado: f.estado, consultas: f.consultas || 0, nota: f.nota, resultados: f.resultados };
  hallazgos = hallazgos.concat(f.hallazgos || []);
}
const ORDEN = { critica: 5, alta: 4, media: 3, baja: 2, info: 1 };
hallazgos.sort((a, b) => (ORDEN[b.severidad] || 0) - (ORDEN[a.severidad] || 0) || Math.abs(b.peso) - Math.abs(a.peso));

// --- score: suma de pesos, con rendimientos decrecientes por categoría para que
//     10 palabras clave no pesen como un hash de malware ---
const porCategoria = {};
for (const h of hallazgos) (porCategoria[h.categoria] = porCategoria[h.categoria] || []).push(h.peso);
let score = 0;
const TOPE = { ingenieria_social: 30, url: 35, html: 35, cabeceras: 20, autenticacion: 40, identidad: 40, lookalike: 45, adjunto: 50, inteligencia: 100, infraestructura: 40, dns: 40, contexto: 20 };
const detalleScore = {};
for (const [cat, pesos] of Object.entries(porCategoria)) {
  const pos = pesos.filter(p => p > 0).sort((a, b) => b - a);
  const neg = pesos.filter(p => p < 0).reduce((s, p) => s + p, 0);
  let sub = 0; pos.forEach((p, i) => { sub += p * (i === 0 ? 1 : i === 1 ? 0.7 : i === 2 ? 0.5 : 0.3); });
  sub = Math.min(sub, TOPE[cat] || 30) + neg;
  detalleScore[cat] = Math.round(sub); score += sub;
}
score = Math.max(0, Math.min(100, Math.round(score)));

// --- reglas duras: evidencia que por sí sola decide ---
const reglas_duras = [];
const tipos = new Set(hallazgos.map(h => h.tipo));
if (tipos.has('malwarebazaar_muestra_conocida') || tipos.has('vt_archivo_malicioso')) reglas_duras.push('adjunto_malware_conocido');
if (tipos.has('urlhaus_url_maliciosa') || tipos.has('threatfox_ioc') || tipos.has('vt_url_maliciosa') || tipos.has('vt_dominio_malicioso')) reglas_duras.push('ioc_confirmado_por_inteligencia');
if (tipos.has('ejecutable') || tipos.has('doble_extension') || tipos.has('unicode_rtl')) reglas_duras.push('adjunto_ejecutable');
if (tipos.has('campo_password')) reglas_duras.push('captura_de_credenciales_embebida');
if (tipos.has('dominio_propio_similar') && (tipos.has('spf_fail') || tipos.has('dmarc_fail') || tipos.has('dkim_fail') || tipos.has('spf_ausente'))) reglas_duras.push('suplantacion_de_dominio_propio');
if (tipos.has('dominio_inexistente')) reglas_duras.push('remitente_inexistente');
if (tipos.has('intento_secuestro_cuenta') && ['enlace_de_numero_desconocido', 'numero_extranjero', 'remitente_alfanumerico', 'nombre_institucional_mensaje', 'grado_militar_en_perfil', 'suplantacion_interna_mensaje'].some(t => tipos.has(t))) reglas_duras.push('secuestro_de_cuenta');
const cont = base.correo;
const canal = base.canal || 'email';
const CANAL_TXT = { email: 'correo electrónico', whatsapp: 'mensaje de WhatsApp', sms: 'SMS' }[canal] || canal;
if (tipos.has('interno_autenticado') && score < 25) reglas_duras.push('interno_autenticado_limpio');

const nivel = score >= 70 ? 'CRITICO' : score >= 45 ? 'ALTO' : score >= 25 ? 'MEDIO' : 'BAJO';
let veredicto_reglas = score >= 65 ? 'VERDADERO_POSITIVO' : score >= 30 ? 'ESCALAR' : 'FALSO_POSITIVO';
if (reglas_duras.some(r => r !== 'interno_autenticado_limpio')) veredicto_reglas = 'VERDADERO_POSITIVO';
else if (reglas_duras.includes('interno_autenticado_limpio')) veredicto_reglas = 'FALSO_POSITIVO';

// --- IOCs defanged para el SOC ---
const A = base.artefactos;
const iocs = {
  remitente: defang(cont.from.direccion), reply_to: cont.reply_to.direccion ? defang(cont.reply_to.direccion) : null,
  ips: A.ips.map(defang), dominios: A.dominios.map(defang), urls: A.urls.map(u => defang(u.url)),
  adjuntos: A.adjuntos.map(a => ({ nombre: a.nombre, sha256: a.sha256, md5: a.md5, tamano: a.tamano }))
};
const fuentes_ok = Object.entries(fuentes).filter(([, v]) => /^ok|parcial/.test(v.estado)).map(([k]) => k);
const fuentes_sin_key = Object.entries(fuentes).filter(([, v]) => v.estado === 'sin_api_key').map(([k]) => k);
const fuentes_error = Object.entries(fuentes).filter(([, v]) => /error|timeout/.test(v.estado)).map(([k]) => k);

// --- prompt para la IA (Ollama local, salida JSON forzada) ---
const evidencia = {
  // (compacta a propósito: en CPU cada token del prompt cuesta tiempo; lo importante ya está resumido en hallazgos)
  canal: CANAL_TXT,
  remitente_telefonico: base.mensaje ? { numero: base.mensaje.numero_origen, nombre_perfil: base.mensaje.nombre_contacto, pais: base.mensaje.telefono && base.mensaje.telefono.pais, alfanumerico: base.mensaje.telefono && base.mensaje.telefono.alfanumerico, registrado_como_propio: base.mensaje.telefono && base.mensaje.telefono.propio } : undefined,
  correo: { de: cont.from.raw, responder_a: cont.reply_to.raw || null, para: cont.to, asunto: cont.subject, fecha: cont.date, autenticacion: { spf: cont.auth.spf, dkim: cont.auth.dkim, dmarc: cont.auth.dmarc }, cuerpo: (cont.cuerpo || '').slice(0, 1200) },
  artefactos: { ips: A.ips, dominios: A.dominios, urls: A.urls.slice(0, 8).map(u => ({ url: u.url.slice(0, 160), texto: (u.texto_ancla || '').slice(0, 80) })), adjuntos: A.adjuntos.map(a => ({ nombre: a.nombre, tipo: a.mime, sha256: a.sha256 })) },
  motor_de_reglas: { score, nivel, veredicto_sugerido: veredicto_reglas, reglas_duras, score_por_categoria: detalleScore },
  hallazgos: hallazgos.filter(h => h.severidad !== 'info').slice(0, 30).map(h => ({ sev: h.severidad, tipo: h.tipo, valor: h.valor.slice(0, 100), detalle: h.detalle.slice(0, 160), fuente: h.fuente })),
  fuentes: { consultadas_ok: fuentes_ok, sin_api_key: fuentes_sin_key, con_error: fuentes_error }
};
const system = `Sos CENTINELA, analista senior de un SOC de ciberdefensa militar argentino. Recibís la evidencia consolidada de un ${CANAL_TXT} (ya desarmado y enriquecido con inteligencia de amenazas) y tenés que decidir cómo tratarlo.
Veredictos posibles:
- VERDADERO_POSITIVO: phishing / smishing / malware / fraude / intento de secuestro de cuenta confirmado. Se bloquea y se alerta.
- FALSO_POSITIVO: mensaje legítimo. Se entrega al usuario.
- ESCALAR: evidencia insuficiente o contradictoria. Lo revisa un investigador humano.
Reglas: basate SOLO en la evidencia dada, no inventes datos. Si faltan fuentes (sin_api_key/con_error) bajá tu confianza. Un hash o URL confirmado por inteligencia de amenazas pesa más que cualquier palabra clave. En correo, un remitente interno con SPF/DKIM pass y sin vector de ataque suele ser legítimo. En WhatsApp/SMS no hay autenticación: pesan el número (país, registrado o no, ID alfanumérico), el nombre de perfil que imita a una institución, los enlaces y el pedido de códigos o datos. Ante la duda, ESCALAR (nunca entregar algo peligroso, nunca bloquear sin evidencia). Escribí en español rioplatense, claro y breve.
Respondé ÚNICAMENTE con un JSON con este esquema exacto:
{"veredicto":"VERDADERO_POSITIVO|FALSO_POSITIVO|ESCALAR","confianza":0.0-1.0,"tipo_amenaza":"phishing_credenciales|malware_adjunto|fraude_bec|smishing|secuestro_cuenta|estafa_mensajeria|spam|legitimo|indeterminado","resumen":"2-3 oraciones para el analista","indicadores_clave":["..."],"acciones_recomendadas":["..."],"mitre_attack":["T1566.002 Spearphishing Link", "..."],"mensaje_para_usuario":"1 oración en lenguaje simple para el destinatario"}`;

const ollama_request = {
  model: base.config.ollama_model, stream: false, format: 'json', options: { temperature: 0.1, num_ctx: 8192 }, keep_alive: '30m',
  messages: [{ role: 'system', content: system }, { role: 'user', content: 'EVIDENCIA:\n' + JSON.stringify(evidencia) }]
};
// Proveedor de la IA: Ollama local o DeepSeek (API compatible con OpenAI, modo JSON). La API key NO viaja en el
// ítem: el nodo HTTP la toma de $env al armar la cabecera, así nunca queda en el reporte.
const ia_request = base.config.ia_proveedor === 'deepseek'
  ? { proveedor: 'deepseek', modelo: base.config.deepseek_model, url: base.config.deepseek_url + '/chat/completions',
      body: { model: base.config.deepseek_model, messages: ollama_request.messages, temperature: 0.1, stream: false, response_format: { type: 'json_object' } } }
  : { proveedor: 'ollama', modelo: base.config.ollama_model, url: base.config.ollama_url + '/api/chat', body: ollama_request };

return [{
  json: {
    report_id: base.report_id, recibido_en: base.recibido_en, origen_entrada: base.origen_entrada, canal, mensaje: base.mensaje || null, notas_parser: base.notas_parser, config: base.config,
    correo: { de: cont.from, reply_to: cont.reply_to, return_path: cont.return_path, para: cont.to, asunto: cont.subject, fecha: cont.date, message_id: cont.message_id, auth: { spf: cont.auth.spf, dkim: cont.auth.dkim, dmarc: cont.auth.dmarc, dkim_dominio: cont.auth.dkim_dominio }, saltos: cont.n_saltos, cuerpo_muestra: (cont.cuerpo || '').slice(0, 3000) },
    artefactos: A, iocs_defanged: iocs,
    score, nivel, veredicto_reglas, reglas_duras, score_por_categoria: detalleScore,
    hallazgos, n_hallazgos: hallazgos.length,
    fuentes, fuentes_ok, fuentes_sin_key, fuentes_error,
    ollama_request, ia_request
  }
}];

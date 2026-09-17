// =====================================================================
//  NODO: Interpretar veredicto IA + guardrails
//  La IA propone; el motor de reglas tiene poder de veto. Nunca se
//  entrega un correo con evidencia dura, y nunca se bloquea sin evidencia.
// =====================================================================
const base = $('Consolidar evidencia y puntuar').first().json;
const resp = $input.first().json || {};
const pedido = base.ia_request || { proveedor: 'ollama', modelo: base.config.ollama_model };
let ia = { disponible: false, proveedor: pedido.proveedor, modelo: pedido.modelo, error: null, veredicto: null, confianza: null, tipo_amenaza: null, resumen: null, indicadores_clave: [], acciones_recomendadas: [], mitre_attack: [], mensaje_para_usuario: null, duracion_ms: null };
try {
  let content = resp.message && resp.message.content;                                   // Ollama
  if (!content && Array.isArray(resp.choices) && resp.choices[0] && resp.choices[0].message) content = resp.choices[0].message.content;  // DeepSeek / OpenAI
  if (!content && resp.response) content = resp.response;
  if (resp.error && !content) throw new Error(typeof resp.error === 'string' ? resp.error : (resp.error.message || JSON.stringify(resp.error)).slice(0, 300));
  if (!content) throw new Error('Respuesta vacía del modelo');
  content = String(content).replace(/^```(?:json)?/i, '').replace(/```$/, '').trim();
  const m = content.indexOf('{'); if (m > 0) content = content.slice(m);
  const p = JSON.parse(content);
  const v = String(p.veredicto || '').toUpperCase().replace(/\s+/g, '_');
  ia.veredicto = ['VERDADERO_POSITIVO', 'FALSO_POSITIVO', 'ESCALAR'].includes(v) ? v : null;
  ia.confianza = typeof p.confianza === 'number' ? Math.max(0, Math.min(1, p.confianza)) : (parseFloat(p.confianza) || null);
  ia.tipo_amenaza = p.tipo_amenaza || null; ia.resumen = p.resumen || null; ia.mensaje_para_usuario = p.mensaje_para_usuario || null;
  ia.indicadores_clave = Array.isArray(p.indicadores_clave) ? p.indicadores_clave : []; ia.acciones_recomendadas = Array.isArray(p.acciones_recomendadas) ? p.acciones_recomendadas : []; ia.mitre_attack = Array.isArray(p.mitre_attack) ? p.mitre_attack : [];
  ia.disponible = !!ia.veredicto;
  ia.duracion_ms = resp.total_duration ? Math.round(resp.total_duration / 1e6) : null;
  if (!ia.veredicto) ia.error = 'La IA no devolvió un veredicto válido';
} catch (e) { ia.error = String(e.message || e); }

// --- guardrails ---
const motivos = [];
let final = ia.disponible ? ia.veredicto : base.veredicto_reglas;
const duras = base.reglas_duras.filter(r => r !== 'interno_autenticado_limpio');
if (!ia.disponible) motivos.push('IA no disponible (' + ia.error + '): se usa el veredicto del motor de reglas');
if (duras.length && final !== 'VERDADERO_POSITIVO') { final = 'VERDADERO_POSITIVO'; motivos.push('Regla dura activada (' + duras.join(', ') + '): la IA no puede degradar evidencia confirmada'); }
if (ia.disponible && ia.veredicto === 'FALSO_POSITIVO' && base.score >= 55) { final = 'ESCALAR'; motivos.push('La IA dijo FALSO_POSITIVO pero el score determinístico es ' + base.score + ': desacuerdo -> revisa un humano'); }
if (ia.disponible && ia.veredicto === 'VERDADERO_POSITIVO' && base.score < 20 && !duras.length) { final = 'ESCALAR'; motivos.push('La IA dijo VERDADERO_POSITIVO con score bajo (' + base.score + ') y sin reglas duras: se escala en vez de bloquear'); }
if (ia.disponible && ia.confianza != null && ia.confianza < 0.55 && !duras.length && final !== 'ESCALAR') { final = 'ESCALAR'; motivos.push('Confianza de la IA baja (' + ia.confianza + ')'); }
if (base.fuentes_ok.length <= 2 && final === 'FALSO_POSITIVO' && base.score >= 15) { final = 'ESCALAR'; motivos.push('Pocas fuentes de inteligencia disponibles para confirmar que es limpio'); }
if (!motivos.length) motivos.push(ia.disponible ? 'IA y motor de reglas coinciden' : 'Motor de reglas');

const esMensaje = base.canal && base.canal !== 'email';
const MITRE_BASE = { phishing_credenciales: ['T1566.002 Spearphishing Link', 'T1598.003 Spearphishing Link (info)', 'T1056.003 Web Portal Capture'], malware_adjunto: ['T1566.001 Spearphishing Attachment', 'T1204.002 User Execution: Malicious File'], fraude_bec: ['T1566.003 Spearphishing via Service', 'T1534 Internal Spearphishing', 'T1656 Impersonation'],
  smishing: ['T1660 Phishing (Mobile)', 'T1566.002 Spearphishing Link'], secuestro_cuenta: ['T1660 Phishing (Mobile)', 'T1111 Multi-Factor Authentication Interception', 'T1656 Impersonation'], estafa_mensajeria: ['T1660 Phishing (Mobile)', 'T1656 Impersonation'],
  spam: [], legitimo: [], indeterminado: ['T1566 Phishing'] };
if (final === 'FALSO_POSITIVO') ia.mitre_attack = [];   // un mensaje legítimo no tiene técnica de ataque (los modelos chicos a veces inventan IDs)
else if (!ia.mitre_attack.length) ia.mitre_attack = MITRE_BASE[ia.tipo_amenaza] || (esMensaje ? MITRE_BASE.smishing : MITRE_BASE.indeterminado);
else {
  // Sólo técnicas ATT&CK reales y pertinentes a phishing/mensajería: los modelos chicos inventan IDs con formato válido
  const VALIDAS = new Set(['T1566', 'T1566.001', 'T1566.002', 'T1566.003', 'T1566.004', 'T1598', 'T1598.001', 'T1598.002', 'T1598.003', 'T1598.004', 'T1660', 'T1656', 'T1204', 'T1204.001', 'T1204.002', 'T1204.003', 'T1534', 'T1111', 'T1056.003', 'T1036', 'T1036.005', 'T1027', 'T1071', 'T1071.001', 'T1105', 'T1078', 'T1552', 'T1539', 'T1550', 'T1114', 'T1583', 'T1583.001', 'T1583.006', 'T1584', 'T1585', 'T1585.002', 'T1586', 'T1586.002', 'T1608', 'T1608.005', 'T1189']);
  ia.mitre_attack = ia.mitre_attack.filter(t => { const m = /^(T1\d{3}(?:\.\d{3})?)\b/.exec(String(t)); return m && VALIDAS.has(m[1]); });
  if (!ia.mitre_attack.length) ia.mitre_attack = MITRE_BASE[ia.tipo_amenaza] || (esMensaje ? MITRE_BASE.smishing : MITRE_BASE.indeterminado);
}
// En WhatsApp/SMS la técnica de entrega es siempre phishing móvil (el modelo tiende a copiar la de correo)
if (esMensaje && final !== 'FALSO_POSITIVO') {
  ia.mitre_attack = ia.mitre_attack.slice();
  if (!ia.mitre_attack.some(t => /^T1660\b/.test(t))) ia.mitre_attack.unshift('T1660 Phishing (Mobile)');
  if ((ia.tipo_amenaza === 'secuestro_cuenta' || base.reglas_duras.includes('secuestro_de_cuenta')) && !ia.mitre_attack.some(t => /^T1111\b/.test(t))) ia.mitre_attack.push('T1111 Multi-Factor Authentication Interception');
}

const ACCION = { VERDADERO_POSITIVO: 'CUARENTENA_Y_ALERTA', ESCALAR: 'COLA_INVESTIGADOR', FALSO_POSITIVO: 'ENTREGAR' };
const out = Object.assign({}, base);
delete out.ollama_request;
delete out.ia_request;
// El reporte lo leen el Agente 2 y el dashboard: las claves y el webhook del SOC sólo figuran como configurados.
out.config = Object.assign({}, base.config);
for (const k of ['vt_api_key', 'abuseipdb_api_key', 'abusech_api_key', 'soc_webhook_url']) out.config[k] = base.config[k] ? 'configurada' : '';
out.ia = ia;
out.veredicto_final = final;
out.accion = ACCION[final];
out.motivo_veredicto = motivos;
out.resumen_ejecutivo = {
  report_id: base.report_id, canal: base.canal || 'email', veredicto: final, accion: ACCION[final], score: base.score, nivel: base.nivel,
  de: base.correo.de.direccion, asunto: base.correo.asunto,
  hallazgos_criticos_altos: base.hallazgos.filter(h => h.severidad === 'critica' || h.severidad === 'alta').length,
  ia_resumen: ia.resumen, ia_confianza: ia.confianza, mitre: ia.mitre_attack, fuentes_ok: base.fuentes_ok
};
return [{ json: out }];

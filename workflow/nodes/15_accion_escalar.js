// =====================================================================
//  ACCIÓN: ESCALAR -> cola del investigador (human-in-the-loop)
//  El correo queda retenido hasta que un analista decida. Acá se
//  integra un ticket (TheHive/Jira/GLPI) vía SOC_WEBHOOK_URL.
// =====================================================================
const r = $('Interpretar veredicto IA + guardrails').first().json;
const ticket = {
  ts: new Date().toISOString(), report_id: r.report_id, canal: r.canal || 'email', accion: 'RETENER_Y_ESCALAR', estado: 'PENDIENTE_REVISION', prioridad: r.nivel === 'ALTO' || r.nivel === 'CRITICO' ? 'P2' : 'P3',
  de: r.correo.de.direccion, reply_to: r.correo.reply_to.direccion || null, asunto: r.correo.asunto, para: r.correo.para, score: r.score, nivel: r.nivel,
  por_que_se_escala: r.motivo_veredicto, ia: { veredicto: r.ia.veredicto, confianza: r.ia.confianza, resumen: r.ia.resumen }, veredicto_reglas: r.veredicto_reglas,
  que_revisar: r.hallazgos.filter(h => h.severidad !== 'info').slice(0, 10).map(h => h.severidad.toUpperCase() + ' ' + h.tipo + ': ' + h.detalle),
  fuentes_faltantes: r.fuentes_sin_key.concat(r.fuentes_error), iocs: r.iocs_defanged, reporte: '/data/reports/' + r.report_id + '.json'
};
let soc = { enviado: false };
const socUrl = $('Consolidar evidencia y puntuar').first().json.config.soc_webhook_url;  // en el reporte está enmascarado
if (socUrl) {
  const texto = ':mag: *CENTINELA - REVISIÓN REQUERIDA* (' + ticket.prioridad + ', score ' + r.score + ')\n*De:* ' + ticket.de + '\n*Asunto:* ' + ticket.asunto + '\n*Motivo:* ' + r.motivo_veredicto.join(' | ') + '\n*Reporte:* ' + r.report_id;
  const w = await httpJson({ method: 'POST', url: socUrl, body: { text: texto, content: texto, centinela: ticket }, timeout: 10000 });
  soc = { enviado: w.ok, http: w.status, error: w.error || null };
}
return [{ json: { report_id: r.report_id, accion: 'RETENER_Y_ESCALAR', veredicto: r.veredicto_final, soc, linea: JSON.stringify(ticket) + '\n' } }];

// =====================================================================
//  ACCIÓN: VERDADERO_POSITIVO -> cuarentena + alerta al SOC
//  Acá se conecta el gateway real (Exchange/Postfix/Proxmox MG) para
//  mover el correo a cuarentena. En el MVP: registro + webhook al SOC.
// =====================================================================
const r = $('Interpretar veredicto IA + guardrails').first().json;
const alerta = {
  ts: new Date().toISOString(), report_id: r.report_id, canal: r.canal || 'email', accion: 'CUARENTENA', veredicto: r.veredicto_final, score: r.score, nivel: r.nivel,
  de: r.correo.de.direccion, reply_to: r.correo.reply_to.direccion || null, asunto: r.correo.asunto, para: r.correo.para,
  tipo_amenaza: r.ia.tipo_amenaza, resumen: r.ia.resumen, mitre: r.ia.mitre_attack, reglas_duras: r.reglas_duras,
  iocs: r.iocs_defanged, top_hallazgos: r.hallazgos.slice(0, 8).map(h => h.severidad.toUpperCase() + ' ' + h.tipo + ': ' + h.detalle),
  acciones_recomendadas: r.ia.acciones_recomendadas, motivo: r.motivo_veredicto
};
let soc = { enviado: false };
const socUrl = $('Consolidar evidencia y puntuar').first().json.config.soc_webhook_url;  // en el reporte está enmascarado
if (socUrl) {
  const texto = ':rotating_light: *CENTINELA - PHISHING BLOQUEADO* (' + r.nivel + ', score ' + r.score + ')\n*De:* ' + alerta.de + '\n*Asunto:* ' + alerta.asunto + '\n*IA:* ' + (alerta.resumen || 's/d') + '\n*IOCs:* ' + r.iocs_defanged.urls.slice(0, 3).join(', ') + '\n*Reporte:* ' + r.report_id;
  const w = await httpJson({ method: 'POST', url: socUrl, body: { text: texto, content: texto, centinela: alerta }, timeout: 10000 });
  soc = { enviado: w.ok, http: w.status, error: w.error || null };
}
return [{ json: { report_id: r.report_id, accion: 'CUARENTENA', veredicto: r.veredicto_final, soc, linea: JSON.stringify(alerta) + '\n' } }];

// =====================================================================
//  ACCIÓN: FALSO_POSITIVO -> entregar al usuario y registrar
//  Se guarda igual la traza para auditoría y para reentrenar umbrales.
// =====================================================================
const r = $('Interpretar veredicto IA + guardrails').first().json;
const reg = {
  ts: new Date().toISOString(), report_id: r.report_id, canal: r.canal || 'email', accion: 'ENTREGAR', veredicto: r.veredicto_final, score: r.score, nivel: r.nivel,
  de: r.correo.de.direccion, asunto: r.correo.asunto, para: r.correo.para,
  ia: { confianza: r.ia.confianza, resumen: r.ia.resumen }, motivo: r.motivo_veredicto,
  senales_residuales: r.hallazgos.filter(h => h.severidad === 'media' || h.severidad === 'alta').slice(0, 5).map(h => h.tipo)
};
return [{ json: { report_id: r.report_id, accion: 'ENTREGAR', veredicto: r.veredicto_final, soc: { enviado: false }, linea: JSON.stringify(reg) + '\n' } }];

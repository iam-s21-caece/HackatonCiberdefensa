// =====================================================================
//  NODO: ThreatFox (abuse.ch) - IOCs de C2 / botnets / phishing kits
// =====================================================================
const d = $input.first().json;
const A = d.artefactos, cfg = d.config, key = cfg.abusech_api_key;
const hz = [], res = {};
const F = 'threatfox';
const iocs = uniq(A.dominios.filter(x => !cfg.dominios_propios.includes(x)).slice(0, LIM.dominios).concat(A.ips.slice(0, LIM.ips)).concat(A.hashes.slice(0, LIM.hashes)));
if (!iocs.length) return salida(F, 'sin_artefactos', res, hz);
if (!key) return salida(F, 'sin_api_key', res, hz, { nota: 'Definí ABUSECH_API_KEY (gratis en auth.abuse.ch) para habilitar esta fuente' });
let consultas = 0, auth_fail = false;
for (const ioc of iocs) {
  consultas++;
  const r = await httpJson({ method: 'POST', url: 'https://threatfox-api.abuse.ch/api/v1/', headers: { 'Auth-Key': key, 'Content-Type': 'application/json' }, body: { query: 'search_ioc', search_term: ioc, exact_match: true } });
  if (r.status === 401 || r.status === 403) { auth_fail = true; break; }
  const x = r.data || {};
  if (x.query_status === 'ok' && Array.isArray(x.data) && x.data.length) {
    const m = x.data[0];
    res[ioc] = { estado: 'conocido', tipo_amenaza: m.threat_type, malware: m.malware_printable, confianza: m.confidence_level, primera_vez: m.first_seen, etiquetas: m.tags, referencia: m.reference };
    hz.push(H('inteligencia', 'threatfox_ioc', ioc, 'critica', 40, 'ThreatFox: IOC asociado a ' + (m.malware_printable || m.threat_type || 'amenaza') + ' (confianza ' + m.confidence_level + '%)', F));
  } else res[ioc] = { estado: x.query_status || 'sin_datos' };
}
return salida(F, auth_fail ? 'sin_api_key' : 'ok', res, hz, { consultas });

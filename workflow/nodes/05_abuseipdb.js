// =====================================================================
//  NODO: AbuseIPDB (reputación de IPs de la cadena de envío)
// =====================================================================
const d = $input.first().json;
const A = d.artefactos, key = d.config.abuseipdb_api_key;
const hz = [], res = {};
const F = 'abuseipdb';
if (!key) return salida(F, 'sin_api_key', res, hz, { nota: 'Definí ABUSEIPDB_API_KEY (gratis, 1000 checks/día) para habilitar esta fuente' });
if (!A.ips.length) return salida(F, 'sin_artefactos', res, hz);

let consultas = 0;
for (const ip of A.ips.slice(0, LIM.ips)) {
  consultas++;
  const r = await httpJson({ method: 'GET', url: 'https://api.abuseipdb.com/api/v2/check', qs: { ipAddress: ip, maxAgeInDays: 90, verbose: '' }, headers: { Key: key, Accept: 'application/json' } });
  if (!r.ok || !r.data || !r.data.data) { res[ip] = { estado: 'error', http: r.status, error: r.error || (r.data && r.data.errors) }; continue; }
  const x = r.data.data;
  res[ip] = { estado: 'ok', confianza_abuso: x.abuseConfidenceScore, reportes: x.totalReports, pais: x.countryCode, isp: x.isp, dominio: x.domain, tor: x.isTor, tipo_uso: x.usageType, ultimo_reporte: x.lastReportedAt, hostnames: x.hostnames };
  if (x.abuseConfidenceScore >= 75) hz.push(H('inteligencia', 'ip_abuso_alto', ip, 'alta', 25, 'AbuseIPDB: confianza de abuso ' + x.abuseConfidenceScore + '% (' + x.totalReports + ' reportes, ' + (x.isp || '') + ', ' + (x.countryCode || '') + ')', F));
  else if (x.abuseConfidenceScore >= 25) hz.push(H('inteligencia', 'ip_abuso_medio', ip, 'media', 12, 'AbuseIPDB: confianza de abuso ' + x.abuseConfidenceScore + '% (' + x.totalReports + ' reportes)', F));
  else if (x.totalReports > 0) hz.push(H('inteligencia', 'ip_con_reportes', ip, 'baja', 4, x.totalReports + ' reportes históricos de abuso', F));
  if (x.isTor) hz.push(H('inteligencia', 'ip_tor', ip, 'alta', 15, 'La IP es un nodo de salida Tor', F));
  if (/hosting|data center|vps/i.test(x.usageType || '') && A.ips.indexOf(ip) === 0) hz.push(H('inteligencia', 'ip_hosting', ip, 'baja', 4, 'Origen en hosting/VPS (' + x.usageType + ') en lugar de infraestructura de correo', F));
}
return salida(F, 'ok', res, hz, { consultas });

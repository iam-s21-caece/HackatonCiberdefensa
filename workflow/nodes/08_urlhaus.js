// =====================================================================
//  NODO: URLhaus (abuse.ch) - URLs y hosts de distribución de malware
//  Requiere Auth-Key gratuita de abuse.ch (auth.abuse.ch) desde 2025.
// =====================================================================
const d = $input.first().json;
const A = d.artefactos, cfg = d.config, key = cfg.abusech_api_key;
const hz = [], res = { urls: {}, hosts: {} };
const F = 'urlhaus';
if (!A.urls.length && !A.ips.length) return salida(F, 'sin_artefactos', res, hz);
const HDR = Object.assign({ 'Content-Type': 'application/x-www-form-urlencoded', Accept: 'application/json' }, key ? { 'Auth-Key': key } : {});
let consultas = 0, auth_fail = false;
async function uh(path, body) {
  consultas++;
  const r = await httpJson({ method: 'POST', url: 'https://urlhaus-api.abuse.ch/v1/' + path + '/', headers: HDR, body, json: false });
  if (r.status === 401 || r.status === 403) auth_fail = true;
  return r;
}
for (const u of A.urls.slice(0, LIM.urls)) {
  const r = await uh('url', 'url=' + encodeURIComponent(u.url));
  const x = r.data || {};
  if (!r.ok) { res.urls[u.url] = { estado: 'error', http: r.status }; continue; }
  res.urls[u.url] = { estado: x.query_status, amenaza: x.threat, estado_url: x.url_status, etiquetas: x.tags, fecha: x.date_added, reportes: x.blacklists };
  if (x.query_status === 'ok') hz.push(H('inteligencia', 'urlhaus_url_maliciosa', u.url, 'critica', 40, 'URLhaus: URL listada como ' + (x.threat || 'malware') + ' (' + (x.url_status || '') + ', tags: ' + ((x.tags || []).join(',') || '-') + ')', F));
}
const hosts = uniq(A.urls.map(u => u.host).concat(A.ips)).filter(h => !cfg.dominios_propios.some(dp => h === dp || h.endsWith('.' + dp))).slice(0, LIM.dominios);
for (const h of hosts) {
  const r = await uh('host', 'host=' + encodeURIComponent(h));
  const x = r.data || {};
  if (!r.ok) { res.hosts[h] = { estado: 'error', http: r.status }; continue; }
  res.hosts[h] = { estado: x.query_status, urls_maliciosas: x.url_count, primera_vez: x.firstseen, listas_negras: x.blacklists };
  if (x.query_status === 'ok' && Number(x.url_count) > 0) hz.push(H('inteligencia', 'urlhaus_host_malicioso', h, 'alta', 25, 'URLhaus: el host distribuyó ' + x.url_count + ' URLs maliciosas (desde ' + (x.firstseen || '?') + ')', F));
}
const estado = auth_fail ? 'sin_api_key' : 'ok';
return salida(F, estado, res, hz, { consultas, nota: auth_fail ? 'Definí ABUSECH_API_KEY (gratis en auth.abuse.ch)' : undefined });

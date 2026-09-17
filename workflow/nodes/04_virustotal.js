// =====================================================================
//  NODO: VirusTotal (IPs, dominios, URLs y hashes)  -  API v3
//  Cuota free: 4 req/min, 500/día -> se limitan artefactos por tipo.
// =====================================================================
const d = $input.first().json;
const A = d.artefactos, key = d.config.vt_api_key;
const hz = [], res = { ips: {}, dominios: {}, urls: {}, hashes: {}, errores: [] };
const F = 'virustotal';
if (!key) return salida(F, 'sin_api_key', res, hz, { nota: 'Definí VT_API_KEY (gratis en virustotal.com) para habilitar esta fuente' });

const HDR = { 'x-apikey': key, 'accept': 'application/json' };
let consultas = 0, rate_limited = false;
async function vt(path) {
  consultas++;
  const r = await httpJson({ method: 'GET', url: 'https://www.virustotal.com/api/v3/' + path, headers: HDR });
  if (r.status === 429) rate_limited = true;
  return r;
}
function stats(r) {
  const a = r.data && r.data.data && r.data.data.attributes; if (!a) return null;
  const s = a.last_analysis_stats || {};
  return { malicious: s.malicious || 0, suspicious: s.suspicious || 0, harmless: s.harmless || 0, undetected: s.undetected || 0, attrs: a };
}
function resumen(r, extra) {
  if (r.status === 404) return { estado: 'desconocido', nota: 'Sin registro en VirusTotal' };
  if (r.status === 429) return { estado: 'rate_limit' };
  if (r.status === 401 || r.status === 403) return { estado: 'api_key_invalida' };
  if (!r.ok) return { estado: 'error', http: r.status, error: r.error };
  const s = stats(r); if (!s) return { estado: 'sin_datos' };
  return Object.assign({ estado: 'ok', malicious: s.malicious, suspicious: s.suspicious, harmless: s.harmless, undetected: s.undetected }, extra ? extra(s.attrs) : {});
}
function pesoPorDetecciones(m, s, base) { return Math.min(base + m * 6 + s * 2, 45); }

for (const ip of A.ips.slice(0, LIM.ips)) {
  const r = await vt('ip_addresses/' + ip);
  const x = resumen(r, a => ({ pais: a.country, as_owner: a.as_owner, reputacion: a.reputation }));
  res.ips[ip] = x;
  if (x.malicious >= 3) hz.push(H('inteligencia', 'vt_ip_maliciosa', ip, 'alta', pesoPorDetecciones(x.malicious, x.suspicious, 15), x.malicious + ' motores marcan la IP como maliciosa (' + (x.as_owner || '') + ')', F));
  else if (x.malicious >= 1 || x.suspicious >= 2) hz.push(H('inteligencia', 'vt_ip_sospechosa', ip, 'media', 8, x.malicious + ' maliciosos / ' + x.suspicious + ' sospechosos', F));
}
for (const dom of A.dominios.slice(0, LIM.dominios)) {
  const r = await vt('domains/' + dom);
  const x = resumen(r, a => ({ categorias: a.categories, creado: a.creation_date ? new Date(a.creation_date * 1000).toISOString().slice(0, 10) : null, reputacion: a.reputation, registrador: a.registrar }));
  res.dominios[dom] = x;
  if (x.malicious >= 3) hz.push(H('inteligencia', 'vt_dominio_malicioso', dom, 'critica', pesoPorDetecciones(x.malicious, x.suspicious, 25), x.malicious + ' motores marcan el dominio como malicioso', F));
  else if (x.malicious >= 1 || x.suspicious >= 2) hz.push(H('inteligencia', 'vt_dominio_sospechoso', dom, 'media', 10, x.malicious + ' maliciosos / ' + x.suspicious + ' sospechosos', F));
  if (x.categorias) { const cats = Object.values(x.categorias).join(' ').toLowerCase(); if (/phish|malware|malicious|fraud|scam/.test(cats)) hz.push(H('inteligencia', 'vt_categoria_phishing', dom, 'alta', 15, 'Categorizado como: ' + Object.values(x.categorias).slice(0, 3).join(', '), F)); }
  if (x.estado === 'ok' && x.creado) { const dias = (Date.now() - Date.parse(x.creado)) / 864e5; if (dias < 30) hz.push(H('inteligencia', 'vt_dominio_reciente', dom, 'alta', 14, 'Dominio creado hace ' + Math.round(dias) + ' días según VT', F)); }
}
for (const u of A.urls.slice(0, LIM.urls)) {
  const id = Buffer.from(u.url).toString('base64').replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  const r = await vt('urls/' + id);
  const x = resumen(r, a => ({ titulo: a.title, url_final: a.last_final_url, ultimo_analisis: a.last_analysis_date ? new Date(a.last_analysis_date * 1000).toISOString() : null }));
  res.urls[u.url] = x;
  if (x.malicious >= 2) hz.push(H('inteligencia', 'vt_url_maliciosa', u.url, 'critica', pesoPorDetecciones(x.malicious, x.suspicious, 25), x.malicious + ' motores marcan la URL como maliciosa/phishing', F));
  else if (x.malicious >= 1 || x.suspicious >= 1) hz.push(H('inteligencia', 'vt_url_sospechosa', u.url, 'media', 10, x.malicious + ' maliciosos / ' + x.suspicious + ' sospechosos', F));
  const pf = x.url_final ? parseUrl(x.url_final) : null;
  if (pf && pf.hostname && registrable(pf.hostname) !== u.dominio) hz.push(H('inteligencia', 'vt_url_redirige', u.url + ' -> ' + x.url_final, 'media', 8, 'La URL redirige a otro dominio', F));
}
for (const hsh of A.hashes.slice(0, LIM.hashes)) {
  const r = await vt('files/' + hsh);
  const x = resumen(r, a => ({ nombre_conocido: a.meaningful_name, tipo: a.type_description, etiquetas: (a.tags || []).slice(0, 8), familia: a.popular_threat_classification && a.popular_threat_classification.suggested_threat_label }));
  res.hashes[hsh] = x;
  const adj = (A.adjuntos.find(a => a.sha256 === hsh) || {}).nombre || hsh;
  if (x.malicious >= 3) hz.push(H('inteligencia', 'vt_archivo_malicioso', adj, 'critica', 45, x.malicious + ' motores detectan el adjunto como malware' + (x.familia ? ' (' + x.familia + ')' : ''), F));
  else if (x.malicious >= 1) hz.push(H('inteligencia', 'vt_archivo_sospechoso', adj, 'alta', 18, x.malicious + ' motores detectan el adjunto', F));
  else if (x.estado === 'desconocido') hz.push(H('inteligencia', 'vt_archivo_desconocido', adj, 'baja', 4, 'Hash nunca visto por VirusTotal (archivo nuevo/único: típico de campañas dirigidas)', F));
}
const estado = rate_limited ? 'parcial_rate_limit' : (consultas ? 'ok' : 'sin_artefactos');
return salida(F, estado, res, hz, { consultas });

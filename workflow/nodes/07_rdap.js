// =====================================================================
//  NODO: RDAP / WHOIS (antigüedad y estado de registro de dominios)
//  Sin API key. rdap.org redirige al RDAP oficial de cada registro.
// =====================================================================
const d = $input.first().json;
const A = d.artefactos, cfg = d.config;
const hz = [], res = {};
const F = 'rdap';
const dominios = A.dominios.filter(x => !cfg.dominios_propios.includes(x) && !esFreemail(x)).slice(0, 5);
if (!dominios.length) return salida(F, 'sin_artefactos', res, hz);

const HDR = Object.assign({ Accept: 'application/rdap+json, application/json' }, UA);
let consultas = 0;
for (const dom of dominios) {
  consultas++;
  // .ar tiene RDAP propio (NIC Argentina); el resto se resuelve vía el bootstrap de rdap.org
  const url = dom.endsWith('.ar') ? 'https://rdap.nic.ar/domain/' + dom : 'https://rdap.org/domain/' + dom;
  let r = await httpJson({ method: 'GET', url, headers: HDR });
  if (r.status === 404 && dom.endsWith('.ar')) r = await httpJson({ method: 'GET', url: 'https://rdap.org/domain/' + dom, headers: HDR });
  if (r.status === 404) { res[dom] = { estado: 'no_registrado_o_sin_rdap' }; hz.push(H('infraestructura', 'dominio_sin_registro', dom, 'media', 8, 'El dominio no aparece registrado (o su TLD no publica RDAP)', F)); continue; }
  if (!r.ok || !r.data || typeof r.data !== 'object') { res[dom] = { estado: 'error', http: r.status, error: r.error }; continue; }
  const x = r.data;
  const ev = {}; for (const e of (x.events || [])) ev[e.eventAction] = e.eventDate;
  const reg = ev.registration ? Date.parse(ev.registration) : NaN;
  const dias = isNaN(reg) ? null : Math.round((Date.now() - reg) / 864e5);
  const exp = ev.expiration ? Date.parse(ev.expiration) : NaN;
  const diasExp = isNaN(exp) ? null : Math.round((exp - Date.now()) / 864e5);
  let registrador = null;
  for (const ent of (x.entities || [])) if ((ent.roles || []).includes('registrar')) { const v = ent.vcardArray && ent.vcardArray[1]; const fn = v && v.find(a => a[0] === 'fn'); registrador = fn ? fn[3] : (ent.handle || null); }
  res[dom] = { estado: 'ok', registrado: ev.registration || null, dias_desde_registro: dias, expira: ev.expiration || null, dias_hasta_expirar: diasExp, ultimo_cambio: ev['last changed'] || null, estados: x.status || [], registrador, nameservers: (x.nameservers || []).map(n => n.ldhName).slice(0, 6) };
  if (dias != null && dias <= 30) hz.push(H('infraestructura', 'dominio_recien_registrado', dom, 'critica', 28, 'Dominio registrado hace ' + dias + ' días (' + String(ev.registration).slice(0, 10) + ')', F));
  else if (dias != null && dias <= 180) hz.push(H('infraestructura', 'dominio_reciente', dom, 'alta', 14, 'Dominio registrado hace ' + dias + ' días', F));
  else if (dias != null && dias <= 365) hz.push(H('infraestructura', 'dominio_menor_a_1_anio', dom, 'baja', 5, 'Dominio con menos de un año', F));
  if (diasExp != null && diasExp <= 400 && dias != null && dias <= 400) hz.push(H('infraestructura', 'registro_1_anio', dom, 'baja', 4, 'Registrado por el período mínimo (1 año): típico de dominios desechables', F));
  if ((x.status || []).some(s => /redemption|pending delete|hold/i.test(s))) hz.push(H('infraestructura', 'dominio_en_hold', dom, 'media', 6, 'Estado de registro anómalo: ' + x.status.join(', '), F));
  if ((x.nameservers || []).some(n => /cloudflare|namecheap|hostinger|freenom|dnspod/i.test(n.ldhName || '')) && dias != null && dias <= 90) hz.push(H('infraestructura', 'ns_barato_reciente', dom, 'baja', 3, 'Nameservers de proveedor económico en dominio reciente', F));
}
return salida(F, 'ok', res, hz, { consultas });

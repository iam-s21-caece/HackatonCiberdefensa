// =====================================================================
//  NODO: DNS (MX / SPF / DMARC / A) vía DNS-over-HTTPS de Cloudflare
//  Sin API key. ¿El dominio remitente existe, recibe correo y publica
//  políticas anti-spoofing? ¿Los dominios de los enlaces resuelven?
// =====================================================================
const d = $input.first().json;
const A = d.artefactos, c = d.correo, cfg = d.config;
const hz = [], res = {};
const F = 'dns';
async function dns(name, type) {
  const r = await httpJson({ method: 'GET', url: 'https://cloudflare-dns.com/dns-query', qs: { name, type }, headers: { accept: 'application/dns-json' }, timeout: 10000 });
  if (!r.ok || !r.data) return { ok: false, rcode: null, answers: [] };
  return { ok: true, rcode: r.data.Status, answers: (r.data.Answer || []).map(a => String(a.data).replace(/^"|"$/g, '').replace(/"\s*"/g, '')) };
}
// El Reply-To en freemail ya lo marca el nodo de cabeceras; acá sólo interesa la infraestructura del dominio que dice enviar
const remitentes = uniq([c.from.dominio_registrable, c.reply_to.dominio_registrable]).filter(x => !esFreemail(x));
const enlaces = uniq(A.urls.filter(u => !u.es_ip).map(u => u.dominio)).filter(x => !remitentes.includes(x)).slice(0, 4);
let consultas = 0;
for (const dom of remitentes) {
  if (!dom) continue;
  const [mx, txt, dmarc, a] = await Promise.all([dns(dom, 'MX'), dns(dom, 'TXT'), dns('_dmarc.' + dom, 'TXT'), dns(dom, 'A')]);
  consultas += 4;
  const spf = txt.answers.find(t => /^v=spf1/i.test(t)) || null;
  const dm = dmarc.answers.find(t => /^v=DMARC1/i.test(t)) || null;
  const pol = dm ? (/p=(\w+)/i.exec(dm) || [null, null])[1] : null;
  res[dom] = { rol: 'remitente', existe: mx.rcode === 0 || a.rcode === 0, mx: mx.answers, spf, dmarc: dm, politica_dmarc: pol, a: a.answers };
  const propio = cfg.dominios_propios.includes(dom);
  if (mx.rcode === 3 && a.rcode === 3) hz.push(H('dns', 'dominio_inexistente', dom, 'critica', 30, 'El dominio remitente no existe en DNS (NXDOMAIN): dirección falsa', F));
  else {
    if (mx.ok && !mx.answers.length) hz.push(H('dns', 'sin_mx', dom, 'alta', 14, 'El dominio remitente no tiene registros MX: no puede recibir respuestas (dominio de "sólo envío" o falso)', F));
    if (txt.ok && !spf) hz.push(H('dns', 'sin_spf', dom, 'media', 8, 'El dominio no publica SPF: cualquiera puede enviar en su nombre', F));
    else if (spf && /\+all/.test(spf)) hz.push(H('dns', 'spf_permisivo', dom, 'alta', 12, 'SPF con +all: autoriza a cualquier servidor', F));
    if (dmarc.ok && !dm) hz.push(H('dns', 'sin_dmarc', dom, 'media', 6, 'El dominio no publica política DMARC', F));
    else if (pol && pol.toLowerCase() === 'none') hz.push(H('dns', 'dmarc_none', dom, 'baja', 3, 'DMARC p=none: sin aplicación (monitoreo solamente)', F));
    if (spf && dm && /p=(reject|quarantine)/i.test(dm) && c.auth.spf === 'pass') hz.push(H('dns', 'dominio_bien_protegido', dom, 'info', -6, 'Dominio con SPF + DMARC ' + pol + ' y SPF pass: difícil de suplantar', F));
    if (propio && spf && dm) hz.push(H('dns', 'dominio_propio_protegido', dom, 'info', 0, 'Dominio propio con SPF/DMARC publicados', F));
  }
}
for (const dom of enlaces) {
  const a = await dns(dom, 'A'); consultas++;
  res[dom] = { rol: 'enlace', existe: a.rcode === 0, a: a.answers };
  if (a.rcode === 3) hz.push(H('dns', 'enlace_no_resuelve', dom, 'media', 6, 'Dominio del enlace no resuelve (campaña desmontada o aún no activa)', F));
}
return salida(F, 'ok', res, hz, { consultas });

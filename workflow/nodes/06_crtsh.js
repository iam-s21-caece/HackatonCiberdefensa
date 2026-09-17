// =====================================================================
//  NODO: crt.sh (Certificate Transparency)
//  Sin API key. Un dominio con su primer certificado emitido hace días
//  y sin historial es una señal fuerte de infraestructura recién montada.
// =====================================================================
const d = $input.first().json;
const A = d.artefactos, cfg = d.config;
const hz = [], res = {};
const F = 'crtsh';
const dominios = A.dominios.filter(x => !cfg.dominios_propios.includes(x) && !esFreemail(x)).slice(0, 4);
if (!dominios.length) return salida(F, 'sin_artefactos', res, hz);

let consultas = 0;
for (const dom of dominios) {
  consultas++;
  const r = await httpJson({ method: 'GET', url: 'https://crt.sh/', qs: { q: '%.' + dom, output: 'json' }, timeout: 25000, headers: UA });
  if (!r.ok || !Array.isArray(r.data)) { res[dom] = { estado: r.status === 0 ? 'timeout' : 'error', http: r.status }; continue; }
  const certs = r.data;
  const fechas = certs.map(c => Date.parse(c.not_before)).filter(t => !isNaN(t)).sort((a, b) => a - b);
  const nombres = uniq(certs.flatMap(c => String(c.name_value || '').split('\n'))).filter(n => !n.startsWith('*'));
  const primero = fechas.length ? new Date(fechas[0]).toISOString().slice(0, 10) : null;
  const ultimo = fechas.length ? new Date(fechas[fechas.length - 1]).toISOString().slice(0, 10) : null;
  const diasPrimero = fechas.length ? Math.round((Date.now() - fechas[0]) / 864e5) : null;
  const emisores = uniq(certs.map(c => c.issuer_name)).slice(0, 5);
  res[dom] = { estado: 'ok', certificados: certs.length, primer_certificado: primero, ultimo_certificado: ultimo, dias_desde_primero: diasPrimero, nombres_vistos: nombres.slice(0, 15), emisores };
  if (certs.length === 0) hz.push(H('infraestructura', 'sin_certificados', dom, 'media', 8, 'El dominio no tiene certificados TLS registrados en CT: sin sitio HTTPS legítimo conocido', F));
  else if (diasPrimero != null && diasPrimero <= 14) hz.push(H('infraestructura', 'certificado_muy_reciente', dom, 'alta', 18, 'Primer certificado emitido hace ' + diasPrimero + ' días (' + primero + '): infraestructura recién montada', F));
  else if (diasPrimero != null && diasPrimero <= 60) hz.push(H('infraestructura', 'certificado_reciente', dom, 'media', 10, 'Primer certificado hace ' + diasPrimero + ' días', F));
  const sosp = nombres.filter(n => /(login|secure|verify|account|cuenta|update|mail|webmail|owa|portal|banco|pago)/i.test(n) && n !== dom);
  // Sólo para dominios chicos: un dominio con decenas de certificados es infraestructura establecida, no un kit de phishing
  if (sosp.length && certs.length < 50) hz.push(H('infraestructura', 'subdominios_sospechosos_ct', dom, 'media', 8, 'Subdominios con certificados: ' + sosp.slice(0, 5).join(', '), F));
  if (emisores.length === 1 && /let's encrypt|zerossl/i.test(emisores[0]) && certs.length <= 3 && diasPrimero != null && diasPrimero <= 90)
    hz.push(H('infraestructura', 'cert_gratuito_reciente', dom, 'baja', 4, 'Sólo certificados gratuitos recientes (' + emisores[0].replace(/^.*O=/, '').slice(0, 30) + ')', F));
}
return salida(F, 'ok', res, hz, { consultas });

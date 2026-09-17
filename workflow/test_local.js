#!/usr/bin/env node
/*
  Ejecuta la cadena de nodos de CENTINELA SIN n8n (útil para debug y CI).
  Emula $input / $() / this.helpers.httpRequest con fetch nativo de Node ≥18.

  Uso:  node test_local.js ../samples/phishing_credenciales.json [--ollama http://localhost:11434]
        node test_local.js ../samples/phishing_reembolso.eml
*/
const fs = require('fs');
const path = require('path');

const file = process.argv[2];
if (!file) { console.error('Uso: node test_local.js <muestra.json|muestra.eml> [--ollama URL]'); process.exit(1); }
const oi = process.argv.indexOf('--ollama');
const OLLAMA = oi > 0 ? process.argv[oi + 1] : (process.env.OLLAMA_URL || '');

const NODES = path.join(__dirname, 'nodes');
const common = fs.readFileSync(path.join(NODES, '_common.js'), 'utf8');
const AsyncFunction = Object.getPrototypeOf(async function () { }).constructor;

// ---- emulación mínima del entorno del nodo Code de n8n ----
const helpers = {
  async httpRequest(o) {
    let url = o.url;
    if (o.qs) url += (url.includes('?') ? '&' : '?') + new URLSearchParams(Object.entries(o.qs).map(([k, v]) => [k, String(v)])).toString();
    const headers = Object.assign({}, o.headers || {});
    let body = o.body;
    if (body && typeof body === 'object') { body = JSON.stringify(body); headers['content-type'] = headers['content-type'] || headers['Content-Type'] || 'application/json'; }
    const ctrl = new AbortController(); const t = setTimeout(() => ctrl.abort(), o.timeout || 20000);
    try {
      const r = await fetch(url, { method: o.method || 'GET', headers, body, signal: ctrl.signal, redirect: 'follow' });
      const txt = await r.text(); let parsed = txt; try { parsed = JSON.parse(txt); } catch (e) { }
      const out = { statusCode: r.status, headers: Object.fromEntries(r.headers), body: parsed };
      if (!o.ignoreHttpStatusErrors && r.status >= 400) { const e = new Error('HTTP ' + r.status); e.response = out; throw e; }
      return o.returnFullResponse ? out : parsed;
    } finally { clearTimeout(t); }
  },
  async getBinaryDataBuffer() { return Buffer.alloc(0); }
};
const store = {};
function makeDollar(items) {
  const fn = name => ({ first: () => store[name][0], all: () => store[name], item: store[name] && store[name][0] });
  return { $: fn, $input: { first: () => items[0], all: () => items, item: items[0] } };
}
async function run(nodeName, file, items) {
  const src = common + '\n' + fs.readFileSync(path.join(NODES, file), 'utf8');
  const { $, $input } = makeDollar(items);
  const f = new AsyncFunction('$input', '$', 'require', '$env', src);
  const t0 = Date.now();
  const out = await f.call({ helpers }, $input, $, require, process.env);
  store[nodeName] = out;
  console.error(`  ✓ ${nodeName} (${Date.now() - t0} ms)` + (out[0] && out[0].json.n_hallazgos != null ? ` → ${out[0].json.n_hallazgos} hallazgos [${out[0].json.estado}]` : ''));
  return out;
}

(async () => {
  const rawIn = fs.readFileSync(file, 'utf8');
  const entrada = file.endsWith('.eml') ? { raw: rawIn } : JSON.parse(rawIn);
  const env = process.env;
  const cfgItem = Object.assign({
    vt_api_key: env.VT_API_KEY || '', abuseipdb_api_key: env.ABUSEIPDB_API_KEY || '', abusech_api_key: env.ABUSECH_API_KEY || '',
    ollama_url: OLLAMA || 'http://ollama:11434', ollama_model: env.OLLAMA_MODEL || 'llama3.2:3b',
    dominios_propios: env.DOMINIOS_PROPIOS || 'ejercito.mil.ar,argentina.gob.ar,mil.ar', numeros_propios: env.NUMEROS_PROPIOS || '', pais_propio: env.PAIS_PROPIO || '54',
    soc_webhook_url: env.SOC_WEBHOOK_URL || ''
  }, { headers: {}, params: {}, query: {}, body: entrada, webhookUrl: 'http://localhost:5678/webhook/centinela/' + (/whatsapp/i.test(file) ? 'whatsapp' : /sms/i.test(file) ? 'sms' : 'analizar') });   // simula la salida del Webhook + Set

  console.error('▶ CENTINELA test local:', path.basename(file));
  const parsed = await run('Desarmar correo', '01_desarmar_correo.js', [{ json: cfgItem }]);
  const fuentes = [
    ['Cabeceras y autenticación (SPF/DKIM/DMARC)', '02_cabeceras_auth.js'], ['Heurísticas: cuerpo, URLs y adjuntos', '03_heuristicas.js'],
    ['VirusTotal: IPs, dominios, URLs y hashes', '04_virustotal.js'], ['AbuseIPDB: reputación de IPs', '05_abuseipdb.js'],
    ['crt.sh: certificados de dominios', '06_crtsh.js'], ['RDAP/WHOIS: antigüedad de dominios', '07_rdap.js'],
    ['URLhaus: URLs maliciosas', '08_urlhaus.js'], ['MalwareBazaar: hashes de adjuntos', '09_malwarebazaar.js'],
    ['ThreatFox: IOCs (dominios/IPs/hashes)', '10_threatfox.js'], ['DNS: MX / SPF / DMARC', '11_dns.js'],
    ['Agente 1: identidad del remitente', '17_agente1.js']
  ];
  const resultados = await Promise.all(fuentes.map(([n, f]) => run(n, f, parsed).catch(e => { console.error('  ✗', n, e.message); return [{ json: { fuente: n, estado: 'error', hallazgos: [], resultados: {} } }]; })));
  const merged = resultados.flat();
  const cons = await run('Consolidar evidencia y puntuar', '12_consolidar.js', merged);
  let iaResp = { error: 'Ollama no configurado (usá --ollama http://localhost:11434)' };
  if (OLLAMA) {
    console.error('  … consultando IA en', OLLAMA);
    try { iaResp = await helpers.httpRequest({ method: 'POST', url: OLLAMA.replace(/\/$/, '') + '/api/chat', body: cons[0].json.ollama_request, timeout: 300000 }); }
    catch (e) { iaResp = { error: e.message }; }
  }
  const final = await run('Interpretar veredicto IA + guardrails', '13_interpretar_ia.js', [{ json: iaResp }]);
  const r = final[0].json;
  const accion = { VERDADERO_POSITIVO: '14_accion_vp.js', ESCALAR: '15_accion_escalar.js', FALSO_POSITIVO: '16_accion_fp.js' }[r.veredicto_final];
  await run('Acción', accion, final);

  console.log('\n================  RESULTADO  ================');
  console.log('Veredicto final :', r.veredicto_final, '→', r.accion);
  console.log('Score / nivel   :', r.score, '/', r.nivel, '  (reglas duras:', r.reglas_duras.join(', ') || '-', ')');
  console.log('Motivo          :', r.motivo_veredicto.join(' | '));
  console.log('IA              :', r.ia.disponible ? `${r.ia.veredicto} (conf ${r.ia.confianza}) - ${r.ia.resumen}` : 'no disponible - ' + r.ia.error);
  console.log('Fuentes OK      :', r.fuentes_ok.join(', '));
  console.log('Sin API key     :', r.fuentes_sin_key.join(', ') || '-');
  console.log('Con error       :', r.fuentes_error.join(', ') || '-');
  console.log('\nHallazgos (' + r.n_hallazgos + '):');
  for (const h of r.hallazgos) console.log(`  [${h.severidad.toUpperCase().padEnd(7)}] ${String(h.peso).padStart(3)}  ${h.tipo.padEnd(32)} ${h.detalle}${h.valor ? '  ← ' + h.valor.slice(0, 70) : ''}`);
  const outFile = path.join(__dirname, '..', 'data', 'reports', r.report_id + '.json');
  fs.mkdirSync(path.dirname(outFile), { recursive: true });
  fs.writeFileSync(outFile, JSON.stringify(r, null, 2));
  console.log('\nReporte:', outFile);
})().catch(e => { console.error('ERROR:', e); process.exit(1); });

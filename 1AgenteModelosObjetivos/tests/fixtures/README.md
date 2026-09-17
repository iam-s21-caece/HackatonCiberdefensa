# Fixtures

| Archivo | Origen |
|---|---|
| `parser_<muestra>.json` | Salida real del nodo "Desarmar correo" de `resources/centinela.json`, generada con `node herramientas/harness_flujo/harness.mjs --flujo resources/centinela.json --eml muestras/<muestra>.eml --salida-parser ...` el 2026-09-16. |
| `dkim_prueba_privada.pem` / `dkim_prueba_publica.b64` | Par RSA de 1024 bits generado con `openssl genrsa` sólo para las pruebas de DKIM. No se usa fuera de `tests/`. |

Para regenerar los `parser_*.json` después de un cambio en el parser del flujo:

```bash
for m in bec_suplantacion_interna bec_autenticacion_forjada interno_legitimo phishing_reembolso; do
  node herramientas/harness_flujo/harness.mjs --flujo resources/centinela.json \
    --eml muestras/$m.eml --salida-parser 1AgenteModelosObjetivos/tests/fixtures/parser_$m.json
done
```

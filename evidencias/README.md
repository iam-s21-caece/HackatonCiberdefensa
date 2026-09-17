# Evidencias de verificación — RNF-05

Cada corrida de `bash scripts/verificar_e2e.sh` crea `evidencias/<fecha UTC>-<commit>[-con-cambios]/`.
El sufijo `-con-cambios` indica que había archivos sin commit: esa corrida no se puede reproducir
exactamente desde el repositorio.

Las corridas son locales (`.gitignore`). Para publicar una **corrida de referencia**:

```bash
git add -f evidencias/<corrida>
```

Qué hay en cada corrida y cómo leerla: [docs/DESPLIEGUE.md § 6](../docs/DESPLIEGUE.md#6-verificación-de-extremo-a-extremo-el-experimento).

Para comparar dos corridas, primero hay que confirmar que las variables controladas coinciden
(`entorno.json`: commit, `imagenes.*.id`, `ia.modelos[].digest`, `entradas.*_sha256`,
`configuracion`). Recién después se comparan `resultados.jsonl`.

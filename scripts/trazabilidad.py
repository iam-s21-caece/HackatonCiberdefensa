"""Matriz de trazabilidad de requerimientos — RNF-01.

    python scripts/trazabilidad.py                  # ejecuta las pruebas unitarias y de contrato
    python scripts/trazabilidad.py --integracion    # incluye las de integración con el workflow (lentas, usan red)
    python scripts/trazabilidad.py --sin-ejecutar   # sólo verifica que existan referencias
    python scripts/trazabilidad.py --incluir-interfaz  # exige también los RI (interfaz)

Para cada ID de docs/REQUERIMIENTOS.md busca:
- implementación: el ID escrito en el código (docstrings/comentarios) o en archivos de despliegue;
- pruebas: tests cuyo NOMBRE contiene el ID (`test_ra1_04_...` cubre RA1-04), y su resultado.

Un requerimiento RG/RA1/RA2 cumple si tiene implementación referenciada y todas sus pruebas ejecutadas
pasan. RNF exige implementación referenciada y, si tiene pruebas, que pasen (RNF-02/04/05: despliegue). Un RI de un módulo (todos salvo RI-08, la base) NO se da
por implementado porque figure en el registro de módulos o en el componente de módulo pendiente:
declarar un módulo no es construirlo. Escribe docs/TRAZABILIDAD.md y sale con código 1 si algo falta.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
REQUERIMIENTOS = RAIZ / "docs" / "REQUERIMIENTOS.md"
SALIDA = RAIZ / "docs" / "TRAZABILIDAD.md"
PYTHON = sys.executable

CODIGO = ["1AgenteModelosObjetivos/agente_identidad", "1AgenteModelosObjetivos/integracion_n8n",
          "2AgenteAprendizaje/agente_aprendizaje", "2AgenteAprendizaje/experimentos", "herramientas/harness_flujo",
          "herramientas/generar_reportes.py", "scripts", "interfaz/src", "interfaz/nginx", "interfaz/Dockerfile",
          "interfaz/vite.config.js", "docker-compose.yml", ".env.example", ".gitattributes",
          "workflow/nodes/17_agente1.js",
          "1AgenteModelosObjetivos/Dockerfile", "2AgenteAprendizaje/Dockerfile",
          "1AgenteModelosObjetivos/.env.example", "2AgenteAprendizaje/.env.example"]
SUITES = {  # nombre -> (directorio de trabajo, argumentos de pytest)
    "agente1": ("1AgenteModelosObjetivos", []),
    "agente2": ("2AgenteAprendizaje", []),
    "contratos": (".", ["herramientas/pruebas_contrato"]),
    "despliegue": (".", ["herramientas/pruebas_despliegue"]),
}
EXTENSIONES = {".py", ".js", ".jsx", ".mjs", ".yml", ".yaml", ".md", ".css", ".sh", ".ps1", ""}
DECLARACIONES_DE_MODULOS = {"interfaz/src/modules/registry.js", "interfaz/src/components/ModuloPendiente.jsx"}
_FILA = re.compile(r"^\|\s*((?:RG|RA1|RA2|RI|RNF)-\d{2})\s*\|\s*(.+?)\s*\|", re.M)
_ID_EN_TEST = re.compile(r"(?<![a-z0-9])(rg|ra1|ra2|ri|rnf)_(\d{2})(?![0-9])")


def requerimientos() -> list[tuple[str, str]]:
    return _FILA.findall(REQUERIMIENTOS.read_text(encoding="utf-8"))


def archivos_codigo() -> list[Path]:
    salida = []
    for ruta in CODIGO:
        p = RAIZ / ruta
        if p.is_file():
            salida.append(p)
        elif p.is_dir():
            salida += [f for f in p.rglob("*") if f.is_file() and f.suffix in EXTENSIONES
                       and "node_modules" not in f.parts and "__pycache__" not in f.parts]
    return salida


def implementaciones(ids: list[str]) -> dict[str, list[str]]:
    encontrados: dict[str, list[str]] = {i: [] for i in ids}
    for archivo in archivos_codigo():
        texto = archivo.read_text(encoding="utf-8", errors="ignore")
        relativo = archivo.relative_to(RAIZ).as_posix()
        for i in ids:
            if i.startswith("RI-") and i != "RI-08" and relativo in DECLARACIONES_DE_MODULOS:
                continue
            if re.search(rf"(?<![A-Z0-9]){re.escape(i)}(?![0-9])", texto):
                encontrados[i].append(relativo)
    return encontrados


def ids_de_test(nombre: str) -> set[str]:
    return {f"{p.upper()}-{n}" for p, n in _ID_EN_TEST.findall(nombre.split("[")[0])}


def tests_declarados() -> dict[str, list[str]]:
    por_id: dict[str, list[str]] = {}
    dirs = [RAIZ / "1AgenteModelosObjetivos/tests", RAIZ / "2AgenteAprendizaje/tests", RAIZ / "herramientas/pruebas_contrato",
            RAIZ / "herramientas/pruebas_despliegue"]
    dirs = [d for d in dirs if d.is_dir()]
    for d in dirs:
        for archivo in d.rglob("test_*.py"):
            for nombre in re.findall(r"^def (test_\w+)", archivo.read_text(encoding="utf-8"), re.M):
                for i in ids_de_test(nombre):
                    por_id.setdefault(i, []).append(f"{archivo.relative_to(RAIZ).as_posix()}::{nombre}")
    return por_id


def ejecutar(integracion: bool) -> dict[str, str]:
    """Devuelve {nombre de test (sin parámetros): 'passed'|'failed'} combinando parametrizaciones."""
    resultados: dict[str, str] = {}
    for suite, (cwd, extra) in SUITES.items():
        with tempfile.TemporaryDirectory() as tmp:
            xml = Path(tmp) / f"{suite}.xml"
            cmd = [PYTHON, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={xml}", *extra]
            if not integracion and suite == "agente1":
                cmd += ["-m", "not integracion"]
            subprocess.run(cmd, cwd=RAIZ / cwd, capture_output=True, text=True)
            if not xml.exists():
                continue
            for caso in ET.parse(xml).getroot().iter("testcase"):
                nombre = caso.get("name", "").split("[")[0]
                fallo = caso.find("failure") is not None or caso.find("error") is not None
                omitido = caso.find("skipped") is not None
                estado = "failed" if fallo else "skipped" if omitido else "passed"
                if resultados.get(nombre) != "failed":
                    resultados[nombre] = estado if resultados.get(nombre) in (None, "skipped", estado) else resultados[nombre]
    return resultados


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--integracion", action="store_true")
    ap.add_argument("--sin-ejecutar", action="store_true")
    ap.add_argument("--incluir-interfaz", action="store_true")
    a = ap.parse_args()

    reqs = requerimientos()
    ids = [i for i, _ in reqs]
    impl = implementaciones(ids)
    tests = tests_declarados()
    resultados = {} if a.sin_ejecutar else ejecutar(a.integracion)

    filas, faltantes = [], []
    for i, texto in reqs:
        grupo = i.split("-")[0]
        nombres = tests.get(i, [])
        estados = [resultados.get(n.split("::")[1], "no_ejecutado") for n in nombres]
        pasan = sum(e == "passed" for e in estados)
        fallan = sum(e == "failed" for e in estados)
        if grupo == "RI" and not a.incluir_interfaz:
            estado = "cumple" if impl[i] else "pendiente (interfaz)"
        elif grupo == "RI":
            estado = "cumple" if impl[i] else "FALTA implementación"
        elif grupo == "RNF":
            estado = ("FALTA implementación" if not impl[i] else f"FALLA ({fallan} prueba/s)" if fallan else "cumple")
        elif not impl[i]:
            estado = "FALTA implementación"
        elif not nombres:
            estado = "FALTA prueba"
        elif fallan:
            estado = f"FALLA ({fallan} prueba/s)"
        elif a.sin_ejecutar or pasan:
            estado = "cumple"
        else:
            estado = "sin pruebas ejecutadas"
        if estado.startswith(("FALTA", "FALLA", "sin")):
            faltantes.append(i)
        prueba_txt = (f"{len(nombres)} ({pasan} ok)" if not a.sin_ejecutar else str(len(nombres))) if nombres else "—"
        filas.append((i, texto, impl[i], nombres, prueba_txt, estado))

    lineas = [
        "# Matriz de trazabilidad", "",
        f"Generada por `scripts/trazabilidad.py` el {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC "
        f"({'sin ejecutar pruebas' if a.sin_ejecutar else 'pruebas ejecutadas' + (' con integración' if a.integracion else ' sin integración')}). "
        "No editar a mano.", "",
        f"**{sum(1 for f in filas if f[5] == 'cumple')} de {len(filas)} requerimientos cumplen.** "
        + (f"Faltan: {', '.join(faltantes)}." if faltantes else "Ninguno falta."), "",
        "| ID | Requerimiento | Implementación | Pruebas | Estado |", "|---|---|---|---|---|",
    ]
    for i, texto, archivos, nombres, prueba_txt, estado in filas:
        impl_txt = "<br>".join(f"`{f}`" for f in archivos[:4]) + (f"<br>+{len(archivos) - 4}" if len(archivos) > 4 else "")
        detalle = "<br>".join(f"`{n.split('::')[1]}`" for n in nombres[:3]) + (f"<br>+{len(nombres) - 3}" if len(nombres) > 3 else "")
        lineas.append(f"| {i} | {texto} | {impl_txt or '—'} | {prueba_txt}{'<br>' + detalle if detalle else ''} | {estado} |")
    SALIDA.write_text("\n".join(lineas) + "\n", encoding="utf-8")

    for i, _, archivos, nombres, prueba_txt, estado in filas:
        print(f"{i:7s} {estado:24s} impl={len(archivos):2d} pruebas={prueba_txt}")
    print(f"\n-> {SALIDA.relative_to(RAIZ)}")
    return 1 if faltantes else 0


if __name__ == "__main__":
    sys.exit(main())

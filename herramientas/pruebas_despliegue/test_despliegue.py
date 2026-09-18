"""Pruebas del despliegue — RNF-02, RNF-03, RNF-04, RNF-05 y RG-04.

No levantan contenedores: verifican la configuración tal como la interpreta Docker Compose
(`docker compose config`) y los archivos que usan los scripts. Lo que sólo se puede comprobar con el
ecosistema corriendo lo verifica `scripts/verificar_e2e.sh` y queda como evidencia.

    pytest herramientas/pruebas_despliegue
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
COMPONENTES = {"n8n", "n8n-importar", "ollama", "ollama-modelo", "agente-identidad", "agente-aprendizaje", "interfaz"}
AGENTES = ("agente-identidad", "agente-aprendizaje")

requiere_docker = pytest.mark.skipif(shutil.which("docker") is None, reason="requiere Docker Compose")


@pytest.fixture(scope="module")
def compose() -> dict:
    # Sin variables del entorno de quien corre las pruebas: se valida lo que viene en el repositorio.
    entorno = {k: v for k, v in os.environ.items()
               if not re.match(r"^(COMPOSE_|CENTINELA_|N8N_|OLLAMA_|AGENTE|INTERFAZ_|ORIGENES_)", k)}
    salida = subprocess.run(["docker", "compose", "--env-file", str(RAIZ / ".env.example"), "config", "--format", "json"],
                            cwd=RAIZ, capture_output=True, text=True, env=entorno)
    assert salida.returncode == 0, salida.stderr
    return json.loads(salida.stdout)


@requiere_docker
def test_rnf_02_cada_componente_corre_en_su_propio_contenedor(compose):
    servicios = compose["services"]
    assert COMPONENTES <= set(servicios)
    construidos = {n: s for n, s in servicios.items() if "build" in s}
    assert set(construidos) == {*AGENTES, "interfaz"}
    assert len({s["image"] for s in construidos.values()}) == 3  # imagen propia por componente
    contextos = {Path(s["build"]["context"]).name for s in construidos.values()}
    assert contextos == {"1AgenteModelosObjetivos", "2AgenteAprendizaje", "interfaz"}
    for nombre in (*AGENTES, "interfaz"):
        s = servicios[nombre]
        assert s["deploy"]["resources"]["limits"]["memory"], nombre
        assert "no-new-privileges:true" in s["security_opt"], nombre
    for nombre in AGENTES:  # los agentes no necesitan escribir fuera de su volumen
        assert servicios[nombre]["read_only"] is True and servicios[nombre]["cap_drop"] == ["ALL"]


@requiere_docker
def test_rnf_02_los_agentes_leen_los_reportes_del_flujo_en_solo_lectura(compose):
    servicios = compose["services"]
    datos_n8n = next(v["source"] for v in servicios["n8n"]["volumes"] if v["target"] == "/data")
    for nombre in AGENTES:
        reportes = next(v for v in servicios[nombre]["volumes"] if v["target"] == "/centinela/reports")
        assert reportes["read_only"] is True
        assert Path(reportes["source"]) == Path(datos_n8n) / "reports"
    # cada agente escribe sólo su volumen y lee el del otro en solo lectura
    a1 = {v["target"]: v for v in servicios["agente-identidad"]["volumes"]}
    a2 = {v["target"]: v for v in servicios["agente-aprendizaje"]["volumes"]}
    assert a1["/agente2"]["read_only"] and a2["/agente1"]["read_only"]
    assert not a1["/data/agente1"].get("read_only") and not a2["/data/agente2"].get("read_only")


@requiere_docker
def test_rg_04_n8n_no_depende_de_los_agentes_ni_de_la_ia(compose):
    n8n = compose["services"]["n8n"]
    assert set(n8n["depends_on"]) == {"n8n-importar"}
    entorno = n8n["environment"]
    assert entorno["AGENTE1_URL"] == "http://agente-identidad:8101"
    assert entorno["OLLAMA_URL"] == "http://ollama:11434"


@requiere_docker
def test_rnf_04_el_flujo_versionado_se_importa_y_publica_por_comando_antes_de_n8n(compose):
    servicios = compose["services"]
    assert servicios["n8n"]["depends_on"]["n8n-importar"]["condition"] == "service_completed_successfully"
    flujo = json.loads((RAIZ / "workflow" / "centinela_workflow.json").read_text(encoding="utf-8"))
    comando = " ".join(servicios["n8n-importar"]["command"])
    assert "n8n import:workflow --input=/workflow/centinela_workflow.json" in comando
    assert f"n8n publish:workflow --id={flujo['id']}" in comando
    assert servicios["n8n-importar"]["restart"] == "no"
    webhooks = {n["parameters"]["path"] for n in flujo["nodes"] if n["type"] == "n8n-nodes-base.webhook"}
    assert webhooks == {"centinela/analizar", "centinela/whatsapp", "centinela/sms"}


@requiere_docker
def test_rnf_04_versiones_fijas_y_puertos_publicados_solo_en_la_maquina(compose):
    for nombre, s in compose["services"].items():
        imagen = s["image"]
        assert ":" in imagen.rsplit("/", 1)[-1] and not imagen.endswith(":latest"), f"{nombre}: {imagen}"
        for puerto in s.get("ports", []):
            assert puerto["host_ip"] == "127.0.0.1", f"{nombre} publica {puerto}"
    for dockerfile in ("1AgenteModelosObjetivos/Dockerfile", "2AgenteAprendizaje/Dockerfile", "interfaz/Dockerfile"):
        for base in re.findall(r"^FROM\s+(\S+)", (RAIZ / dockerfile).read_text(encoding="utf-8"), re.M):
            assert ":" in base and not base.endswith(":latest"), f"{dockerfile}: {base}"


def test_rnf_04_scripts_y_claves_con_fin_de_linea_lf():
    atributos = (RAIZ / ".gitattributes").read_text(encoding="utf-8")
    assert re.search(r"^\*\s+text=auto\s+eol=lf", atributos, re.M)
    for script in (RAIZ / "scripts").glob("*.sh"):
        assert b"\r\n" not in script.read_bytes(), script.name
        assert script.read_text(encoding="utf-8").startswith("#!/usr/bin/env bash"), script.name


@requiere_docker
def test_rnf_03_secretos_por_entorno_y_nunca_versionados(compose):
    ejemplo = dict(re.findall(r"^([A-Z0-9_]+)=(.*)$", (RAIZ / ".env.example").read_text(encoding="utf-8"), re.M))
    for secreto in ("AGENTE2_TOKEN", "N8N_OWNER_PASSWORD_HASH", "VT_API_KEY", "ABUSEIPDB_API_KEY", "ABUSECH_API_KEY", "DEEPSEEK_API_KEY"):
        assert ejemplo[secreto] == "", f"{secreto} no puede venir con valor en .env.example"
    ignorado = subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=RAIZ)
    assert ignorado.returncode == 0, ".env tiene que estar en .gitignore"
    assert "AGENTE2_TOKEN" in compose["services"]["agente-aprendizaje"]["environment"]


def test_rnf_03_las_claves_no_viajan_en_el_item_ni_quedan_en_el_reporte():
    """La key de DeepSeek la lee sólo el nodo HTTP desde $env; el nodo que arma el reporte enmascara las demás."""
    flujo = json.loads((RAIZ / "workflow" / "centinela_workflow.json").read_text(encoding="utf-8"))
    nodos = {n["name"]: n for n in flujo["nodes"]}
    config = nodos["Configuración"]["parameters"]["assignments"]["assignments"]
    assert not any("DEEPSEEK_API_KEY" in a["value"] and a["type"] != "boolean" for a in config)
    ia = next(n for n in flujo["nodes"] if n["type"] == "n8n-nodes-base.httpRequest")
    cabecera = ia["parameters"]["headerParameters"]["parameters"][0]
    assert cabecera["name"] == "Authorization" and "$env.DEEPSEEK_API_KEY" in cabecera["value"]
    interpretar = nodos["Interpretar veredicto IA + guardrails"]["parameters"]["jsCode"]
    for clave in ("vt_api_key", "abuseipdb_api_key", "abusech_api_key", "soc_webhook_url"):
        assert f"'{clave}'" in interpretar.split("out.config = Object.assign({}, base.config);")[1].split("\n")[1]


def test_rnf_05_las_hipotesis_cubren_todas_las_muestras_y_respetan_los_guardrails():
    esperados = json.loads((RAIZ / "samples" / "esperados.json").read_text(encoding="utf-8"))["muestras"]
    archivos = {e["archivo"] for e in esperados}
    muestras = {f"samples/{p.name}" for p in (RAIZ / "samples").iterdir() if p.name != "esperados.json"}
    assert archivos == muestras
    for e in esperados:
        assert (RAIZ / e["archivo"]).is_file()
        assert e["veredicto_esperado"] in e["veredictos_aceptados"], e["archivo"]
        prohibido = {"MALICIOSO": "FALSO_POSITIVO", "LEGITIMO": "VERDADERO_POSITIVO"}[e["verdad"]]
        assert prohibido not in e["veredictos_aceptados"], f"{e['archivo']}: la hipótesis acepta lo que el guardrail prohíbe"
        esperado_a1 = {"NO_APLICA"} if e["canal"] != "email" else None
        if esperado_a1:
            assert set(e["agente1_aceptadas"]) == esperado_a1, e["archivo"]
        elif e["verdad"] == "MALICIOSO":
            assert "IDENTIDAD_VERIFICADA" not in e["agente1_aceptadas"], e["archivo"]
        assert e["fundamento"]

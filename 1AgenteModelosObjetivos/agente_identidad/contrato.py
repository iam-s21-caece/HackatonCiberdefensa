from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Severidad = Literal["info", "baja", "media", "alta", "critica"]
FUENTE = "agente_identidad"


class _Flexible(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class Direccion(_Flexible):
    raw: str = ""
    nombre: str = ""
    direccion: str = ""
    dominio: str = ""
    dominio_registrable: str = ""


class AuthDeclarada(_Flexible):
    spf: str | None = None
    dkim: str | None = None
    dmarc: str | None = None
    dkim_dominio: str | None = None
    raw: str = ""


class Salto(_Flexible):
    from_: str | None = Field(default=None, alias="from")
    ip: str | None = None
    raw: str = ""


class CorreoParseado(_Flexible):
    from_: Direccion = Field(default_factory=Direccion, alias="from")
    reply_to: Direccion = Field(default_factory=Direccion)
    return_path: Direccion = Field(default_factory=Direccion)
    to: str = ""
    subject: str = ""
    message_id: str = ""
    auth: AuthDeclarada = Field(default_factory=AuthDeclarada)
    received: list[Salto] = Field(default_factory=list)
    cabeceras: dict[str, list[str]] = Field(default_factory=dict)
    cuerpo: str = ""


class ConfigFlujo(_Flexible):
    dominios_propios: list[str] = Field(default_factory=list)


class SalidaParser(_Flexible):
    report_id: str
    origen_entrada: str = "json_estructurado"
    config: ConfigFlujo = Field(default_factory=ConfigFlujo)
    correo: CorreoParseado


class EntradaAnalisis(BaseModel):
    parseado: SalidaParser
    raw_eml: str | None = Field(default=None, description="El .eml original, si el flujo lo recibió crudo.")


class Hallazgo(BaseModel):
    categoria: str
    tipo: str
    valor: str
    severidad: Severidad
    peso: int
    detalle: str
    fuente: Literal["agente_identidad"] = FUENTE


class SalidaAnalizador(BaseModel):
    fuente: Literal["agente_identidad"] = FUENTE
    estado: Literal["ok", "parcial", "con_error"]
    resultados: dict
    hallazgos: list[Hallazgo]
    n_hallazgos: int
    consultas: int = 0
    nota: str | None = None

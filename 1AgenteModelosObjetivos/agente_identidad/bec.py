from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field

_GRADO_ABREV = re.compile(r"\b(?:Gral|Cnel|Tcnl|My|Cap|Tte|Subof|Sarg|Cte|Dir)\.\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+")
_GRADO_LARGO = re.compile(
    r"\b(?i:general|coronel|teniente coronel|mayor|capit[aá]n|teniente|suboficial|sargento|comandante)"
    r"\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+"
)
_CARGO = re.compile(
    r"(?i)\b(jefatura|jefe de\s+\w+|estado mayor|comandante|comando de\s+\w+|director(?:a)? (?:general|de)"
    r"|secretar[ií][ao] (?:general|de)|subsecretar[ií][ao]|ministr[oa] de)\b"
)
_22_DIGITOS = re.compile(r"(?<!\d)(\d(?:[ -]?\d){21})(?!\d)")
_ALIAS = re.compile(r"(?i)\balias(?:\s+(?:cbu|cvu|bancario))?\s*[:=]?\s*([a-z0-9][a-z0-9.\-]{4,18}[a-z0-9])\b")
_MONTO = re.compile(
    r"(?i)(?:\$|\bars\b|u\$s|\busd\b)\s?\d{1,3}(?:[.\s]\d{3})+(?:,\d{2})?"
    r"|\b\d{1,3}(?:\.\d{3})+(?:,\d{2})?\s?(?:pesos|d[oó]lares)\b"
)
_TRANSFERENCIA = re.compile(r"(?i)\b(transfer\w*|deposit\w*|gir(?:o|ar|es)|abon(?:o|ar|es)|pag(?:o|ar|ues))\b")
_URGENCIA_SECRETO = re.compile(
    r"(?i)\b(urgente|urgencia|hoy mismo|a la brevedad|confidencial|reservad[oa]|no lo comentes"
    r"|con discreci[oó]n|estoy en (?:una )?reuni[oó]n|no puedo atender)\b"
)

_PESOS_B1 = (7, 1, 3, 9, 7, 1, 3)
_PESOS_B2 = (3, 9, 7, 1, 3, 9, 7, 1, 3, 9, 7, 1, 3)


def cbu_valido(numero: str) -> bool:
    """Dígitos verificadores del CBU/CVU (BCRA): bloque 1 de 8 dígitos, bloque 2 de 14."""
    d = re.sub(r"\D", "", numero)
    if len(d) != 22:
        return False
    b1, b2 = d[:8], d[8:]
    v1 = (10 - sum(int(x) * p for x, p in zip(b1[:7], _PESOS_B1)) % 10) % 10
    v2 = (10 - sum(int(x) * p for x, p in zip(b2[:13], _PESOS_B2)) % 10) % 10
    return v1 == int(b1[7]) and v2 == int(b2[13])


def enmascarar(numero: str) -> str:
    d = re.sub(r"\D", "", numero)
    return f"{d[:3]}…{d[-4:]}" if len(d) > 7 else "…"


def huella_destino(valor: str) -> str:
    """Hash estable de un destino de pago (RA2-10, contrato RG-06): permite correlacionar campañas que piden
    transferir al mismo CBU/CVU/alias sin que el dato viaje en claro a otro componente."""
    return hashlib.sha256(f"centinela-destino:{valor}".encode()).hexdigest()[:16]


@dataclass
class SenalesBEC:
    autoridad: list[str] = field(default_factory=list)
    cbu: list[str] = field(default_factory=list)  # enmascarados
    cvu: list[str] = field(default_factory=list)  # enmascarados
    alias: list[str] = field(default_factory=list)
    montos: list[str] = field(default_factory=list)
    transferencia: bool = False
    urgencia_secreto: list[str] = field(default_factory=list)
    destinos_hash: list[str] = field(default_factory=list)

    @property
    def instruccion_pago(self) -> bool:
        return bool(self.cbu or self.cvu or self.alias) or (self.transferencia and bool(self.montos))

    @property
    def se_presenta_como_autoridad(self) -> bool:
        return bool(self.autoridad)

    def a_dict(self) -> dict:
        d = asdict(self)
        d["instruccion_pago"] = self.instruccion_pago
        return d


def extraer(nombre_visible: str, asunto: str, cuerpo: str) -> SenalesBEC:
    cuerpo = cuerpo or ""
    lineas = [l.strip() for l in cuerpo.strip().splitlines() if l.strip()]
    firma = "\n".join(lineas[-6:])
    zona_autoridad = "\n".join([nombre_visible or "", asunto or "", firma])

    autoridad: list[str] = []
    for patron in (_GRADO_ABREV, _GRADO_LARGO, _CARGO):
        for m in patron.finditer(zona_autoridad):
            texto = m.group(0).strip()
            if texto not in autoridad:
                autoridad.append(texto)

    cbu, cvu, huellas = [], [], []
    for m in _22_DIGITOS.finditer(cuerpo):
        if cbu_valido(m.group(1)):
            digitos = re.sub(r"\D", "", m.group(1))
            (cvu if digitos.startswith("000") else cbu).append(enmascarar(digitos))
            huellas.append(huella_destino(digitos))
    alias = [m.group(1).lower() for m in _ALIAS.finditer(cuerpo)]
    huellas += [huella_destino(a) for a in alias]

    return SenalesBEC(
        autoridad=autoridad,
        cbu=cbu,
        cvu=cvu,
        alias=alias,
        montos=[m.group(0) for m in _MONTO.finditer(cuerpo)],
        transferencia=bool(_TRANSFERENCIA.search(cuerpo)),
        urgencia_secreto=sorted({m.group(1).lower() for m in _URGENCIA_SECRETO.finditer(cuerpo)}),
        destinos_hash=sorted(set(huellas)),
    )

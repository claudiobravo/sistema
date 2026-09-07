"""Red de seguridad contra alucinaciones del LLM.

La regla de oro es simple: un código de seguimiento solo vale si se puede
demostrar. Cuando tenemos el texto original del documento (PDF con capa de
texto, o una nota escrita en el chat) exigimos que el código aparezca
*literalmente* en él. Cuando no lo tenemos (una captura o una etiqueta
escaneada) al menos exigimos que tenga forma de código de transportista real,
y avisamos en el chat para que un humano lo verifique.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Familias de códigos de los transportistas que salen por Vinted/Wallapop en España.
# Se comparan contra el código ya normalizado (mayúsculas, sin espacios ni guiones).
PATRONES_TRANSPORTISTA: dict[str, tuple[re.Pattern[str], ...]] = {
    "Correos": (
        re.compile(r"^[A-Z]{2}\d{9}ES$"),          # formato UPU S10 (certificados)
        re.compile(r"^(PQ|PK|CP|RR)[0-9A-Z]{14,20}$"),
    ),
    "Correos Express": (re.compile(r"^\d{13}$"),),
    "InPost": (
        re.compile(r"^\d{20,24}$"),
        re.compile(r"^6\d{11,15}$"),
    ),
    "Mondial Relay": (re.compile(r"^\d{8}$"),),
    "SEUR": (re.compile(r"^\d{10,11}$"),),
    "GLS": (re.compile(r"^\d{12,14}$"),),
    "CTT Express": (re.compile(r"^\d{12}$"),),
    "Boyacá": (re.compile(r"^\d{9,12}$"),),
    "UPS": (re.compile(r"^1Z[0-9A-Z]{16}$"),),
    "DHL": (re.compile(r"^\d{10}$"),),
}

# Cualquier código plausible: si no pasa ni esto, es basura o texto inventado.
PATRON_GENERICO = re.compile(r"^[0-9A-Z]{8,34}$")

# Códigos que aparecen en los ejemplos del prompt. Si el modelo devuelve uno de
# ellos es que está copiando el few-shot en vez de leer el documento.
CODIGOS_DE_EJEMPLO = frozenset(
    {
        "520012345678901234567890",
        "PQ8A1234567890123456",
        "12345678",
        "LK123456789ES",
    }
)

ALIAS_TRANSPORTISTA = {
    "inpost": "InPost",
    "in post": "InPost",
    "mondial relay": "Mondial Relay",
    "mondialrelay": "Mondial Relay",
    "punto pack": "Mondial Relay",
    "correos": "Correos",
    "correos express": "Correos Express",
    "correosexpress": "Correos Express",
    "seur": "SEUR",
    "gls": "GLS",
    "ctt": "CTT Express",
    "ctt express": "CTT Express",
    "boyaca": "Boyacá",
    "boyacá": "Boyacá",
    "ups": "UPS",
    "dhl": "DHL",
    "mrw": "MRW",
    "nacex": "Nacex",
    "envialia": "Envialia",
    "tipsa": "TIPSA",
    "packlink": "Packlink",
    "vinted go": "Vinted Go",
    "vintedgo": "Vinted Go",
}

ALIAS_PLATAFORMA = {
    "vinted": "Vinted",
    "wallapop": "Wallapop",
}

_NO_ALFANUMERICO = re.compile(r"[^0-9A-Z]")


def normalizar_codigo(codigo: str | None) -> str:
    """Deja el código en mayúsculas y sin separadores, para comparar sin ruido."""
    if not codigo:
        return ""
    return _NO_ALFANUMERICO.sub("", codigo.upper())


def detectar_transportista_por_codigo(codigo: str | None) -> str | None:
    """Devuelve el transportista cuyo formato encaja con el código, si es unívoco."""
    limpio = normalizar_codigo(codigo)
    if not limpio:
        return None
    candidatos = [
        nombre
        for nombre, patrones in PATRONES_TRANSPORTISTA.items()
        if any(p.match(limpio) for p in patrones)
    ]
    return candidatos[0] if len(candidatos) == 1 else None


def normalizar_transportista(nombre: str | None) -> str | None:
    if not nombre:
        return None
    limpio = " ".join(nombre.strip().lower().split())
    if not limpio:
        return None
    for alias, canonico in ALIAS_TRANSPORTISTA.items():
        if alias in limpio:
            return canonico
    return nombre.strip()[:60]


def normalizar_plataforma(valor: str | None, texto_contexto: str = "") -> str:
    fuente = f"{valor or ''} {texto_contexto}".lower()
    for alias, canonico in ALIAS_PLATAFORMA.items():
        if alias in fuente:
            return canonico
    return "Otro"


def normalizar_precio(valor: object) -> tuple[float | None, list[str]]:
    """Acepta 24, '24,50', '24.50 €' … y descarta lo que no tenga sentido."""
    if valor is None or valor == "":
        return None, []
    if isinstance(valor, bool):
        return None, ["precio descartado: no era un número"]
    if isinstance(valor, (int, float)):
        numero = float(valor)
    else:
        texto = str(valor).strip().replace("€", "").replace("EUR", "").strip()
        texto = texto.replace(" ", "")
        if "," in texto and "." in texto:  # 1.234,56 -> 1234.56
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", ".")
        try:
            numero = float(texto)
        except ValueError:
            return None, [f"precio ilegible descartado: {valor!r}"]
    if numero < 0:
        return None, ["precio negativo descartado"]
    if numero > 10_000:
        return None, [f"precio fuera de rango descartado: {numero}"]
    return round(numero, 2), []


@dataclass
class ResultadoValidacion:
    codigo_seguimiento: str | None = None
    transportista: str | None = None
    avisos: list[str] = field(default_factory=list)
    verificado_en_fuente: bool = False


def validar_codigo_seguimiento(
    codigo: str | None,
    *,
    texto_fuente: str | None,
    transportista: str | None = None,
) -> ResultadoValidacion:
    """Valida el código devuelto por el LLM.

    `texto_fuente` es el texto real del documento cuando lo tenemos. Si viene,
    la comprobación es dura: o el código está ahí escrito, o se descarta.
    """
    resultado = ResultadoValidacion(transportista=normalizar_transportista(transportista))
    limpio = normalizar_codigo(codigo)
    if not limpio:
        return resultado

    if limpio in CODIGOS_DE_EJEMPLO:
        resultado.avisos.append(
            "código descartado: coincide con un ejemplo del prompt (alucinación)"
        )
        return resultado

    if not PATRON_GENERICO.match(limpio):
        resultado.avisos.append(f"código descartado por formato imposible: {codigo!r}")
        return resultado

    if texto_fuente:
        if normalizar_codigo(texto_fuente).find(limpio) == -1:
            resultado.avisos.append(
                "código descartado: no aparece literalmente en el documento"
            )
            return resultado
        resultado.verificado_en_fuente = True

    detectado = detectar_transportista_por_codigo(limpio)
    if detectado and not resultado.transportista:
        resultado.transportista = detectado
    elif detectado and resultado.transportista and detectado != resultado.transportista:
        resultado.avisos.append(
            f"el formato del código parece de {detectado}, no de {resultado.transportista}"
        )

    if not resultado.verificado_en_fuente and detectado is None:
        resultado.avisos.append(
            "código sin verificar: formato no reconocido, compruébalo a mano"
        )

    resultado.codigo_seguimiento = codigo.strip() if codigo else None
    return resultado

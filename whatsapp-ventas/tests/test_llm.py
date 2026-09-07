"""Pruebas del proveedor Anthropic con un cliente falso (no toca la red)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.llm import EntradaExtraccion, ErrorLLM, _parsear_json
from tests.conftest import venta

anthropic = pytest.importorskip("anthropic")


class MensajesFalsos:
    def __init__(self, respuesta_parse=None, respuesta_create=None, error_parse=None):
        self.respuesta_parse = respuesta_parse
        self.respuesta_create = respuesta_create
        self.error_parse = error_parse
        self.llamadas: list[dict] = []

    def parse(self, **kwargs):
        self.llamadas.append({"metodo": "parse", **kwargs})
        if self.error_parse:
            raise self.error_parse
        return self.respuesta_parse

    def create(self, **kwargs):
        self.llamadas.append({"metodo": "create", **kwargs})
        return self.respuesta_create


def _respuesta(parsed=None, texto="", stop_reason="end_turn"):
    return SimpleNamespace(
        parsed_output=parsed,
        stop_reason=stop_reason,
        stop_details=None,
        content=[SimpleNamespace(type="text", text=texto)],
    )


def _proveedor(ajustes, mensajes):
    from app.llm import ProveedorAnthropic

    proveedor = ProveedorAnthropic(ajustes)
    proveedor._cliente = SimpleNamespace(messages=mensajes)
    return proveedor


def _error_400():
    import httpx

    respuesta = httpx.Response(400, request=httpx.Request("POST", "https://api.anthropic.com"))
    return anthropic.BadRequestError("output_format no soportado", response=respuesta, body=None)


def test_json_envuelto_en_markdown_se_interpreta():
    datos = venta().model_dump()
    assert _parsear_json("```json\n" + json.dumps(datos) + "\n```").articulo == datos["articulo"]
    assert _parsear_json("Aquí tienes: " + json.dumps(datos)).plataforma == "Vinted"


def test_json_invalido_da_error_de_llm():
    with pytest.raises(ErrorLLM):
        _parsear_json("lo siento, no puedo")
    with pytest.raises(ErrorLLM):
        _parsear_json('{"legible": true}')  # incompleto para el esquema


def test_texto_usa_el_modelo_barato_y_no_manda_adjuntos(ajustes):
    mensajes = MensajesFalsos(respuesta_parse=_respuesta(parsed=venta()))
    proveedor = _proveedor(ajustes, mensajes)
    proveedor.extraer(EntradaExtraccion(instruccion="extrae esto", texto="vendida por 25€"))

    llamada = mensajes.llamadas[0]
    assert llamada["model"] == ajustes.modelo_texto
    bloques = llamada["messages"][0]["content"]
    assert [b["type"] for b in bloques] == ["text"]
    assert "vendida por 25€" in bloques[0]["text"]
    assert llamada["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_imagen_usa_el_modelo_con_vision(ajustes):
    mensajes = MensajesFalsos(respuesta_parse=_respuesta(parsed=venta()))
    proveedor = _proveedor(ajustes, mensajes)
    proveedor.extraer(
        EntradaExtraccion(instruccion="lee la etiqueta", imagenes=[("image/png", b"\x89PNG")])
    )
    llamada = mensajes.llamadas[0]
    assert llamada["model"] == ajustes.modelo_vision
    bloques = llamada["messages"][0]["content"]
    assert bloques[0]["type"] == "image"
    assert bloques[0]["source"]["media_type"] == "image/png"


def test_pdf_nativo_va_como_bloque_document(ajustes):
    mensajes = MensajesFalsos(respuesta_parse=_respuesta(parsed=venta()))
    proveedor = _proveedor(ajustes, mensajes)
    proveedor.extraer(EntradaExtraccion(instruccion="lee la etiqueta", pdf=b"%PDF-1.4"))
    bloques = mensajes.llamadas[0]["messages"][0]["content"]
    assert bloques[0]["type"] == "document"
    assert bloques[0]["source"]["media_type"] == "application/pdf"


def test_si_no_hay_salidas_estructuradas_se_cae_al_modo_texto(ajustes):
    mensajes = MensajesFalsos(
        error_parse=_error_400(),
        respuesta_create=_respuesta(texto=json.dumps(venta().model_dump())),
    )
    proveedor = _proveedor(ajustes, mensajes)
    resultado = proveedor.extraer(EntradaExtraccion(instruccion="extrae", texto="hola"))
    assert resultado.plataforma == "Vinted"
    assert [ll["metodo"] for ll in mensajes.llamadas] == ["parse", "create"]


def test_un_rechazo_del_modelo_se_convierte_en_error_de_llm(ajustes):
    mensajes = MensajesFalsos(respuesta_parse=_respuesta(stop_reason="refusal"))
    proveedor = _proveedor(ajustes, mensajes)
    with pytest.raises(ErrorLLM):
        proveedor.extraer(EntradaExtraccion(instruccion="extrae", texto="hola"))


def test_el_modelo_de_gemini_por_defecto_no_es_uno_retirado():
    """gemini-2.0-flash estaba por defecto y Google ya lo ha retirado.

    Falla con 404 en cada mensaje, y como el error salta dentro del contenedor
    solo se ve en el grupo. Este test no comprueba la red: fija el valor para
    que cambiarlo sin querer salte aqui y no en produccion.
    """
    from app.config import Ajustes

    ajustes = Ajustes(_env_file=None)
    assert ajustes.gemini_modelo == "gemini-2.5-flash"
    # Un alias se mueve solo de modelo: eso es justo lo que no queremos.
    assert not ajustes.gemini_modelo.endswith("-latest")

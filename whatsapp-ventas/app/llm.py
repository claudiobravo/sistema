"""Proveedores de extracción. La interfaz es una sola función: `extraer`.

Se soportan tres backends porque el coste y la privacidad importan aquí:
- Anthropic (por defecto): Haiku 4.5 para texto, Sonnet 5 para visión.
- Gemini: alternativa barata con visión.
- Ollama: 100% local, para quien no quiera que las etiquetas salgan del servidor.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Protocol

from .config import Ajustes
from .models import VentaExtraida
from .prompts import SYSTEM_PROMPT

log = logging.getLogger(__name__)

_BLOQUE_JSON = re.compile(r"\{.*\}", re.DOTALL)


class ErrorLLM(Exception):
    """Fallo al hablar con el modelo o al interpretar su respuesta."""


@dataclass
class EntradaExtraccion:
    """Material que se le manda al modelo para una única extracción."""

    instruccion: str
    texto: str | None = None
    imagenes: list[tuple[str, bytes]] = field(default_factory=list)
    pdf: bytes | None = None
    nombre_fichero: str | None = None

    @property
    def usa_vision(self) -> bool:
        return bool(self.imagenes) or self.pdf is not None

    @property
    def texto_completo(self) -> str:
        """Instrucción y contenido en un único bloque de texto para el modelo."""
        if self.texto:
            return f"{self.instruccion}\n\n{self.texto}"
        return self.instruccion


class ProveedorLLM(Protocol):
    nombre: str

    def extraer(self, entrada: EntradaExtraccion) -> VentaExtraida: ...


def _parsear_json(texto: str) -> VentaExtraida:
    """Interpreta la respuesta del modelo aunque venga envuelta en ```json."""
    limpio = texto.strip()
    if limpio.startswith("```"):
        limpio = re.sub(r"^```[a-zA-Z]*\n?", "", limpio)
        limpio = re.sub(r"\n?```$", "", limpio).strip()
    try:
        datos = json.loads(limpio)
    except json.JSONDecodeError:
        encontrado = _BLOQUE_JSON.search(limpio)
        if not encontrado:
            raise ErrorLLM(f"el modelo no devolvió JSON: {texto[:200]!r}") from None
        try:
            datos = json.loads(encontrado.group(0))
        except json.JSONDecodeError as exc:
            raise ErrorLLM(f"JSON inválido del modelo: {exc}") from exc
    try:
        return VentaExtraida.model_validate(datos)
    except Exception as exc:
        raise ErrorLLM(f"el JSON del modelo no cumple el esquema: {exc}") from exc


# --------------------------------------------------------------------------
# Anthropic
# --------------------------------------------------------------------------
class ProveedorAnthropic:
    nombre = "anthropic"

    def __init__(self, ajustes: Ajustes) -> None:
        import anthropic  # import perezoso: los otros proveedores no lo necesitan

        self._anthropic = anthropic
        self._cliente = anthropic.Anthropic(
            api_key=ajustes.anthropic_api_key or None,
            timeout=ajustes.llm_timeout,
            max_retries=2,
        )
        self._ajustes = ajustes

    def _modelo(self, entrada: EntradaExtraccion) -> str:
        return self._ajustes.modelo_vision if entrada.usa_vision else self._ajustes.modelo_texto

    def _bloques(self, entrada: EntradaExtraccion) -> list[dict]:
        bloques: list[dict] = []
        if entrada.pdf is not None:
            bloques.append(
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": base64.standard_b64encode(entrada.pdf).decode("ascii"),
                    },
                }
            )
        for mimetype, datos in entrada.imagenes:
            bloques.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mimetype,
                        "data": base64.standard_b64encode(datos).decode("ascii"),
                    },
                }
            )
        bloques.append({"type": "text", "text": entrada.texto_completo})
        return bloques

    def extraer(self, entrada: EntradaExtraccion) -> VentaExtraida:
        sistema = [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]
        mensajes = [{"role": "user", "content": self._bloques(entrada)}]
        comunes = {
            "model": self._modelo(entrada),
            "max_tokens": self._ajustes.llm_max_tokens,
            "system": sistema,
            "messages": mensajes,
        }
        try:
            respuesta = self._cliente.messages.parse(
                **comunes, output_format=VentaExtraida
            )
            self._comprobar_parada(respuesta)
            if getattr(respuesta, "parsed_output", None) is not None:
                return respuesta.parsed_output
            return _parsear_json(self._texto(respuesta))
        except self._anthropic.BadRequestError as exc:
            # Algún modelo o pasarela sin salidas estructuradas: se pide el JSON
            # por prompt y se valida en casa.
            log.warning("salida estructurada no disponible (%s); uso el modo texto", exc)
            respuesta = self._cliente.messages.create(**comunes)
            self._comprobar_parada(respuesta)
            return _parsear_json(self._texto(respuesta))
        except self._anthropic.APIStatusError as exc:
            raise ErrorLLM(f"error de la API de Anthropic ({exc.status_code}): {exc}") from exc
        except self._anthropic.APIConnectionError as exc:
            raise ErrorLLM(f"no he podido conectar con la API de Anthropic: {exc}") from exc

    def _comprobar_parada(self, respuesta) -> None:
        if getattr(respuesta, "stop_reason", None) == "refusal":
            detalles = getattr(respuesta, "stop_details", None)
            raise ErrorLLM(f"el modelo rechazó el documento ({detalles})")

    @staticmethod
    def _texto(respuesta) -> str:
        return "".join(b.text for b in respuesta.content if getattr(b, "type", "") == "text")


# --------------------------------------------------------------------------
# Gemini
# --------------------------------------------------------------------------
class ProveedorGemini:
    nombre = "gemini"

    def __init__(self, ajustes: Ajustes) -> None:
        import httpx

        self._ajustes = ajustes
        self._cliente = httpx.Client(timeout=ajustes.llm_timeout)

    def extraer(self, entrada: EntradaExtraccion) -> VentaExtraida:
        partes: list[dict] = []
        if entrada.pdf is not None:
            partes.append(
                {
                    "inline_data": {
                        "mime_type": "application/pdf",
                        "data": base64.standard_b64encode(entrada.pdf).decode("ascii"),
                    }
                }
            )
        for mimetype, datos in entrada.imagenes:
            partes.append(
                {
                    "inline_data": {
                        "mime_type": mimetype,
                        "data": base64.standard_b64encode(datos).decode("ascii"),
                    }
                }
            )
        partes.append({"text": entrada.texto_completo})

        url = (
            f"{self._ajustes.gemini_base_url}/v1beta/models/"
            f"{self._ajustes.gemini_modelo}:generateContent"
        )
        cuerpo = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": partes}],
            "generationConfig": {
                "temperature": 0,
                "maxOutputTokens": self._ajustes.llm_max_tokens,
                "response_mime_type": "application/json",
            },
        }
        try:
            respuesta = self._cliente.post(
                url, json=cuerpo, headers={"x-goog-api-key": self._ajustes.gemini_api_key}
            )
            respuesta.raise_for_status()
            datos = respuesta.json()
        except Exception as exc:
            raise ErrorLLM(f"error llamando a Gemini: {exc}") from exc
        try:
            texto_salida = datos["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise ErrorLLM(f"respuesta inesperada de Gemini: {datos}") from exc
        return _parsear_json(texto_salida)


# --------------------------------------------------------------------------
# Ollama (local)
# --------------------------------------------------------------------------
class ProveedorOllama:
    nombre = "ollama"

    def __init__(self, ajustes: Ajustes) -> None:
        import httpx

        self._ajustes = ajustes
        self._cliente = httpx.Client(timeout=ajustes.llm_timeout)

    def extraer(self, entrada: EntradaExtraccion) -> VentaExtraida:
        if entrada.pdf is not None:
            raise ErrorLLM("Ollama no lee PDFs: rasteriza la etiqueta antes (PDF_NATIVO=false)")
        mensaje: dict = {"role": "user", "content": entrada.texto_completo}
        if entrada.imagenes:
            mensaje["images"] = [
                base64.standard_b64encode(datos).decode("ascii") for _, datos in entrada.imagenes
            ]
        cuerpo = {
            "model": self._ajustes.ollama_modelo,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, mensaje],
            "stream": False,
            "format": VentaExtraida.model_json_schema(),
            "options": {"temperature": 0},
        }
        try:
            respuesta = self._cliente.post(f"{self._ajustes.ollama_base_url}/api/chat", json=cuerpo)
            respuesta.raise_for_status()
            datos = respuesta.json()
        except Exception as exc:
            raise ErrorLLM(f"error llamando a Ollama: {exc}") from exc
        return _parsear_json(datos.get("message", {}).get("content", ""))


def construir_proveedor(ajustes: Ajustes) -> ProveedorLLM:
    if ajustes.llm_proveedor == "anthropic":
        return ProveedorAnthropic(ajustes)
    if ajustes.llm_proveedor == "gemini":
        return ProveedorGemini(ajustes)
    if ajustes.llm_proveedor == "ollama":
        return ProveedorOllama(ajustes)
    raise ValueError(f"proveedor LLM desconocido: {ajustes.llm_proveedor}")

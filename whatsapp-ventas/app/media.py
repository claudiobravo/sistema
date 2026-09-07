"""Tratamiento de los adjuntos: PDFs de etiqueta e imágenes."""

from __future__ import annotations

import logging
import re
from typing import Literal

log = logging.getLogger(__name__)

TipoMedia = Literal["pdf", "imagen", "otro"]

MIMES_IMAGEN = {"image/jpeg", "image/png", "image/gif", "image/webp"}
_ESPACIOS = re.compile(r"[ \t]+")
_LINEAS_VACIAS = re.compile(r"\n{3,}")


class MediaNoLegible(Exception):
    """El adjunto existe pero no hay forma de sacarle contenido."""


def detectar_tipo(datos: bytes, mimetype: str | None = None, nombre: str | None = None) -> TipoMedia:
    """Decide el tipo mirando primero los bytes; el mimetype de WhatsApp miente a veces."""
    if datos[:5] == b"%PDF-":
        return "pdf"
    if datos[:8] == b"\x89PNG\r\n\x1a\n" or datos[:3] == b"\xff\xd8\xff":
        return "imagen"
    if datos[:4] == b"RIFF" and datos[8:12] == b"WEBP":
        return "imagen"
    if datos[:6] in (b"GIF87a", b"GIF89a"):
        return "imagen"
    mime = (mimetype or "").lower()
    if mime == "application/pdf" or (nombre or "").lower().endswith(".pdf"):
        return "pdf"
    if mime.startswith("image/"):
        return "imagen"
    return "otro"


def mimetype_imagen(datos: bytes, mimetype: str | None = None) -> str:
    """Mimetype que aceptan las APIs de visión, deducido de los bytes."""
    if datos[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if datos[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if datos[:4] == b"RIFF" and datos[8:12] == b"WEBP":
        return "image/webp"
    if datos[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    mime = (mimetype or "").split(";")[0].strip().lower()
    if mime in MIMES_IMAGEN:
        return mime
    raise MediaNoLegible(f"formato de imagen no soportado: {mimetype or 'desconocido'}")


def limpiar_texto(texto: str) -> str:
    texto = texto.replace("\r\n", "\n").replace("\x00", "")
    texto = _ESPACIOS.sub(" ", texto)
    texto = "\n".join(linea.strip() for linea in texto.split("\n"))
    return _LINEAS_VACIAS.sub("\n\n", texto).strip()


def extraer_texto_pdf(datos: bytes, max_paginas: int = 2) -> str:
    """Saca la capa de texto del PDF. Devuelve '' si el PDF es una imagen escaneada.

    Se intenta con pdfplumber (mejor con tablas y etiquetas maquetadas) y, si
    falla, con pypdf, que aguanta algunos PDFs que pdfplumber rechaza.
    """
    texto = _texto_con_pdfplumber(datos, max_paginas)
    if not texto.strip():
        texto = _texto_con_pypdf(datos, max_paginas)
    return limpiar_texto(texto)


def _texto_con_pdfplumber(datos: bytes, max_paginas: int) -> str:
    try:
        import io

        import pdfplumber
    except ImportError:  # pragma: no cover - dependencia declarada en requirements
        return ""
    try:
        with pdfplumber.open(io.BytesIO(datos)) as pdf:
            paginas = pdf.pages[:max_paginas]
            return "\n".join((p.extract_text() or "") for p in paginas)
    except Exception as exc:
        log.warning("pdfplumber no pudo abrir el PDF: %s", exc)
        return ""


def _texto_con_pypdf(datos: bytes, max_paginas: int) -> str:
    try:
        import io

        from pypdf import PdfReader
    except ImportError:  # pragma: no cover
        return ""
    try:
        lector = PdfReader(io.BytesIO(datos))
        return "\n".join((p.extract_text() or "") for p in lector.pages[:max_paginas])
    except Exception as exc:
        log.warning("pypdf no pudo abrir el PDF: %s", exc)
        return ""


def texto_suficiente(texto: str, minimo: int) -> bool:
    """¿Hay capa de texto de verdad, o son cuatro caracteres sueltos del render?"""
    return len(re.sub(r"\s", "", texto)) >= minimo


def pdf_a_imagenes(datos: bytes, dpi: int = 200, max_paginas: int = 2) -> list[bytes]:
    """Rasteriza el PDF a PNG para mandarlo a un modelo con visión.

    Requiere poppler-utils (`pdftoppm`), que la imagen Docker ya instala.
    """
    try:
        from pdf2image import convert_from_bytes
    except ImportError as exc:  # pragma: no cover - dependencia opcional
        raise MediaNoLegible(
            "pdf2image no está instalado: no puedo rasterizar un PDF sin capa de texto"
        ) from exc
    try:
        paginas = convert_from_bytes(datos, dpi=dpi, fmt="png", first_page=1, last_page=max_paginas)
    except Exception as exc:
        raise MediaNoLegible(f"no he podido rasterizar el PDF: {exc}") from exc

    import io

    salida: list[bytes] = []
    for pagina in paginas:
        buffer = io.BytesIO()
        pagina.save(buffer, format="PNG")
        salida.append(buffer.getvalue())
    if not salida:
        raise MediaNoLegible("el PDF no tiene páginas")
    return salida

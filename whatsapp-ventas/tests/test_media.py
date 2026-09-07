import pytest

from app.media import (
    MediaNoLegible,
    detectar_tipo,
    extraer_texto_pdf,
    limpiar_texto,
    mimetype_imagen,
    texto_suficiente,
)
from tests.utiles import PNG_1x1, pdf_de_prueba


def test_detecta_el_tipo_por_los_bytes_aunque_mienta_el_mimetype():
    pdf = pdf_de_prueba(["hola"])
    assert detectar_tipo(pdf, "image/jpeg", "cosa.jpg") == "pdf"
    assert detectar_tipo(PNG_1x1, "application/pdf", "cosa.pdf") == "imagen"
    assert detectar_tipo(b"texto plano", "text/plain", "a.txt") == "otro"


def test_detecta_pdf_por_mimetype_si_los_bytes_no_dicen_nada():
    assert detectar_tipo(b"\x01\x02\x03", "application/pdf") == "pdf"


def test_mimetype_de_imagen():
    assert mimetype_imagen(PNG_1x1) == "image/png"
    assert mimetype_imagen(b"\xff\xd8\xff\xe0algo") == "image/jpeg"
    with pytest.raises(MediaNoLegible):
        mimetype_imagen(b"\x00\x01", "application/zip")


def test_extrae_la_capa_de_texto_de_una_etiqueta():
    pdf = pdf_de_prueba(
        ["InPost", "N de envio: 5200 1234 5678 9012 3456 7891", "Destinatario: MARIA G."]
    )
    texto = extraer_texto_pdf(pdf)
    assert "InPost" in texto
    assert "5200 1234 5678 9012 3456 7891" in texto
    assert texto_suficiente(texto, 40) is True


def test_pdf_sin_texto_util_se_detecta_como_escaneado():
    pdf = pdf_de_prueba(["x"])
    assert texto_suficiente(extraer_texto_pdf(pdf), 80) is False


def test_pdf_corrupto_no_revienta():
    assert extraer_texto_pdf(b"%PDF-1.4\nbasura") == ""


def test_limpiar_texto():
    assert limpiar_texto("  hola   mundo \r\n\n\n\n adios ") == "hola mundo\n\nadios"

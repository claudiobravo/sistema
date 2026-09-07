from app.validacion import (
    detectar_transportista_por_codigo,
    normalizar_codigo,
    normalizar_plataforma,
    normalizar_precio,
    normalizar_transportista,
    validar_codigo_seguimiento,
)


def test_normalizar_codigo_quita_separadores():
    assert normalizar_codigo(" 5200-1234 5678 ") == "520012345678"
    assert normalizar_codigo(None) == ""


def test_detecta_transportista_por_formato():
    assert detectar_transportista_por_codigo("LK123456789ES") == "Correos"
    assert detectar_transportista_por_codigo("1Z999AA10123456784") == "UPS"
    assert detectar_transportista_por_codigo("no-es-un-codigo") is None


def test_codigo_presente_en_el_pdf_se_acepta_y_se_verifica():
    texto = "InPost\nNº de envío: 5200 1234 5678 9012 3456 7891\nDestinatario: MARIA G."
    resultado = validar_codigo_seguimiento(
        "520012345678901234567891", texto_fuente=texto, transportista="inpost"
    )
    assert resultado.codigo_seguimiento == "520012345678901234567891"
    assert resultado.verificado_en_fuente is True
    assert resultado.transportista == "InPost"
    assert resultado.avisos == []


def test_codigo_inventado_se_descarta_cuando_hay_texto_fuente():
    texto = "Correos\nDestinatario: Laura Pérez\nAcuse de recibo"
    resultado = validar_codigo_seguimiento("LK987654321ES", texto_fuente=texto)
    assert resultado.codigo_seguimiento is None
    assert "no aparece literalmente" in resultado.avisos[0]


def test_codigo_de_ejemplo_del_prompt_se_descarta():
    resultado = validar_codigo_seguimiento(
        "5200 1234 5678 9012 3456 7890", texto_fuente=None
    )
    assert resultado.codigo_seguimiento is None
    assert "ejemplo del prompt" in resultado.avisos[0]


def test_sin_texto_fuente_un_formato_raro_se_acepta_pero_avisa():
    resultado = validar_codigo_seguimiento("ABC123XYZ789Q", texto_fuente=None)
    assert resultado.codigo_seguimiento == "ABC123XYZ789Q"
    assert any("compruébalo a mano" in aviso for aviso in resultado.avisos)


def test_formato_imposible_se_descarta():
    assert validar_codigo_seguimiento("n/a", texto_fuente=None).codigo_seguimiento is None


def test_discrepancia_entre_transportista_y_formato_avisa():
    resultado = validar_codigo_seguimiento(
        "1Z999AA10123456784", texto_fuente=None, transportista="Correos"
    )
    assert any("parece de UPS" in aviso for aviso in resultado.avisos)


def test_precios():
    assert normalizar_precio("24,50 €") == (24.5, [])
    assert normalizar_precio("1.234,56") == (1234.56, [])
    assert normalizar_precio(18) == (18.0, [])
    assert normalizar_precio(None) == (None, [])
    assert normalizar_precio("gratis")[0] is None
    assert normalizar_precio(-5)[0] is None
    assert normalizar_precio(99999)[0] is None


def test_plataforma_y_transportista():
    assert normalizar_plataforma("vinted") == "Vinted"
    assert normalizar_plataforma(None, "vendido por wallapop") == "Wallapop"
    assert normalizar_plataforma(None, "un trueque") == "Otro"
    assert normalizar_transportista("MONDIAL RELAY") == "Mondial Relay"
    assert normalizar_transportista(None) is None

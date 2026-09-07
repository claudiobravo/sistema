from app.validacion import (
    detectar_transportista_por_codigo,
    familias_que_encajan,
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


# --- Capa 3: formato conocido. Casos vistos al preparar la puesta en marcha ---


def test_las_familias_que_encajan_se_devuelven_todas():
    """Los rangos de los transportistas españoles se solapan mucho."""
    assert familias_que_encajan("1234567890") == ["SEUR", "Boyacá", "DHL"]
    assert familias_que_encajan("12345678") == ["Mondial Relay"]
    assert familias_que_encajan("no-es-un-codigo") == []


def test_un_codigo_ambiguo_dice_que_es_ambiguo_y_no_que_no_se_reconoce():
    """Antes los dos casos daban el mismo aviso, y eran cosas distintas.

    Un aviso que salta con todos los transportistas numéricos deja de leerse.
    """
    resultado = validar_codigo_seguimiento("1234567890", texto_fuente=None)
    assert resultado.codigo_seguimiento == "1234567890"
    aviso = " ".join(resultado.avisos)
    assert "varios transportistas" in aviso
    assert "SEUR" in aviso and "DHL" in aviso
    assert "formato no reconocido" not in aviso


def test_el_transportista_de_la_etiqueta_desambigua_y_deja_de_avisar():
    """Si la etiqueta dice SEUR y el código encaja con SEUR, no hay nada que avisar.

    Antes se avisaba igual, porque el código también encajaba con DHL y con
    Boyacá y la detección se rendía.
    """
    resultado = validar_codigo_seguimiento(
        "1234567890", texto_fuente=None, transportista="SEUR"
    )
    assert resultado.codigo_seguimiento == "1234567890"
    assert resultado.transportista == "SEUR"
    assert resultado.avisos == []


def test_si_el_formato_no_respalda_al_transportista_declarado_se_avisa():
    resultado = validar_codigo_seguimiento(
        "1234567890", texto_fuente=None, transportista="Correos"
    )
    assert any("no de Correos" in aviso for aviso in resultado.avisos)


def test_un_codigo_verificado_en_el_documento_no_arrastra_avisos_de_formato():
    """La capa 3 es un respaldo de la 2, no un juez por encima de ella."""
    texto = "SEUR\nExpedición: 1234567890\nDestinatario: A. G."
    resultado = validar_codigo_seguimiento("1234567890", texto_fuente=texto)
    assert resultado.verificado_en_fuente is True
    assert resultado.avisos == []


def test_la_verificacion_literal_sigue_mandando_sobre_todo_lo_demas():
    """Blindaje: aunque el formato sea perfecto, si no está en el papel, fuera."""
    texto = "SEUR\nExpedición: 1234567890"
    resultado = validar_codigo_seguimiento(
        "9999999999", texto_fuente=texto, transportista="SEUR"
    )
    assert resultado.codigo_seguimiento is None
    assert "no aparece literalmente" in resultado.avisos[0]

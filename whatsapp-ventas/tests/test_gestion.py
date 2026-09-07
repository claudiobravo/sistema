"""Alta del gateway: los formatos de `webhook/set` y la comprobación posterior."""

from tools.gestion import _base64_activo, cuerpos_webhook

URL = "http://bot:8000/webhook/token-de-prueba"


def test_se_prueban_los_tres_formatos_conocidos_en_orden():
    nombres = [nombre for nombre, _ in cuerpos_webhook(URL)]
    assert nombres == ["anidado (v2.1+)", "camelCase plano", "snake_case (v2.0)"]


def test_los_tres_formatos_encienden_el_base64_con_su_propia_clave():
    """Cada versión de Evolution llama distinto a la clave del base64.

    Si se manda el nombre que no toca, el gateway puede aceptar el cuerpo y
    dejar el base64 apagado: el bot seguiría yendo, pero pidiendo cada adjunto
    al gateway por separado.
    """
    cuerpos = dict(cuerpos_webhook(URL))
    assert cuerpos["anidado (v2.1+)"]["webhook"]["base64"] is True
    assert cuerpos["camelCase plano"]["webhookBase64"] is True
    assert cuerpos["snake_case (v2.0)"]["webhook_base64"] is True


def test_todos_los_formatos_llevan_la_url_y_solo_messages_upsert():
    for _, cuerpo in cuerpos_webhook(URL):
        plano = cuerpo.get("webhook", cuerpo)
        assert plano["url"] == URL
        assert plano["enabled"] is True
        assert plano["events"] == ["MESSAGES_UPSERT"]


def test_se_detecta_el_base64_en_la_respuesta_sea_cual_sea_el_formato():
    assert _base64_activo({"webhook": {"base64": True}}) is True
    assert _base64_activo({"webhook": {"base64": False}}) is False
    assert _base64_activo({"webhookBase64": True}) is True
    assert _base64_activo({"webhook_base64": False}) is False


def test_si_no_se_puede_saber_no_se_inventa():
    """None es «no lo sé», y no se avisa. Distinto de False, que sí avisa."""
    assert _base64_activo({}) is None
    assert _base64_activo({"url": "x"}) is None
    assert _base64_activo(None) is None
    assert _base64_activo("no es un dict") is None

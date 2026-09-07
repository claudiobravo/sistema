"""Traducción de los payloads de Evolution.

Los casos de aquí salieron de preparar la puesta en marcha real: son formas de
mensaje que WhatsApp manda a diario y que el parser dejaba a medias.
"""

from app.evolution import _capas, _desenvolver, parsear_mensaje


def _payload(mensaje: dict, **extra) -> dict:
    datos = {
        "key": {"remoteJid": "120363000000000000@g.us", "id": "MSG1"},
        "messageTimestamp": 1757260000,
        "message": mensaje,
    }
    datos.update(extra)
    return {"event": "messages.upsert", "data": datos}


def test_el_base64_sobrevive_a_un_pdf_con_pie_de_foto():
    """El caso estrella: etiqueta en PDF con el precio en el pie de foto.

    Evolution cuelga el base64 del `message` de primer nivel, pero WhatsApp
    envuelve el documento en `documentWithCaptionMessage`. Al desenvolver se
    perdía el nivel donde estaba el base64 y había que volver a pedir el
    fichero al gateway en cada etiqueta.
    """
    mensaje = parsear_mensaje(
        _payload(
            {
                "documentWithCaptionMessage": {
                    "message": {
                        "documentMessage": {
                            "mimetype": "application/pdf",
                            "fileName": "etiqueta.pdf",
                            "caption": "Vendida por 25 euros",
                        }
                    }
                },
                "base64": "JVBERi0xLjQK",
            }
        )
    )
    assert mensaje is not None
    assert mensaje.base64 == "JVBERi0xLjQK"
    assert mensaje.tiene_media is True
    assert mensaje.nombre_fichero == "etiqueta.pdf"
    assert mensaje.texto == "Vendida por 25 euros"


def test_el_base64_sobrevive_a_varios_envoltorios_anidados():
    mensaje = parsear_mensaje(
        _payload(
            {
                "ephemeralMessage": {
                    "message": {
                        "viewOnceMessageV2": {
                            "message": {"imageMessage": {"mimetype": "image/jpeg"}}
                        }
                    }
                },
                "base64": "AAAA",
            }
        )
    )
    assert mensaje.base64 == "AAAA"
    assert mensaje.tiene_media is True


def test_el_base64_se_sigue_encontrando_donde_ya_se_buscaba():
    """Las rutas que ya funcionaban no se tocan."""
    sin_envoltorio = parsear_mensaje(
        _payload({"documentMessage": {"mimetype": "application/pdf"}, "base64": "SGkK"})
    )
    assert sin_envoltorio.base64 == "SGkK"

    en_el_dato = parsear_mensaje(
        _payload({"imageMessage": {"mimetype": "image/png"}}, base64="T1RSTw==")
    )
    assert en_el_dato.base64 == "T1RSTw=="

    en_media = parsear_mensaje(
        _payload({"imageMessage": {"mimetype": "image/png"}}, media={"base64": "TUVE"})
    )
    assert en_media.base64 == "TUVE"


def test_sin_base64_en_ninguna_capa_devuelve_none():
    mensaje = parsear_mensaje(_payload({"documentMessage": {"mimetype": "application/pdf"}}))
    assert mensaje.base64 is None


def test_capas_devuelve_el_sobre_y_el_interior():
    interior = {"documentMessage": {"mimetype": "application/pdf"}}
    sobre = {"documentWithCaptionMessage": {"message": interior}, "base64": "X"}
    capas = _capas(sobre)
    assert capas[0] is sobre
    assert capas[-1] is interior
    assert _desenvolver(sobre) is interior


def test_un_evento_que_no_es_mensaje_se_ignora():
    assert parsear_mensaje({"event": "connection.update", "data": {}}) is None
    assert parsear_mensaje({"event": "messages.upsert", "data": {}}) is None

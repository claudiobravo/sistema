from app.formatting import (
    formatear_fecha,
    formatear_precio,
    mensaje_confirmacion,
    mensaje_ilegible,
    mensaje_pendientes,
)
from app.models import RegistroVenta


def _registro(**cambios) -> RegistroVenta:
    base = {
        "id": 7,
        "fecha_registro": "2026-09-07T08:30:00+00:00",
        "articulo": "Chaqueta vaquera Levi's talla S",
        "plataforma": "Vinted",
        "precio_venta": 1234.5,
        "transportista": "InPost",
        "codigo_seguimiento": "520012345678901234567891",
        "destinatario_o_punto_pack": "MARIA G.",
        "confianza": 0.9,
    }
    base.update(cambios)
    return RegistroVenta(**base)


def test_precio_en_formato_espanol():
    assert formatear_precio(24.5) == "24,50 €"
    assert formatear_precio(1234.5) == "1.234,50 €"
    assert formatear_precio(None) == "—"


def test_fecha_en_hora_local():
    assert formatear_fecha("2026-09-07T08:30:00+00:00", "Europe/Madrid") == "07/09/2026 10:30"
    assert formatear_fecha("no-es-fecha") == "no-es-fecha"


def test_confirmacion_lleva_todos_los_campos():
    texto = mensaje_confirmacion(_registro())
    assert "Venta registrada* #7" in texto
    assert "Chaqueta vaquera" in texto
    assert "1.234,50 €" in texto
    assert "520012345678901234567891" in texto
    assert "07/09/2026 10:30" in texto


def test_confirmacion_avisa_de_confianza_baja_y_de_los_avisos():
    texto = mensaje_confirmacion(
        _registro(confianza=0.3, avisos=["código sin verificar"]), creado=False
    )
    assert "Venta actualizada" in texto
    assert "Confianza baja" in texto
    assert "código sin verificar" in texto


def test_mensajes_auxiliares():
    assert "no se puede leer" in mensaje_ilegible(None)
    assert "borroso" in mensaje_ilegible("está borroso")
    assert "No hay ventas pendientes" in mensaje_pendientes([])
    assert "#7" in mensaje_pendientes([_registro()])


def test_si_falta_la_base_de_zonas_se_avisa_en_el_log(caplog):
    """El fallo era mudo: sin tzdata las horas salían en UTC y nadie se enteraba.

    La hora sigue saliendo (no se tira el mensaje por esto), pero queda rastro.
    """
    from app import formatting

    formatting._zona_horaria.cache_clear()
    with caplog.at_level("WARNING"):
        salida = formatting.formatear_fecha("2026-09-07T08:30:00+00:00", "Marte/Olympus")
    assert salida == "07/09/2026 08:30"
    assert "Marte/Olympus" in caplog.text
    formatting._zona_horaria.cache_clear()


def test_la_zona_se_resuelve_una_sola_vez():
    from app import formatting

    formatting._zona_horaria.cache_clear()
    formatting.formatear_fecha("2026-09-07T08:30:00+00:00", "Europe/Madrid")
    formatting.formatear_fecha("2026-09-08T08:30:00+00:00", "Europe/Madrid")
    assert formatting._zona_horaria.cache_info().hits == 1


def test_europe_madrid_esta_disponible_de_verdad():
    """Guarda contra el bug real: si esto falla, faltan las zonas horarias."""
    from app.formatting import _zona_horaria

    assert _zona_horaria("Europe/Madrid") is not None

from app.db import Almacen
from app.models import RegistroVenta


def _registro(**cambios) -> RegistroVenta:
    base = {
        "fecha_registro": "2026-09-07T10:00:00+00:00",
        "articulo": "Chaqueta vaquera",
        "plataforma": "Vinted",
        "precio_venta": 25.0,
        "transportista": "InPost",
        "codigo_seguimiento": "520012345678901234567891",
        "destinatario_o_punto_pack": "MARIA G.",
        "confianza": 0.9,
        "origen": "pdf",
        "mensaje_id": "MSG1",
    }
    base.update(cambios)
    return RegistroVenta(**base)


def test_guardar_e_incrementar_ids(tmp_path):
    almacen = Almacen(tmp_path / "v.db")
    almacen.inicializar()
    primero, creado = almacen.guardar(_registro())
    assert creado and primero.id == 1
    segundo, creado = almacen.guardar(_registro(codigo_seguimiento="99999999", mensaje_id="M2"))
    assert creado and segundo.id == 2


def test_mismo_tracking_fusiona_en_vez_de_duplicar(tmp_path):
    almacen = Almacen(tmp_path / "v.db")
    almacen.inicializar()
    # Primero llega la etiqueta: solo tracking y transportista.
    almacen.guardar(
        _registro(articulo=None, precio_venta=None, destinatario_o_punto_pack=None)
    )
    # Después, la captura de la venta con el mismo código.
    fusionado, creado = almacen.guardar(
        _registro(mensaje_id="MSG2", codigo_seguimiento="5200-1234 5678 9012 3456 7891",
                  avisos=["revisar"])
    )
    assert creado is False
    assert fusionado.id == 1
    assert fusionado.articulo == "Chaqueta vaquera"
    assert fusionado.precio_venta == 25.0
    assert fusionado.avisos == ["revisar"]
    assert len(almacen.listar()) == 1


def test_ventas_sin_tracking_no_se_fusionan(tmp_path):
    almacen = Almacen(tmp_path / "v.db")
    almacen.inicializar()
    almacen.guardar(_registro(codigo_seguimiento=None))
    almacen.guardar(_registro(codigo_seguimiento=None, mensaje_id="M2"))
    assert len(almacen.listar()) == 2


def test_buscar_por_referencia_y_cambiar_estado(tmp_path):
    almacen = Almacen(tmp_path / "v.db")
    almacen.inicializar()
    guardado, _ = almacen.guardar(_registro())
    assert almacen.buscar_por_referencia("#1").id == guardado.id
    assert almacen.buscar_por_referencia("5200 1234 5678 9012 3456 7891").id == guardado.id
    assert almacen.buscar_por_referencia("nada") is None
    actualizado = almacen.cambiar_estado(guardado.id, "enviado")
    assert actualizado.estado == "enviado"
    assert almacen.listar(estado="pendiente_envio") == []


def test_idempotencia_de_mensajes(tmp_path):
    almacen = Almacen(tmp_path / "v.db")
    almacen.inicializar()
    assert almacen.mensaje_visto("A") is False
    almacen.marcar_mensaje("A", "en_proceso")
    assert almacen.mensaje_visto("A") is True
    almacen.marcar_mensaje("A", "registrado")  # no revienta por conflicto


def test_resumen(tmp_path):
    almacen = Almacen(tmp_path / "v.db")
    almacen.inicializar()
    almacen.guardar(_registro())
    almacen.guardar(_registro(codigo_seguimiento="88888888", precio_venta=10.0))
    assert almacen.resumen() == {"total": 2, "pendientes": 2, "ingresos": 35.0}

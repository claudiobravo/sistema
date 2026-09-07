"""El puente que apunta en Glivo las ventas del bot.

Ninguna prueba toca Glivo: la función que escribe se inyecta, así que aquí se
comprueba la lógica sin ir a la base de producción de nadie.
"""

import json

from app.db import Almacen
from app.models import RegistroVenta
from tools.puente_glivo import (
    apuntar,
    canal_para_glivo,
    escribir_estado,
    leer_estado,
    seleccionar,
    texto_para_glivo,
)


class GlivoFalso:
    """Doble de `registro_diario.guardar_evento`."""

    def __init__(self, devuelve: int = 7):
        self.eventos: list[dict] = []
        self.devuelve = devuelve

    def __call__(self, **kwargs) -> int:
        self.eventos.append(kwargs)
        return self.devuelve


def _venta(**cambios) -> RegistroVenta:
    base = {
        "fecha_registro": "2026-09-07T10:00:00+00:00",
        "articulo": "Sudadera Nike gris talla M",
        "plataforma": "Wallapop",
        "precio_venta": 18.5,
        "transportista": "SEUR",
        "codigo_seguimiento": "7391045628",
        "origen": "texto",
        "mensaje_id": "MSG1",
    }
    base.update(cambios)
    return RegistroVenta(**base)


def _como_la_api(tmp_path, *ventas) -> list[dict]:
    """Lo que devolveria GET /ventas: se pasa por el Almacen real para que los
    ids y los valores por defecto sean los de verdad, no los que yo suponga."""
    almacen = Almacen(tmp_path / "ventas.db")
    almacen.inicializar()
    for venta in ventas:
        almacen.guardar(venta)
    return [v.model_dump() for v in almacen.listar(limite=200)]


# --- qué se apunta y qué no ------------------------------------------------


def test_canal_solo_para_las_plataformas_que_glivo_conoce():
    assert canal_para_glivo("Vinted") == "vinted"
    assert canal_para_glivo("wallapop") == "wallapop"
    assert canal_para_glivo("Otro") is None
    assert canal_para_glivo(None) is None


def test_una_venta_sin_precio_no_se_apunta(tmp_path):
    """Sin importe, Glivo abre una `venta_pendiente` y te pregunta por Telegram.

    Ese es justo el trabajo manual que el bot viene a quitar, así que se espera
    a que llegue el precio (normalmente al fusionar con la etiqueta).
    """
    api = _como_la_api(tmp_path, _venta(precio_venta=None, codigo_seguimiento=None))
    assert seleccionar(api, set()) == []


def test_una_venta_cancelada_no_se_apunta(tmp_path):
    api = _como_la_api(tmp_path, _venta(estado="cancelado"))
    assert seleccionar(api, set()) == []


def test_se_apunta_con_el_importe_el_canal_y_la_fecha(tmp_path):
    api = _como_la_api(tmp_path, _venta())
    glivo = GlivoFalso()

    apuntadas, problemas = apuntar(seleccionar(api, set()), glivo)

    assert apuntadas == [1]
    assert problemas == []
    evento = glivo.eventos[0]
    assert evento["tipo"] == "venta"
    assert evento["valor"] == 18.5
    assert evento["unidad"] == "eur"
    assert evento["canal"] == "wallapop"
    assert evento["fecha"] == "2026-09-07"
    assert "Sudadera Nike" in evento["texto_original"]


def test_el_texto_deja_rastro_de_que_viene_del_bot():
    """Sin la marca no habría forma de distinguirlas de las que apunta él."""
    texto = texto_para_glivo(
        {"id": 12, "articulo": "Camiseta", "transportista": "InPost"}
    )
    assert "[bot ventas #12]" in texto
    assert "Camiseta" in texto
    assert "InPost" in texto


def test_una_plataforma_desconocida_avisa_en_vez_de_inventarse_un_canal(tmp_path):
    api = _como_la_api(tmp_path, _venta(plataforma="Otro"))
    glivo = GlivoFalso()

    apuntadas, problemas = apuntar(seleccionar(api, set()), glivo)

    assert apuntadas == []
    assert glivo.eventos == []
    assert "no es un canal de Glivo" in problemas[0]


# --- no duplicar ------------------------------------------------------------


def test_lo_ya_apuntado_no_se_repite(tmp_path):
    api = _como_la_api(tmp_path, _venta(), _venta(codigo_seguimiento="8123456789", mensaje_id="M2"))
    assert len(seleccionar(api, set())) == 2
    assert [v["id"] for v in seleccionar(api, {1})] == [2]
    assert seleccionar(api, {1, 2}) == []


def test_el_estado_sobrevive_entre_pasadas(tmp_path):
    ruta = tmp_path / "estado.json"
    assert leer_estado(ruta) == set()  # todavía no existe
    escribir_estado(ruta, [3, 1, 2])
    assert leer_estado(ruta) == {1, 2, 3}
    assert json.loads(ruta.read_text())["apuntadas"] == [1, 2, 3]


def test_un_estado_corrupto_no_revienta_el_puente(tmp_path):
    """Peor caso: volver a apuntar algo. Mejor que caerse y no apuntar nada."""
    ruta = tmp_path / "estado.json"
    ruta.write_text("esto no es json")
    assert leer_estado(ruta) == set()


# --- el fallo silencioso de Glivo ------------------------------------------


def test_si_glivo_devuelve_menos_uno_no_se_da_por_apuntada(tmp_path):
    """`guardar_evento` falla en silencio devolviendo -1.

    Si el puente no mirara ese valor, marcaría la venta como apuntada y no
    volvería a intentarlo nunca: se perdería sin un solo error por ningún lado.
    """
    api = _como_la_api(tmp_path, _venta())
    glivo = GlivoFalso(devuelve=-1)

    apuntadas, problemas = apuntar(seleccionar(api, set()), glivo)

    assert apuntadas == []
    assert "devolvió -1" in problemas[0]
    # Y como no se apunta, la siguiente pasada la vuelve a coger.
    assert len(seleccionar(api, set())) == 1


def test_simular_no_escribe_nada(tmp_path):
    api = _como_la_api(tmp_path, _venta())
    glivo = GlivoFalso()

    apuntadas, problemas = apuntar(seleccionar(api, set()), glivo, simular=True)

    assert apuntadas == [1]
    assert problemas == []
    assert glivo.eventos == []

"""Pruebas del servicio HTTP: autenticación del webhook y API de consulta."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.main import crear_app
from tests.conftest import GRUPO, evento, venta


def _app(ajustes, almacen, gateway, proveedor):
    return crear_app(ajustes, almacen=almacen, gateway=gateway, proveedor=proveedor)


def _esperar(condicion, segundos: float = 5.0) -> bool:
    limite = time.time() + segundos
    while time.time() < limite:
        if condicion():
            return True
        time.sleep(0.05)
    return False


def test_el_webhook_exige_el_token(ajustes, almacen, gateway, proveedor):
    with TestClient(_app(ajustes, almacen, gateway, proveedor)) as cliente:
        assert cliente.post("/webhook/otro-token", json={}).status_code == 404
        assert cliente.post("/webhook/secreto", json=evento(texto="hola")).status_code == 200


def test_el_webhook_encola_y_el_trabajador_registra_la_venta(
    ajustes, almacen, gateway, proveedor
):
    proveedor.respuestas.append(venta())
    with TestClient(_app(ajustes, almacen, gateway, proveedor)) as cliente:
        respuesta = cliente.post("/webhook/secreto", json=evento(texto="vendida por 25€"))
        assert respuesta.status_code == 200 and respuesta.json()["ok"] is True
        assert _esperar(lambda: bool(gateway.enviados)), "el trabajador no procesó el evento"

        destino, texto = gateway.enviados[0]
        assert destino == GRUPO and "Venta registrada" in texto

        ventas = cliente.get("/ventas").json()
        assert len(ventas) == 1 and ventas[0]["plataforma"] == "Vinted"


def test_ruta_por_evento_de_evolution(ajustes, almacen, gateway, proveedor):
    proveedor.respuestas.append(venta())
    with TestClient(_app(ajustes, almacen, gateway, proveedor)) as cliente:
        assert cliente.post(
            "/webhook/secreto/messages-upsert", json=evento(texto="vendida")
        ).status_code == 200
        assert cliente.post("/webhook/secreto/chats-update", json={}).json()["ignorado"] == "chats-update"


def test_cuerpo_invalido(ajustes, almacen, gateway, proveedor):
    with TestClient(_app(ajustes, almacen, gateway, proveedor)) as cliente:
        assert cliente.post("/webhook/secreto", content=b"no soy json").status_code == 400
        assert cliente.post("/webhook/secreto", json=[1, 2]).status_code == 400


def test_salud_reporta_configuracion_y_resumen(ajustes, almacen, gateway, proveedor):
    with TestClient(_app(ajustes, almacen, gateway, proveedor)) as cliente:
        datos = cliente.get("/salud").json()
        assert datos["chats_vigilados"] == [GRUPO]
        assert datos["problemas_configuracion"] == []
        assert datos["resumen"]["total"] == 0


def test_salud_avisa_si_falta_configuracion(ajustes, almacen, gateway, proveedor):
    ajustes.grupo_ventas_jid = ""
    with TestClient(_app(ajustes, almacen, gateway, proveedor)) as cliente:
        problemas = cliente.get("/salud").json()["problemas_configuracion"]
        assert any("GRUPO_VENTAS_JID" in p for p in problemas)


def test_api_de_ventas(ajustes, almacen, gateway, proveedor):
    from app.models import RegistroVenta

    almacen.guardar(
        RegistroVenta(fecha_registro="2026-09-07T10:00:00+00:00", articulo="Botas", precio_venta=30.0)
    )
    with TestClient(_app(ajustes, almacen, gateway, proveedor)) as cliente:
        assert cliente.get("/ventas/1").json()["articulo"] == "Botas"
        assert cliente.get("/ventas/99").status_code == 404
        assert cliente.post("/ventas/1/estado", params={"estado": "enviado"}).json()["estado"] == "enviado"
        assert cliente.get("/ventas", params={"estado": "pendiente_envio"}).json() == []


def test_sin_proveedor_configurado_el_servicio_arranca_igual(ajustes, almacen, gateway):
    ajustes.anthropic_api_key = ""
    ajustes.llm_proveedor = "gemini"  # sin clave: construir_proveedor no falla, la llamada sí
    with TestClient(crear_app(ajustes, almacen=almacen, gateway=gateway)) as cliente:
        assert cliente.get("/salud").status_code == 200

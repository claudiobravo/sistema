"""Pruebas del recorrido completo con dobles: evento -> SQLite -> respuesta."""

from __future__ import annotations

import asyncio

from app.llm import ErrorLLM
from tests.conftest import GRUPO, evento, venta
from tests.utiles import PNG_1x1, pdf_de_prueba

CODIGO = "5200 1234 5678 9012 3456 7891"
CODIGO_LIMPIO = "520012345678901234567891"


def ejecutar(corrutina):
    return asyncio.run(corrutina)


# --- blindaje del grupo ----------------------------------------------------
def test_ignora_los_chats_que_no_son_el_grupo(procesador, gateway, proveedor):
    proveedor.respuestas.append(venta())
    resultado = ejecutar(procesador.procesar(evento(texto="hola", jid="34600@s.whatsapp.net")))
    assert resultado.estado == "ignorado"
    assert gateway.enviados == []
    assert proveedor.entradas == []


def test_con_el_jid_vacio_el_bot_no_escucha_nada(almacen, gateway, proveedor, tmp_path):
    """Vacío significa sordo, nunca «escucha todo».

    Es el valor por defecto del .env.example y el estado en el que se arranca
    antes de saber el JID del grupo: si aquí se colara un «si no hay filtro,
    pasa todo», el bot procesaría los chats privados del número secundario.
    """
    from app.config import Ajustes
    from app.pipeline import Procesador

    sin_grupo = Ajustes(
        _env_file=None,
        evolution_api_key="clave",
        webhook_token="secreto",
        grupo_ventas_jid="",
        anthropic_api_key="sk-test",
        db_path=str(tmp_path / "otra.db"),
    )
    assert sin_grupo.jids_permitidos == frozenset()
    procesador_sordo = Procesador(sin_grupo, almacen, gateway, proveedor)
    proveedor.respuestas.append(venta())

    resultado = ejecutar(procesador_sordo.procesar(evento(texto="Vendida por 25€")))

    assert resultado.estado == "ignorado"
    assert gateway.enviados == []
    assert proveedor.entradas == []


def test_ignora_sus_propios_mensajes(procesador, gateway):
    resultado = ejecutar(procesador.procesar(evento(texto="✅ Venta registrada", de_mi=True)))
    assert resultado.estado == "ignorado"
    assert gateway.enviados == []


def test_ignora_un_evento_que_no_es_mensaje(procesador):
    assert ejecutar(procesador.procesar({"event": "presence.update", "data": {}})).estado == "ignorado"


def test_el_reintento_del_gateway_no_duplica_la_venta(procesador, proveedor, almacen):
    proveedor.respuestas.append(venta())
    primero = ejecutar(procesador.procesar(evento(texto="Vendida la chaqueta por 25€ en Vinted")))
    segundo = ejecutar(procesador.procesar(evento(texto="Vendida la chaqueta por 25€ en Vinted")))
    assert primero.estado == "registrado"
    assert segundo.estado == "ignorado"
    assert len(almacen.listar()) == 1


# --- notas de texto --------------------------------------------------------
def test_registra_una_nota_de_texto_y_confirma_en_el_grupo(procesador, gateway, almacen):
    procesador.proveedor.respuestas.append(venta())
    resultado = ejecutar(procesador.procesar(evento(texto="Vendida la chaqueta por 25€ en Vinted")))

    assert resultado.estado == "registrado"
    assert resultado.registro.plataforma == "Vinted"
    assert resultado.registro.precio_venta == 25.0
    assert resultado.registro.origen == "texto"
    assert resultado.registro.remitente == "Claudio"
    assert almacen.listar()[0].estado == "pendiente_envio"

    destino, texto = gateway.enviados[0]
    assert destino == GRUPO
    assert "Venta registrada" in texto
    assert "Chaqueta vaquera" in texto


def test_no_inventa_codigo_en_una_nota_que_no_lo_lleva(procesador, gateway):
    procesador.proveedor.respuestas.append(venta(codigo_seguimiento="PQ1122334455667788"))
    resultado = ejecutar(procesador.procesar(evento(texto="Vendida la chaqueta por 25€")))
    assert resultado.registro.codigo_seguimiento is None
    assert any("no aparece literalmente" in a for a in resultado.registro.avisos)
    assert "no aparece literalmente" in gateway.ultimo


def test_descarta_la_venta_si_no_hay_ningun_dato_util(procesador, gateway):
    procesador.proveedor.respuestas.append(
        venta(articulo=None, precio_venta=None, codigo_seguimiento=None)
    )
    resultado = ejecutar(procesador.procesar(evento(texto="buenos días")))
    assert resultado.estado == "ilegible"
    assert "No he podido registrar" in gateway.ultimo


# --- PDFs ------------------------------------------------------------------
# Una etiqueta real trae mucho más texto que un par de líneas; estas son las que
# suele llevar una de InPost generada desde Vinted.
ETIQUETA_INPOST = [
    "InPost - Envio a Punto Pack",
    "Vinted",
    f"N de envio: {CODIGO}",
    "Destinatario: MARIA G.",
    "Punto Pack: CARREFOUR EXPRESS",
    "C/ Mayor 12, 28013 Madrid",
    "Remitente: CLAUDIO B.",
    "Peso maximo: 2 kg   Bulto 1/1",
]


def _evento_pdf(lineas, mensaje_id="PDF1"):
    return evento(
        mensaje_id=mensaje_id,
        documento={"fileName": "etiqueta.pdf", "mimetype": "application/pdf"},
        b64=pdf_de_prueba(lineas),
    )


def test_etiqueta_pdf_con_capa_de_texto_va_por_la_via_de_texto(procesador, proveedor):
    proveedor.respuestas.append(
        venta(
            tipo_documento="etiqueta_envio",
            articulo=None,
            precio_venta=None,
            transportista="InPost",
            codigo_seguimiento=CODIGO_LIMPIO,
            destinatario_o_punto_pack="MARIA G.",
        )
    )
    resultado = ejecutar(
        procesador.procesar(_evento_pdf(ETIQUETA_INPOST))
    )
    assert resultado.estado == "registrado"
    assert resultado.registro.codigo_seguimiento == CODIGO_LIMPIO
    assert resultado.registro.transportista == "InPost"
    assert resultado.registro.origen == "pdf"
    assert resultado.registro.avisos == []
    # No se ha usado visión: el texto del PDF basta.
    assert proveedor.entradas[0].imagenes == []
    assert proveedor.entradas[0].pdf is None
    assert CODIGO in proveedor.entradas[0].texto_completo


def test_codigo_alucinado_en_un_pdf_legible_se_tira(procesador, proveedor, gateway):
    proveedor.respuestas.append(
        venta(articulo=None, precio_venta=None, codigo_seguimiento="520099999999999999999999")
    )
    resultado = ejecutar(
        procesador.procesar(_evento_pdf(ETIQUETA_INPOST))
    )
    assert resultado.estado == "ilegible"  # sin código no queda ningún dato aprovechable
    assert "No he podido registrar" in gateway.ultimo


def test_pdf_escaneado_se_manda_al_modelo_como_pdf_nativo(procesador, proveedor):
    proveedor.respuestas.append(venta(tipo_documento="etiqueta_envio", codigo_seguimiento=None))
    ejecutar(procesador.procesar(_evento_pdf(["x"])))
    assert proveedor.entradas[0].pdf is not None
    assert proveedor.entradas[0].imagenes == []


def test_pdf_escaneado_se_rasteriza_si_el_proveedor_no_lee_pdfs(
    ajustes, almacen, gateway, proveedor, monkeypatch
):
    from app import media
    from app.pipeline import Procesador

    ajustes.pdf_nativo = False
    monkeypatch.setattr(media, "pdf_a_imagenes", lambda *a, **k: [PNG_1x1])
    proc = Procesador(ajustes, almacen, gateway, proveedor)
    proveedor.respuestas.append(venta(codigo_seguimiento=None))
    ejecutar(proc.procesar(_evento_pdf(["x"])))
    assert proveedor.entradas[0].imagenes == [("image/png", PNG_1x1)]


def test_si_no_se_puede_rasterizar_se_avisa_en_el_grupo(
    ajustes, almacen, gateway, proveedor, monkeypatch
):
    from app import media
    from app.pipeline import Procesador

    ajustes.pdf_nativo = False

    def explota(*a, **k):
        raise media.MediaNoLegible("poppler no está instalado")

    monkeypatch.setattr(media, "pdf_a_imagenes", explota)
    proc = Procesador(ajustes, almacen, gateway, proveedor)
    resultado = ejecutar(proc.procesar(_evento_pdf(["x"])))
    assert resultado.estado == "ilegible"
    assert "poppler" in gateway.ultimo


# --- imágenes --------------------------------------------------------------
def test_captura_de_venta_usa_vision_con_el_base64_del_webhook(procesador, proveedor):
    proveedor.respuestas.append(venta(tipo_documento="captura_venta", plataforma="Wallapop"))
    resultado = ejecutar(
        procesador.procesar(
            evento(mensaje_id="IMG1", imagen={"mimetype": "image/png"}, b64=PNG_1x1)
        )
    )
    assert resultado.registro.plataforma == "Wallapop"
    assert resultado.registro.origen == "imagen"
    assert proveedor.entradas[0].imagenes == [("image/png", PNG_1x1)]


def test_si_el_webhook_no_trae_base64_se_descarga_del_gateway(procesador, proveedor, gateway):
    gateway.media = PNG_1x1
    proveedor.respuestas.append(venta(tipo_documento="captura_venta"))
    ejecutar(procesador.procesar(evento(mensaje_id="IMG2", imagen={"mimetype": "image/png"})))
    assert proveedor.entradas[0].imagenes == [("image/png", PNG_1x1)]


def test_el_pie_de_foto_llega_al_modelo_como_contexto(procesador, proveedor):
    proveedor.respuestas.append(venta())
    ejecutar(
        procesador.procesar(
            evento(
                mensaje_id="IMG3",
                imagen={"mimetype": "image/png"},
                b64=PNG_1x1,
                texto="esta es la sudadera de 18€",
            )
        )
    )
    assert "18€" in proveedor.entradas[0].texto_completo


def test_adjunto_demasiado_grande(ajustes, almacen, gateway, proveedor):
    from app.pipeline import Procesador

    ajustes.max_media_mb = 0.000001
    proc = Procesador(ajustes, almacen, gateway, proveedor)
    resultado = ejecutar(
        proc.procesar(evento(mensaje_id="BIG", imagen={"mimetype": "image/png"}, b64=PNG_1x1))
    )
    assert resultado.estado == "ilegible"
    assert "MB" in resultado.motivo


def test_adjunto_de_tipo_no_soportado(procesador):
    resultado = ejecutar(
        procesador.procesar(
            evento(
                mensaje_id="ZIP",
                documento={"fileName": "cosas.zip", "mimetype": "application/zip"},
                b64=b"PK\x03\x04basura",
            )
        )
    )
    assert resultado.estado == "ilegible"
    assert "no soportado" in resultado.motivo


# --- errores ---------------------------------------------------------------
def test_documento_ilegible_segun_el_modelo(procesador, gateway):
    procesador.proveedor.respuestas.append(
        venta(legible=False, tipo_documento="desconocido", motivo_ilegible="es un ticket del súper")
    )
    resultado = ejecutar(procesador.procesar(evento(texto="mira")))
    assert resultado.estado == "ilegible"
    assert "ticket del súper" in gateway.ultimo


def test_fallo_del_llm_se_reporta_sin_guardar_nada(procesador, gateway, almacen):
    procesador.proveedor.respuestas.append(ErrorLLM("429 rate limit"))
    resultado = ejecutar(procesador.procesar(evento(texto="Vendida la chaqueta")))
    assert resultado.estado == "error"
    assert almacen.listar() == []
    assert "NO se ha guardado" in gateway.ultimo


def test_si_falla_la_respuesta_al_grupo_la_venta_sigue_guardada(procesador, gateway, almacen):
    gateway.fallar_envio = True
    procesador.proveedor.respuestas.append(venta())
    resultado = ejecutar(procesador.procesar(evento(texto="Vendida la chaqueta por 25€")))
    assert resultado.estado == "registrado"
    assert len(almacen.listar()) == 1


# --- comandos --------------------------------------------------------------
def test_comando_ayuda(procesador, gateway):
    resultado = ejecutar(procesador.procesar(evento(texto="/ayuda")))
    assert resultado.estado == "comando"
    assert "/pendientes" in gateway.ultimo


def test_comando_pendientes_y_enviado(procesador, gateway, proveedor):
    proveedor.respuestas.append(
        venta(codigo_seguimiento=CODIGO_LIMPIO, transportista="InPost")
    )
    ejecutar(procesador.procesar(evento(mensaje_id="V1", texto=f"vendida por 25€, envio {CODIGO}")))

    ejecutar(procesador.procesar(evento(mensaje_id="C1", texto="/pendientes")))
    assert "#1" in gateway.ultimo

    ejecutar(procesador.procesar(evento(mensaje_id="C2", texto=f"/enviado {CODIGO}")))
    assert "enviado" in gateway.ultimo

    ejecutar(procesador.procesar(evento(mensaje_id="C3", texto="/pendientes")))
    assert "No hay ventas pendientes" in gateway.ultimo


def test_comando_con_referencia_inexistente(procesador, gateway):
    ejecutar(procesador.procesar(evento(texto="/enviado #999")))
    assert "No encuentro" in gateway.ultimo


def test_comando_desconocido(procesador, gateway):
    ejecutar(procesador.procesar(evento(texto="/bailar")))
    assert "/ayuda" in gateway.ultimo


def test_resumen(procesador, gateway, proveedor):
    proveedor.respuestas.append(venta())
    ejecutar(procesador.procesar(evento(mensaje_id="V2", texto="vendida por 25€")))
    ejecutar(procesador.procesar(evento(mensaje_id="C4", texto="/resumen")))
    assert "25,00 €" in gateway.ultimo

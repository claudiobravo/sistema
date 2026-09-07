"""Orquestación: del evento del gateway a la fila en SQLite y la respuesta al grupo."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from . import formatting, media, prompts
from .config import Ajustes
from .db import Almacen
from .evolution import ClienteEvolution, ErrorGateway, decodificar_base64, parsear_mensaje
from .llm import EntradaExtraccion, ErrorLLM, ProveedorLLM
from .models import Estado, MensajeEntrante, RegistroVenta, ResultadoProceso, VentaExtraida
from .validacion import (
    normalizar_plataforma,
    normalizar_precio,
    normalizar_transportista,
    validar_codigo_seguimiento,
)

log = logging.getLogger(__name__)

_ESTADOS_COMANDO: dict[str, Estado] = {
    "enviado": "enviado",
    "entregado": "entregado",
    "cancelado": "cancelado",
}


class Procesador:
    def __init__(
        self,
        ajustes: Ajustes,
        almacen: Almacen,
        gateway: ClienteEvolution,
        proveedor: ProveedorLLM,
    ) -> None:
        self.ajustes = ajustes
        self.almacen = almacen
        self.gateway = gateway
        self.proveedor = proveedor

    # -- entrada principal --------------------------------------------------
    async def procesar(self, payload: dict) -> ResultadoProceso:
        mensaje = parsear_mensaje(payload)
        if mensaje is None:
            return ResultadoProceso(estado="ignorado", motivo="el evento no es un mensaje")

        # Blindaje: fuera del grupo de ventas el bot es sordo.
        if mensaje.chat_jid not in self.ajustes.jids_permitidos:
            log.debug("mensaje descartado, chat no autorizado: %s", mensaje.chat_jid)
            return ResultadoProceso(estado="ignorado", motivo="chat no autorizado")
        if mensaje.de_mi:
            return ResultadoProceso(estado="ignorado", motivo="mensaje propio")
        if self.almacen.mensaje_visto(mensaje.mensaje_id):
            return ResultadoProceso(estado="ignorado", motivo="mensaje ya procesado")

        # Se marca antes de trabajar: si el gateway reintenta el webhook (lo hace)
        # no queremos pagar dos veces el LLM ni duplicar la venta.
        self.almacen.marcar_mensaje(mensaje.mensaje_id, "en_proceso")

        try:
            resultado = await self._despachar(mensaje)
        except Exception as exc:  # noqa: BLE001 - la última red antes del webhook
            log.exception("fallo procesando %s", mensaje.mensaje_id)
            resultado = ResultadoProceso(estado="error", motivo=str(exc))

        self.almacen.marcar_mensaje(mensaje.mensaje_id, resultado.estado)
        await self._responder(mensaje, resultado)
        return resultado

    # -- despacho -----------------------------------------------------------
    async def _despachar(self, mensaje: MensajeEntrante) -> ResultadoProceso:
        if (
            self.ajustes.comandos_activos
            and mensaje.texto
            and mensaje.texto.lstrip().startswith("/")
        ):
            return self._ejecutar_comando(mensaje.texto.strip())

        if mensaje.tiene_media:
            return await self._procesar_adjunto(mensaje)
        if mensaje.texto:
            return await self._procesar_texto(mensaje)
        return ResultadoProceso(estado="ignorado", motivo="mensaje sin contenido aprovechable")

    async def _procesar_texto(self, mensaje: MensajeEntrante) -> ResultadoProceso:
        entrada = EntradaExtraccion(
            instruccion=prompts.INSTRUCCION_TEXTO.format(contenido=mensaje.texto)
        )
        return await self._extraer_y_guardar(
            mensaje, entrada, origen="texto", texto_fuente=mensaje.texto
        )

    async def _procesar_adjunto(self, mensaje: MensajeEntrante) -> ResultadoProceso:
        datos = await self._obtener_bytes(mensaje)
        if len(datos) > self.ajustes.max_media_bytes:
            return ResultadoProceso(
                estado="ilegible",
                motivo=f"el adjunto pesa más de {self.ajustes.max_media_mb:.0f} MB",
            )

        tipo = media.detectar_tipo(datos, mensaje.mimetype, mensaje.nombre_fichero)
        if tipo == "pdf":
            return await self._procesar_pdf(mensaje, datos)
        if tipo == "imagen":
            return await self._procesar_imagen(mensaje, datos)
        return ResultadoProceso(
            estado="ilegible",
            motivo=f"tipo de adjunto no soportado ({mensaje.mimetype or 'desconocido'})",
        )

    async def _procesar_pdf(self, mensaje: MensajeEntrante, datos: bytes) -> ResultadoProceso:
        nombre = mensaje.nombre_fichero or "etiqueta.pdf"
        texto = await asyncio.to_thread(
            media.extraer_texto_pdf, datos, self.ajustes.pdf_max_paginas
        )

        if media.texto_suficiente(texto, self.ajustes.pdf_min_caracteres):
            # Camino preferido: hay capa de texto, así que el código se puede
            # verificar carácter a carácter contra el original.
            contexto = self._con_contexto(texto, mensaje.texto)
            entrada = EntradaExtraccion(
                instruccion=prompts.INSTRUCCION_PDF.format(nombre=nombre, contenido=contexto),
                nombre_fichero=nombre,
            )
            return await self._extraer_y_guardar(
                mensaje, entrada, origen="pdf", texto_fuente=contexto
            )

        log.info("PDF %s sin capa de texto útil; tiro de visión", nombre)
        if self.ajustes.pdf_nativo and self.ajustes.llm_proveedor in ("anthropic", "gemini"):
            entrada = EntradaExtraccion(
                instruccion=self._con_instruccion(
                    prompts.INSTRUCCION_PDF_NATIVO, mensaje.texto
                ),
                pdf=datos,
                nombre_fichero=nombre,
            )
        else:
            try:
                imagenes = await asyncio.to_thread(
                    media.pdf_a_imagenes,
                    datos,
                    self.ajustes.pdf_dpi,
                    self.ajustes.pdf_max_paginas,
                )
            except media.MediaNoLegible as exc:
                return ResultadoProceso(estado="ilegible", motivo=str(exc))
            entrada = EntradaExtraccion(
                instruccion=self._con_instruccion(prompts.INSTRUCCION_IMAGEN, mensaje.texto),
                imagenes=[("image/png", img) for img in imagenes],
                nombre_fichero=nombre,
            )
        return await self._extraer_y_guardar(mensaje, entrada, origen="pdf", texto_fuente=None)

    async def _procesar_imagen(self, mensaje: MensajeEntrante, datos: bytes) -> ResultadoProceso:
        try:
            mimetype = media.mimetype_imagen(datos, mensaje.mimetype)
        except media.MediaNoLegible as exc:
            return ResultadoProceso(estado="ilegible", motivo=str(exc))
        entrada = EntradaExtraccion(
            instruccion=self._con_instruccion(prompts.INSTRUCCION_IMAGEN, mensaje.texto),
            imagenes=[(mimetype, datos)],
            nombre_fichero=mensaje.nombre_fichero,
        )
        return await self._extraer_y_guardar(mensaje, entrada, origen="imagen", texto_fuente=None)

    async def _obtener_bytes(self, mensaje: MensajeEntrante) -> bytes:
        if mensaje.base64:
            return decodificar_base64(mensaje.base64)
        return await self.gateway.descargar_media(mensaje.crudo)

    @staticmethod
    def _con_contexto(texto_documento: str, pie: str | None) -> str:
        if pie:
            return f"{texto_documento}\n\n--- COMENTARIO EN EL CHAT ---\n{pie}"
        return texto_documento

    @staticmethod
    def _con_instruccion(instruccion: str, pie: str | None) -> str:
        if pie:
            return f"{instruccion}\n\nComentario que lo acompaña en el chat: {pie}"
        return instruccion

    # -- extracción + persistencia -----------------------------------------
    async def _extraer_y_guardar(
        self,
        mensaje: MensajeEntrante,
        entrada: EntradaExtraccion,
        *,
        origen: str,
        texto_fuente: str | None,
    ) -> ResultadoProceso:
        try:
            extraido: VentaExtraida = await asyncio.to_thread(self.proveedor.extraer, entrada)
        except ErrorLLM as exc:
            return ResultadoProceso(estado="error", motivo=str(exc))

        if not extraido.legible:
            return ResultadoProceso(
                estado="ilegible", motivo=extraido.motivo_ilegible or "documento no interpretable"
            )

        registro, avisos = self._a_registro(mensaje, extraido, origen, texto_fuente)
        if self._vacio(registro):
            return ResultadoProceso(
                estado="ilegible",
                motivo="no he encontrado ni artículo, ni precio, ni código de seguimiento",
            )
        registro.avisos = avisos
        guardado, creado = await asyncio.to_thread(self.almacen.guardar, registro)
        return ResultadoProceso(
            estado="registrado" if creado else "actualizado", registro=guardado
        )

    def _a_registro(
        self,
        mensaje: MensajeEntrante,
        extraido: VentaExtraida,
        origen: str,
        texto_fuente: str | None,
    ) -> tuple[RegistroVenta, list[str]]:
        avisos: list[str] = []

        precio, avisos_precio = normalizar_precio(extraido.precio_venta)
        avisos += avisos_precio

        validacion = validar_codigo_seguimiento(
            extraido.codigo_seguimiento,
            texto_fuente=texto_fuente,
            transportista=extraido.transportista,
        )
        avisos += validacion.avisos

        plataforma = extraido.plataforma
        if plataforma == "Otro":
            plataforma = normalizar_plataforma(None, texto_fuente or mensaje.texto or "")

        registro = RegistroVenta(
            fecha_registro=mensaje.fecha_iso,
            articulo=(extraido.articulo or None),
            plataforma=plataforma,
            precio_venta=precio,
            transportista=validacion.transportista or normalizar_transportista(extraido.transportista),
            codigo_seguimiento=validacion.codigo_seguimiento,
            destinatario_o_punto_pack=(extraido.destinatario_o_punto_pack or None),
            confianza=max(0.0, min(1.0, float(extraido.confianza or 0.0))),
            origen=origen,  # type: ignore[arg-type]
            tipo_documento=extraido.tipo_documento,
            mensaje_id=mensaje.mensaje_id,
            remitente=mensaje.nombre_remitente or mensaje.remitente,
        )
        return registro, avisos

    @staticmethod
    def _vacio(registro: RegistroVenta) -> bool:
        return not any(
            (registro.articulo, registro.precio_venta, registro.codigo_seguimiento)
        )

    # -- comandos -----------------------------------------------------------
    def _ejecutar_comando(self, texto: str) -> ResultadoProceso:
        partes = texto.split(maxsplit=1)
        comando = partes[0].lstrip("/").lower()
        argumento = partes[1].strip() if len(partes) > 1 else ""

        if comando in ("ayuda", "help", "start"):
            return ResultadoProceso(estado="comando", respuesta=formatting.mensaje_ayuda())
        if comando == "pendientes":
            pendientes = self.almacen.listar(estado="pendiente_envio", limite=20)
            return ResultadoProceso(
                estado="comando", respuesta=formatting.mensaje_pendientes(pendientes)
            )
        if comando == "resumen":
            return ResultadoProceso(
                estado="comando", respuesta=formatting.mensaje_resumen(self.almacen.resumen())
            )
        if comando in _ESTADOS_COMANDO:
            if not argumento:
                return ResultadoProceso(
                    estado="comando",
                    respuesta=f"Dime cuál: `/{comando} #12` o `/{comando} <código>`.",
                )
            venta = self.almacen.buscar_por_referencia(argumento)
            if venta is None or venta.id is None:
                return ResultadoProceso(
                    estado="comando", respuesta=f"🤷 No encuentro ninguna venta con «{argumento}»."
                )
            actualizada = self.almacen.cambiar_estado(venta.id, _ESTADOS_COMANDO[comando])
            return ResultadoProceso(
                estado="comando",
                registro=actualizada,
                respuesta=formatting.mensaje_estado(actualizada) if actualizada else None,
            )
        return ResultadoProceso(
            estado="comando", respuesta=f"No conozco `/{comando}`. Prueba con `/ayuda`."
        )

    # -- salida -------------------------------------------------------------
    async def _responder(self, mensaje: MensajeEntrante, resultado: ResultadoProceso) -> None:
        texto = self._texto_respuesta(resultado)
        if not texto or not self.ajustes.responder_en_grupo:
            return
        citando = self._cita(mensaje)
        try:
            await self.gateway.enviar_texto(mensaje.chat_jid, texto, citando=citando)
        except ErrorGateway as exc:
            log.error("no he podido responder en el grupo: %s", exc)

    def _texto_respuesta(self, resultado: ResultadoProceso) -> Optional[str]:
        if resultado.respuesta:
            return resultado.respuesta
        if resultado.estado in ("registrado", "actualizado") and resultado.registro:
            return formatting.mensaje_confirmacion(
                resultado.registro,
                creado=resultado.estado == "registrado",
                zona=self.ajustes.zona_horaria,
            )
        if not self.ajustes.responder_errores:
            return None
        if resultado.estado == "ilegible":
            return formatting.mensaje_ilegible(resultado.motivo)
        if resultado.estado == "error":
            return formatting.mensaje_error(resultado.motivo or "fallo desconocido")
        return None

    @staticmethod
    def _cita(mensaje: MensajeEntrante) -> dict | None:
        clave = mensaje.crudo.get("key")
        contenido = mensaje.crudo.get("message")
        if isinstance(clave, dict) and isinstance(contenido, dict):
            return {"key": clave, "message": contenido}
        return None

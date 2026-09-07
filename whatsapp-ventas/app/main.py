"""Microservicio FastAPI que escucha el webhook de Evolution API.

El webhook contesta enseguida y encola: el gateway reintenta si tarda, y no
queremos que el LLM (varios segundos) bloquee la entrega de eventos.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import APIRouter, FastAPI, HTTPException, Request, Response

from .config import Ajustes, obtener_ajustes
from .db import Almacen
from .evolution import ClienteEvolution
from .llm import EntradaExtraccion, ErrorLLM, ProveedorLLM, construir_proveedor
from .models import Estado, RegistroVenta
from .pipeline import Procesador

log = logging.getLogger(__name__)
VERSION = "1.0.0"


class ProveedorRoto:
    """Sustituto cuando el proveedor no se pudo construir (falta la API key…).

    Así el servicio arranca, `/salud` explica el problema y los mensajes se
    responden con un error claro en vez de morir en el arranque.
    """

    nombre = "roto"

    def __init__(self, motivo: str) -> None:
        self.motivo = motivo

    def extraer(self, entrada: EntradaExtraccion):  # noqa: ARG002
        raise ErrorLLM(f"el extractor no está configurado: {self.motivo}")


def crear_app(
    ajustes: Optional[Ajustes] = None,
    *,
    almacen: Optional[Almacen] = None,
    gateway: Optional[ClienteEvolution] = None,
    proveedor: Optional[ProveedorLLM] = None,
) -> FastAPI:
    ajustes = ajustes or obtener_ajustes()
    logging.basicConfig(
        level=getattr(logging, ajustes.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    almacen = almacen or Almacen(ajustes.db_path)
    almacen.inicializar()

    gateway = gateway or ClienteEvolution(
        ajustes.evolution_base_url, ajustes.evolution_api_key, ajustes.evolution_instancia
    )

    if proveedor is None:
        try:
            proveedor = construir_proveedor(ajustes)
        except Exception as exc:  # noqa: BLE001
            log.error("no he podido construir el proveedor LLM: %s", exc)
            proveedor = ProveedorRoto(str(exc))

    procesador = Procesador(ajustes, almacen, gateway, proveedor)
    cola: asyncio.Queue[dict] = asyncio.Queue(maxsize=ajustes.cola_max)

    @asynccontextmanager
    async def ciclo_vida(app: FastAPI):
        for problema in ajustes.problemas():
            log.warning("configuración incompleta: %s", problema)
        trabajador = asyncio.create_task(_trabajador(cola, procesador), name="procesador")
        log.info(
            "bot de ventas listo (proveedor=%s, chats vigilados=%d)",
            getattr(proveedor, "nombre", "?"),
            len(ajustes.jids_permitidos),
        )
        try:
            yield
        finally:
            trabajador.cancel()
            try:
                await trabajador
            except asyncio.CancelledError:
                pass
            await gateway.cerrar()

    app = FastAPI(title="Bot de ventas Vinted/Wallapop", version=VERSION, lifespan=ciclo_vida)
    app.state.ajustes = ajustes
    app.state.almacen = almacen
    app.state.gateway = gateway
    app.state.procesador = procesador
    app.state.cola = cola
    app.include_router(_router(ajustes, almacen, cola, proveedor))
    return app


async def _trabajador(cola: asyncio.Queue, procesador: Procesador) -> None:
    while True:
        payload = await cola.get()
        try:
            resultado = await procesador.procesar(payload)
            if resultado.estado not in ("ignorado",):
                log.info("evento procesado: %s (%s)", resultado.estado, resultado.motivo or "")
        except Exception:  # noqa: BLE001 - el trabajador no se puede morir
            log.exception("error no controlado procesando un evento")
        finally:
            cola.task_done()


def _router(
    ajustes: Ajustes, almacen: Almacen, cola: asyncio.Queue, proveedor: ProveedorLLM
) -> APIRouter:
    router = APIRouter()

    def _comprobar_token(token: str) -> None:
        if not ajustes.webhook_token or not secrets.compare_digest(token, ajustes.webhook_token):
            raise HTTPException(status_code=404, detail="not found")

    async def _encolar(request: Request) -> dict[str, Any]:
        try:
            payload = await request.json()
        except Exception:  # noqa: BLE001
            raise HTTPException(status_code=400, detail="cuerpo no es JSON") from None
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="se esperaba un objeto JSON")
        try:
            cola.put_nowait(payload)
        except asyncio.QueueFull:
            log.error("cola llena (%d): descarto el evento", ajustes.cola_max)
            raise HTTPException(status_code=503, detail="cola llena") from None
        return {"ok": True, "encolados": cola.qsize()}

    @router.post("/webhook/{token}")
    async def webhook(token: str, request: Request) -> dict[str, Any]:
        _comprobar_token(token)
        return await _encolar(request)

    # Con WEBHOOK_BY_EVENTS=true, Evolution añade el evento a la ruta
    # (…/webhook/<token>/messages-upsert).
    @router.post("/webhook/{token}/{evento}")
    async def webhook_por_evento(token: str, evento: str, request: Request) -> dict[str, Any]:
        _comprobar_token(token)
        if evento.replace("_", "-").lower() not in ("messages-upsert", "send-message"):
            return {"ok": True, "ignorado": evento}
        return await _encolar(request)

    @router.get("/salud")
    async def salud() -> dict[str, Any]:
        return {
            "version": VERSION,
            "proveedor": getattr(proveedor, "nombre", "?"),
            "chats_vigilados": sorted(ajustes.jids_permitidos),
            "cola": cola.qsize(),
            "problemas_configuracion": ajustes.problemas(),
            "resumen": almacen.resumen(),
        }

    @router.get("/ventas")
    async def listar_ventas(
        estado: Estado | None = None, limite: int = 50, desplazamiento: int = 0
    ) -> list[RegistroVenta]:
        return almacen.listar(
            estado=estado, limite=min(limite, 200), desplazamiento=max(desplazamiento, 0)
        )

    @router.get("/ventas/{venta_id}")
    async def obtener_venta(venta_id: int) -> RegistroVenta:
        venta = almacen.obtener(venta_id)
        if venta is None:
            raise HTTPException(status_code=404, detail="venta no encontrada")
        return venta

    @router.post("/ventas/{venta_id}/estado")
    async def cambiar_estado(venta_id: int, estado: Estado) -> RegistroVenta:
        venta = almacen.cambiar_estado(venta_id, estado)
        if venta is None:
            raise HTTPException(status_code=404, detail="venta no encontrada")
        return venta

    @router.get("/", include_in_schema=False)
    async def raiz() -> Response:
        return Response(status_code=204)

    return router


app_singleton: FastAPI | None = None


def obtener_app() -> FastAPI:
    """Punto de entrada de uvicorn: `uvicorn app.main:obtener_app --factory`."""
    global app_singleton
    if app_singleton is None:
        app_singleton = crear_app()
    return app_singleton

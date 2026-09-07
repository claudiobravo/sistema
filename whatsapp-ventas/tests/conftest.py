"""Dobles de prueba: ni WhatsApp ni LLM reales."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any

import pytest

from app.config import Ajustes
from app.db import Almacen
from app.llm import EntradaExtraccion, ErrorLLM
from app.models import VentaExtraida
from app.pipeline import Procesador

GRUPO = "120363000000000000@g.us"


@dataclass
class GatewayFalso:
    enviados: list[tuple[str, str]] = field(default_factory=list)
    media: bytes | None = None
    fallar_envio: bool = False

    async def enviar_texto(self, jid: str, texto: str, *, citando: dict | None = None) -> dict:
        if self.fallar_envio:
            from app.evolution import ErrorGateway

            raise ErrorGateway("gateway caído")
        self.enviados.append((jid, texto))
        return {"key": {"id": "SENT"}}

    async def descargar_media(self, datos_mensaje: dict) -> bytes:
        if self.media is None:
            from app.evolution import ErrorGateway

            raise ErrorGateway("sin media")
        return self.media

    async def cerrar(self) -> None:
        return None

    @property
    def ultimo(self) -> str:
        return self.enviados[-1][1] if self.enviados else ""


@dataclass
class ProveedorFalso:
    nombre: str = "falso"
    respuestas: list[Any] = field(default_factory=list)
    entradas: list[EntradaExtraccion] = field(default_factory=list)

    def extraer(self, entrada: EntradaExtraccion) -> VentaExtraida:
        self.entradas.append(entrada)
        if not self.respuestas:
            raise ErrorLLM("sin respuestas preparadas")
        siguiente = self.respuestas.pop(0)
        if isinstance(siguiente, Exception):
            raise siguiente
        return siguiente


def venta(**cambios: Any) -> VentaExtraida:
    base = {
        "legible": True,
        "tipo_documento": "nota_texto",
        "articulo": "Chaqueta vaquera Levi's talla S",
        "plataforma": "Vinted",
        "precio_venta": 25.0,
        "transportista": None,
        "codigo_seguimiento": None,
        "destinatario_o_punto_pack": None,
        "confianza": 0.9,
        "motivo_ilegible": None,
    }
    base.update(cambios)
    return VentaExtraida(**base)


def evento(
    *,
    texto: str | None = None,
    jid: str = GRUPO,
    mensaje_id: str = "MSG1",
    de_mi: bool = False,
    documento: dict | None = None,
    imagen: dict | None = None,
    b64: bytes | None = None,
) -> dict:
    mensaje: dict[str, Any] = {}
    if documento is not None:
        mensaje["documentMessage"] = documento
    if imagen is not None:
        mensaje["imageMessage"] = imagen
    if texto is not None and not mensaje:
        mensaje["conversation"] = texto
    elif texto is not None:
        objetivo = "documentMessage" if documento is not None else "imageMessage"
        mensaje[objetivo]["caption"] = texto
    if b64 is not None:
        mensaje["base64"] = base64.b64encode(b64).decode("ascii")
    return {
        "event": "messages.upsert",
        "instance": "ventas",
        "data": {
            "key": {"remoteJid": jid, "fromMe": de_mi, "id": mensaje_id, "participant": "34600@s.whatsapp.net"},
            "pushName": "Claudio",
            "message": mensaje,
            "messageType": "conversation",
            "messageTimestamp": 1757260000,
        },
    }


@pytest.fixture
def ajustes(tmp_path) -> Ajustes:
    return Ajustes(
        _env_file=None,
        evolution_api_key="clave",
        webhook_token="secreto",
        grupo_ventas_jid=GRUPO,
        anthropic_api_key="sk-test",
        db_path=str(tmp_path / "ventas.db"),
        zona_horaria="Europe/Madrid",
    )


@pytest.fixture
def almacen(ajustes) -> Almacen:
    almacen = Almacen(ajustes.db_path)
    almacen.inicializar()
    return almacen


@pytest.fixture
def gateway() -> GatewayFalso:
    return GatewayFalso()


@pytest.fixture
def proveedor() -> ProveedorFalso:
    return ProveedorFalso()


@pytest.fixture
def procesador(ajustes, almacen, gateway, proveedor) -> Procesador:
    return Procesador(ajustes, almacen, gateway, proveedor)  # type: ignore[arg-type]

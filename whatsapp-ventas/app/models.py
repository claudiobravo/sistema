"""Contratos de datos: lo que devuelve el LLM y lo que se guarda en SQLite."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

Plataforma = Literal["Vinted", "Wallapop", "Otro"]
TipoDocumento = Literal["etiqueta_envio", "captura_venta", "nota_texto", "desconocido"]
Estado = Literal["pendiente_envio", "enviado", "entregado", "cancelado"]
Origen = Literal["texto", "imagen", "pdf"]


class VentaExtraida(BaseModel):
    """JSON estricto que el LLM debe devolver. Todos los campos son obligatorios;
    lo que no aparezca en el documento va como `null`, nunca inventado.

    `fecha_registro` NO se le pide al modelo a propósito: la pone el backend a
    partir del timestamp del mensaje de WhatsApp, que es un dato fiable.
    """

    legible: bool = Field(description="False si el documento no se puede leer o no es una venta")
    tipo_documento: TipoDocumento
    articulo: Optional[str]
    plataforma: Plataforma
    precio_venta: Optional[float]
    transportista: Optional[str]
    codigo_seguimiento: Optional[str]
    destinatario_o_punto_pack: Optional[str]
    confianza: float = Field(description="0.0 a 1.0: seguridad global de la extracción")
    motivo_ilegible: Optional[str] = Field(
        description="Si legible=false, una frase corta explicando por qué"
    )


class RegistroVenta(BaseModel):
    """Fila de `ventas` tal y como se persiste y se devuelve al chat."""

    id: Optional[int] = None
    fecha_registro: str
    articulo: Optional[str] = None
    plataforma: Plataforma = "Otro"
    precio_venta: Optional[float] = None
    transportista: Optional[str] = None
    codigo_seguimiento: Optional[str] = None
    destinatario_o_punto_pack: Optional[str] = None
    estado: Estado = "pendiente_envio"
    confianza: float = 0.0
    origen: Origen = "texto"
    tipo_documento: TipoDocumento = "desconocido"
    mensaje_id: Optional[str] = None
    remitente: Optional[str] = None
    avisos: list[str] = Field(default_factory=list)

    @staticmethod
    def ahora_iso() -> str:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class MensajeEntrante(BaseModel):
    """Un mensaje del grupo, ya normalizado desde el payload de Evolution API."""

    mensaje_id: str
    chat_jid: str
    de_mi: bool
    remitente: Optional[str] = None
    nombre_remitente: Optional[str] = None
    timestamp: Optional[int] = None
    texto: Optional[str] = None
    tiene_media: bool = False
    mimetype: Optional[str] = None
    nombre_fichero: Optional[str] = None
    base64: Optional[str] = None
    crudo: dict = Field(default_factory=dict, repr=False)

    @property
    def fecha_iso(self) -> str:
        if self.timestamp:
            return (
                datetime.fromtimestamp(self.timestamp, tz=timezone.utc)
                .replace(microsecond=0)
                .isoformat()
            )
        return RegistroVenta.ahora_iso()


class ResultadoProceso(BaseModel):
    """Lo que devuelve el pipeline; útil para tests y para el endpoint de depuración."""

    estado: Literal["registrado", "actualizado", "ignorado", "ilegible", "error", "comando"]
    motivo: Optional[str] = None
    registro: Optional[RegistroVenta] = None
    respuesta: Optional[str] = None

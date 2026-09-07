"""Mensajes que el bot escribe en el grupo."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import RegistroVenta

_ETIQUETAS_ESTADO = {
    "pendiente_envio": "⏳ pendiente de envío",
    "enviado": "📮 enviado",
    "entregado": "✅ entregado",
    "cancelado": "❌ cancelado",
}


def formatear_precio(valor: float | None) -> str:
    if valor is None:
        return "—"
    return f"{valor:,.2f} €".replace(",", "@").replace(".", ",").replace("@", ".")


def formatear_fecha(iso: str, zona: str = "Europe/Madrid") -> str:
    try:
        momento = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    try:
        momento = momento.astimezone(ZoneInfo(zona))
    except (ZoneInfoNotFoundError, ValueError):
        pass
    return momento.strftime("%d/%m/%Y %H:%M")


def _campo(valor: str | None, maximo: int = 90) -> str:
    if not valor:
        return "—"
    limpio = " ".join(str(valor).split())
    return limpio if len(limpio) <= maximo else limpio[: maximo - 1] + "…"


def mensaje_confirmacion(
    registro: RegistroVenta, *, creado: bool = True, zona: str = "Europe/Madrid"
) -> str:
    cabecera = (
        f"✅ *Venta registrada* #{registro.id}"
        if creado
        else f"🔄 *Venta actualizada* #{registro.id}"
    )
    lineas = [
        cabecera,
        f"🛍️ Artículo: {_campo(registro.articulo)}",
        f"🏷️ Plataforma: {registro.plataforma}",
        f"💶 Precio: {formatear_precio(registro.precio_venta)}",
        f"📦 Transportista: {_campo(registro.transportista)}",
        f"🔖 Seguimiento: {_campo(registro.codigo_seguimiento, 60)}",
        f"📍 Destino: {_campo(registro.destinatario_o_punto_pack)}",
        f"📌 Estado: {_ETIQUETAS_ESTADO.get(registro.estado, registro.estado)}",
        f"🕐 {formatear_fecha(registro.fecha_registro, zona)}",
    ]
    if registro.confianza < 0.6:
        lineas.append(f"🤔 Confianza baja ({registro.confianza:.0%}): revísalo.")
    for aviso in registro.avisos:
        lineas.append(f"⚠️ {aviso}")
    return "\n".join(lineas)


def mensaje_ilegible(motivo: str | None) -> str:
    return (
        "⚠️ *No he podido registrar esto*\n"
        f"Motivo: {motivo or 'el documento no se puede leer'}.\n"
        "Reenvía el PDF original o una captura más nítida, o escríbeme los datos "
        "a mano (artículo, plataforma, precio, transportista y código)."
    )


def mensaje_error(detalle: str) -> str:
    return (
        "🚨 *Error procesando el mensaje*\n"
        f"{_campo(detalle, 200)}\n"
        "La venta NO se ha guardado. Vuelve a enviarlo en un rato."
    )


def mensaje_pendientes(registros: list[RegistroVenta], zona: str = "Europe/Madrid") -> str:
    if not registros:
        return "📭 No hay ventas pendientes de envío."
    lineas = [f"📋 *Pendientes de envío* ({len(registros)})"]
    for r in registros:
        lineas.append(
            f"• #{r.id} · {_campo(r.articulo, 40)} · {formatear_precio(r.precio_venta)}"
            f" · {_campo(r.transportista, 20)} · {_campo(r.codigo_seguimiento, 30)}"
        )
    return "\n".join(lineas)


def mensaje_resumen(resumen: dict) -> str:
    return (
        "📊 *Resumen*\n"
        f"• Ventas registradas: {resumen['total']}\n"
        f"• Pendientes de envío: {resumen['pendientes']}\n"
        f"• Ingresos acumulados: {formatear_precio(resumen['ingresos'])}"
    )


def mensaje_estado(registro: RegistroVenta) -> str:
    return (
        f"📌 Venta #{registro.id} marcada como "
        f"*{_ETIQUETAS_ESTADO.get(registro.estado, registro.estado)}*."
    )


def mensaje_ayuda() -> str:
    return (
        "🤖 *Bot de ventas*\n"
        "Mándame al grupo la etiqueta en PDF, la captura de la venta o una nota "
        "de texto y la registro sola.\n\n"
        "Comandos:\n"
        "• `/pendientes` — ventas sin enviar\n"
        "• `/enviado <#id o código>` — marcar como enviada\n"
        "• `/entregado <#id o código>` — marcar como entregada\n"
        "• `/resumen` — totales\n"
        "• `/ayuda` — esto"
    )

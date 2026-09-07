#!/usr/bin/env python3
"""Utilidad de línea de comandos para dar de alta y blindar el bot.

    python -m tools.gestion crear      # crea la instancia y saca el QR
    python -m tools.gestion qr         # vuelve a pedir el QR
    python -m tools.gestion estado     # ¿está vinculado el número?
    python -m tools.gestion grupos     # lista los grupos -> de aquí sale el group_jid
    python -m tools.gestion webhook    # apunta el gateway a este backend
    python -m tools.gestion probar     # manda un mensaje de prueba al grupo

Se ejecuta desde el host (o con `docker compose exec bot ...`) y lee el .env.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import obtener_ajustes  # noqa: E402


def _cliente(ajustes) -> httpx.Client:
    return httpx.Client(
        base_url=ajustes.evolution_base_url,
        headers={"apikey": ajustes.evolution_api_key, "Content-Type": "application/json"},
        timeout=60.0,
    )


def _mostrar(respuesta: httpx.Response) -> Any:
    try:
        datos = respuesta.json()
    except ValueError:
        datos = respuesta.text
    print(json.dumps(datos, indent=2, ensure_ascii=False)[:4000])
    return datos


def _guardar_qr(datos: dict) -> None:
    """Vuelca el QR a fichero y, si se puede, lo pinta en el terminal."""
    bloque = datos.get("qrcode") or datos
    codigo = bloque.get("code") or bloque.get("pairingCode")
    base64_png = bloque.get("base64") or ""

    if base64_png:
        crudo = base64_png.split(",", 1)[-1]
        destino = Path("qr.png")
        destino.write_bytes(base64.b64decode(crudo))
        print(f"\n📷 QR guardado en {destino.resolve()} — ábrelo y escanéalo.")

    if codigo:
        try:
            import qrcode  # type: ignore

            qr = qrcode.QRCode()
            qr.add_data(codigo)
            qr.print_ascii(invert=True)
        except ImportError:
            print(f"\n(instala `qrcode` para verlo aquí mismo)\ncódigo: {codigo}")

    print(
        "\nEn el MÓVIL DE LA SIM SECUNDARIA: WhatsApp → Ajustes → Dispositivos "
        "vinculados → Vincular un dispositivo → escanea el QR.\n"
        "El QR caduca en ~40 s: si se pasa, vuelve a lanzar `qr`."
    )


def cmd_crear(ajustes, args) -> None:
    with _cliente(ajustes) as cliente:
        cuerpo = {
            "instanceName": ajustes.evolution_instancia,
            "qrcode": True,
            "integration": "WHATSAPP-BAILEYS",
            "groupsIgnore": False,
            "alwaysOnline": False,
            "readMessages": False,
            "readStatus": False,
        }
        respuesta = cliente.post("/instance/create", json=cuerpo)
        if respuesta.status_code == 403 or "already in use" in respuesta.text:
            print("La instancia ya existe; pido el QR directamente.")
            return cmd_qr(ajustes, args)
        datos = _mostrar(respuesta)
        if isinstance(datos, dict):
            _guardar_qr(datos)


def cmd_qr(ajustes, args) -> None:
    with _cliente(ajustes) as cliente:
        datos = _mostrar(cliente.get(f"/instance/connect/{ajustes.evolution_instancia}"))
        if isinstance(datos, dict):
            _guardar_qr(datos)


def cmd_estado(ajustes, args) -> None:
    with _cliente(ajustes) as cliente:
        datos = _mostrar(cliente.get(f"/instance/connectionState/{ajustes.evolution_instancia}"))
    estado = ""
    if isinstance(datos, dict):
        estado = (datos.get("instance") or {}).get("state") or datos.get("state") or ""
    print("\n✅ Número vinculado." if estado == "open" else f"\n⏳ Estado: {estado or 'desconocido'}")


def cmd_grupos(ajustes, args) -> None:
    with _cliente(ajustes) as cliente:
        respuesta = cliente.get(
            f"/group/fetchAllGroups/{ajustes.evolution_instancia}",
            params={"getParticipants": "false"},
        )
    if respuesta.status_code >= 400:
        print(f"Error {respuesta.status_code}: {respuesta.text[:400]}")
        sys.exit(1)
    datos = respuesta.json()
    grupos = datos if isinstance(datos, list) else datos.get("groups", [])
    if not grupos:
        print("No hay grupos. ¿Está el número dentro del grupo de ventas?")
        return
    print(f"{'GROUP_JID':<32}  NOMBRE")
    for grupo in grupos:
        jid = grupo.get("id", "")
        nombre = grupo.get("subject", "")
        marca = "  ← configurado" if jid == ajustes.grupo_ventas_jid else ""
        print(f"{jid:<32}  {nombre}{marca}")
    print("\nCopia el JID que acaba en @g.us en GRUPO_VENTAS_JID del .env y reinicia el bot.")


def cmd_webhook(ajustes, args) -> None:
    url = args.url or f"{args.base}/webhook/{ajustes.webhook_token}"
    eventos = ["MESSAGES_UPSERT"]
    moderno = {
        "webhook": {
            "enabled": True,
            "url": url,
            "byEvents": False,
            "base64": True,
            "events": eventos,
        }
    }
    antiguo = {
        "enabled": True,
        "url": url,
        "webhook_by_events": False,
        "webhook_base64": True,
        "events": eventos,
    }
    ruta = f"/webhook/set/{ajustes.evolution_instancia}"
    with _cliente(ajustes) as cliente:
        respuesta = cliente.post(ruta, json=moderno)
        if respuesta.status_code >= 400:
            print(f"Formato moderno rechazado ({respuesta.status_code}); pruebo el antiguo.")
            respuesta = cliente.post(ruta, json=antiguo)
        _mostrar(respuesta)
    print(f"\nWebhook apuntando a: {url}")


def cmd_probar(ajustes, args) -> None:
    if not ajustes.grupo_ventas_jid:
        print("Falta GRUPO_VENTAS_JID en el .env")
        sys.exit(1)
    texto = args.texto or "🤖 Bot de ventas conectado. Mándame etiquetas, capturas o notas."
    with _cliente(ajustes) as cliente:
        respuesta = cliente.post(
            f"/message/sendText/{ajustes.evolution_instancia}",
            json={"number": ajustes.grupo_ventas_jid, "text": texto},
        )
        if respuesta.status_code >= 400:
            respuesta = cliente.post(
                f"/message/sendText/{ajustes.evolution_instancia}",
                json={
                    "number": ajustes.grupo_ventas_jid,
                    "options": {"delay": 0},
                    "textMessage": {"text": texto},
                },
            )
        _mostrar(respuesta)


def main() -> None:
    parser = argparse.ArgumentParser(description="Gestión del gateway de WhatsApp")
    sub = parser.add_subparsers(dest="comando", required=True)
    sub.add_parser("crear", help="crea la instancia y muestra el QR")
    sub.add_parser("qr", help="pide un QR nuevo")
    sub.add_parser("estado", help="estado de la vinculación")
    sub.add_parser("grupos", help="lista los grupos con su JID")
    p_webhook = sub.add_parser("webhook", help="configura el webhook de la instancia")
    p_webhook.add_argument("--base", default="http://bot:8000", help="URL base del backend")
    p_webhook.add_argument("--url", default=None, help="URL completa del webhook")
    p_probar = sub.add_parser("probar", help="envía un mensaje de prueba al grupo")
    p_probar.add_argument("--texto", default=None)

    args = parser.parse_args()
    ajustes = obtener_ajustes()
    acciones = {
        "crear": cmd_crear,
        "qr": cmd_qr,
        "estado": cmd_estado,
        "grupos": cmd_grupos,
        "webhook": cmd_webhook,
        "probar": cmd_probar,
    }
    acciones[args.comando](ajustes, args)


if __name__ == "__main__":
    main()

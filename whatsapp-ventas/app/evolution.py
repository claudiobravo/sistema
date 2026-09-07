"""Cliente del gateway de WhatsApp (Evolution API) y traducción de sus payloads.

Evolution ha cambiado de forma entre la v2.0 y la v2.1 (cuerpos planos vs.
`textMessage`/`options`). Aquí se intenta primero el formato moderno y, si el
gateway lo rechaza, se reintenta con el antiguo: así el mismo backend sirve
para las dos ramas sin tocar código.
"""

from __future__ import annotations

import base64
import binascii
import logging
from typing import Any, Optional

import httpx

from .models import MensajeEntrante

log = logging.getLogger(__name__)

# Envoltorios que WhatsApp añade y que esconden el mensaje real.
_ENVOLTORIOS = (
    "ephemeralMessage",
    "viewOnceMessage",
    "viewOnceMessageV2",
    "viewOnceMessageV2Extension",
    "documentWithCaptionMessage",
    "editedMessage",
)


class ErrorGateway(Exception):
    """El gateway ha respondido mal o no responde."""


class ClienteEvolution:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        instancia: str,
        *,
        timeout: float = 30.0,
        cliente: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.instancia = instancia
        self._propio = cliente is None
        self._cliente = cliente or httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            headers={"apikey": api_key, "Content-Type": "application/json"},
        )

    async def cerrar(self) -> None:
        if self._propio:
            await self._cliente.aclose()

    async def _peticion(
        self, metodo: str, ruta: str, *, json: Any = None, params: dict | None = None
    ) -> httpx.Response:
        try:
            return await self._cliente.request(metodo, ruta, json=json, params=params)
        except httpx.HTTPError as exc:
            raise ErrorGateway(f"no he podido hablar con el gateway: {exc}") from exc

    # --- salida ------------------------------------------------------------
    async def enviar_texto(
        self, jid: str, texto: str, *, citando: dict | None = None
    ) -> dict:
        """Envía un mensaje al chat. `citando` es la `key`+`message` del original."""
        ruta = f"/message/sendText/{self.instancia}"
        moderno: dict[str, Any] = {"number": jid, "text": texto, "delay": 0}
        if citando:
            moderno["quoted"] = citando

        respuesta = await self._peticion("POST", ruta, json=moderno)
        if respuesta.status_code < 400:
            return _json_seguro(respuesta)

        if respuesta.status_code in (400, 404, 422):
            log.info("sendText moderno rechazado (%s); pruebo el formato v2.0", respuesta.status_code)
            antiguo: dict[str, Any] = {
                "number": jid,
                "options": {"delay": 0, "presence": "composing"},
                "textMessage": {"text": texto},
            }
            if citando:
                antiguo["options"]["quoted"] = citando
            respuesta = await self._peticion("POST", ruta, json=antiguo)
            if respuesta.status_code < 400:
                return _json_seguro(respuesta)

        raise ErrorGateway(
            f"el gateway rechazó el envío ({respuesta.status_code}): {respuesta.text[:300]}"
        )

    # --- entrada -----------------------------------------------------------
    async def descargar_media(self, datos_mensaje: dict) -> bytes:
        """Pide al gateway el binario de un adjunto en base64."""
        ruta = f"/chat/getBase64FromMediaMessage/{self.instancia}"
        cuerpos = [
            {
                "message": {
                    "key": datos_mensaje.get("key", {}),
                    "message": datos_mensaje.get("message", {}),
                },
                "convertToMp4": False,
            },
            {"message": {"key": datos_mensaje.get("key", {})}, "convertToMp4": False},
        ]
        ultimo = ""
        for cuerpo in cuerpos:
            respuesta = await self._peticion("POST", ruta, json=cuerpo)
            if respuesta.status_code < 400:
                datos = _json_seguro(respuesta)
                b64 = datos.get("base64") or datos.get("media") or ""
                if b64:
                    return decodificar_base64(b64)
                ultimo = "el gateway devolvió una respuesta sin base64"
                continue
            ultimo = f"{respuesta.status_code}: {respuesta.text[:200]}"
        raise ErrorGateway(f"no he podido descargar el adjunto ({ultimo})")

    # --- administración ----------------------------------------------------
    async def listar_grupos(self) -> list[dict]:
        respuesta = await self._peticion(
            "GET",
            f"/group/fetchAllGroups/{self.instancia}",
            params={"getParticipants": "false"},
        )
        if respuesta.status_code >= 400:
            raise ErrorGateway(
                f"no he podido listar los grupos ({respuesta.status_code}): {respuesta.text[:200]}"
            )
        datos = _json_seguro(respuesta)
        grupos = datos if isinstance(datos, list) else datos.get("groups", [])
        return [g for g in grupos if isinstance(g, dict)]

    async def estado_conexion(self) -> dict:
        respuesta = await self._peticion("GET", f"/instance/connectionState/{self.instancia}")
        return _json_seguro(respuesta)


def _json_seguro(respuesta: httpx.Response) -> Any:
    try:
        return respuesta.json()
    except ValueError:
        return {}


def decodificar_base64(valor: str) -> bytes:
    if "," in valor[:64] and valor.lstrip().startswith("data:"):
        valor = valor.split(",", 1)[1]
    try:
        return base64.b64decode(valor, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise ErrorGateway(f"base64 corrupto: {exc}") from exc


def _capas(mensaje: dict) -> list[dict]:
    """Devuelve el sobre y cada capa que envuelve al mensaje, de fuera hacia dentro.

    Hace falta la lista entera, no solo el interior: Evolution engancha el
    base64 del adjunto en el nivel donde venía el `message` del webhook, que
    es el de FUERA. Si nos quedamos solo con el contenido desenvuelto (el caso
    de una etiqueta PDF con pie de foto, `documentWithCaptionMessage`) el
    base64 se queda atrás y hay que volver a pedir el fichero al gateway.
    """
    capas = [mensaje]
    for _ in range(5):
        for envoltorio in _ENVOLTORIOS:
            interior = capas[-1].get(envoltorio)
            if isinstance(interior, dict) and isinstance(interior.get("message"), dict):
                capas.append(interior["message"])
                break
        else:
            break
    return capas


def _desenvolver(mensaje: dict) -> dict:
    """Quita las capas de mensajes efímeros / de una sola vez / con pie de foto."""
    return _capas(mensaje)[-1]


def parsear_mensaje(payload: dict) -> Optional[MensajeEntrante]:
    """Convierte un evento `messages.upsert` de Evolution en algo manejable.

    Devuelve None si el evento no es un mensaje de chat (recibos, presencias,
    actualizaciones de estado…).
    """
    evento = str(payload.get("event", "")).lower().replace("_", ".")
    if evento and evento not in ("messages.upsert", "send.message"):
        return None

    datos = payload.get("data")
    if isinstance(datos, list):
        datos = datos[0] if datos else None
    if not isinstance(datos, dict):
        return None

    clave = datos.get("key") or {}
    chat_jid = clave.get("remoteJid") or ""
    mensaje_id = clave.get("id") or ""
    if not chat_jid or not mensaje_id:
        return None

    capas = _capas(datos.get("message") or {})
    contenido = capas[-1]

    texto = (
        contenido.get("conversation")
        or (contenido.get("extendedTextMessage") or {}).get("text")
        or (contenido.get("imageMessage") or {}).get("caption")
        or (contenido.get("documentMessage") or {}).get("caption")
        or None
    )

    imagen = contenido.get("imageMessage") or {}
    documento = contenido.get("documentMessage") or {}
    adjunto = imagen or documento

    b64 = _extraer_base64(datos, capas, adjunto)

    return MensajeEntrante(
        mensaje_id=mensaje_id,
        chat_jid=chat_jid,
        de_mi=bool(clave.get("fromMe")),
        remitente=clave.get("participant") or datos.get("sender"),
        nombre_remitente=datos.get("pushName"),
        timestamp=_entero(datos.get("messageTimestamp")),
        texto=texto.strip() if isinstance(texto, str) else None,
        tiene_media=bool(adjunto),
        mimetype=adjunto.get("mimetype"),
        nombre_fichero=documento.get("fileName") or imagen.get("fileName"),
        base64=b64,
        crudo=datos,
    )


def _extraer_base64(datos: dict, capas: list[dict], adjunto: dict) -> str | None:
    """El base64 embebido cambia de sitio según la versión y la config del webhook.

    Se miran TODAS las capas del mensaje, no solo la interior: con
    `WEBHOOK_BASE64=true` Evolution lo cuelga del `message` de primer nivel, y
    ese nivel desaparece en cuanto el mensaje viene envuelto (pie de foto,
    efímero, ver una vez). Antes se perdía justo ahí y cada etiqueta con pie de
    foto obligaba a una llamada extra a getBase64FromMediaMessage.
    """
    candidatos: list[Any] = [datos.get("base64"), adjunto.get("base64")]
    candidatos.extend(capa.get("base64") for capa in capas)
    for clave in ("media", "mediaMessage"):
        anidado = datos.get(clave)
        if isinstance(anidado, dict):
            candidatos.append(anidado.get("base64"))
    for candidato in candidatos:
        if isinstance(candidato, str) and candidato.strip():
            return candidato
    return None


def _entero(valor: Any) -> int | None:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None

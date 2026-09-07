#!/usr/bin/env python3
"""Apunta en Glivo las ventas que registra el bot de WhatsApp.

    python -m tools.puente_glivo --simular   # dice qué haría, sin escribir
    python -m tools.puente_glivo             # apunta de verdad

El problema que resuelve: el bot guarda las ventas en su propio `ventas.db`,
pero el panel de El Sistema y `experto_vinted.py` leen la tabla
`eventos_diarios` de `glivo_memory.db`. Sin este puente habría dos
contabilidades y ninguna sería la buena.

Por qué es un proceso aparte y no código dentro del bot:

- El bot corre en Docker y Glivo en el host, con su propio entorno. Desde el
  contenedor no se puede importar `registro_diario`.
- Así no se toca ni una línea de Glivo: solo se llama a su función pública
  `guardar_evento()`, igual que hace cualquier otro módulo suyo.
- Si esto falla, el bot sigue registrando ventas en su base. Se arregla el
  puente y la siguiente pasada recupera lo que falte; no se pierde nada.

Por qué las ventas se leen por HTTP y no abriendo `ventas.db`: la base es del
uid 10001 (el del contenedor) y este puente corre como `claudio`, que es quien
puede escribir en Glivo. Al probarlo con el fichero saltó
`attempt to write a readonly database` incluso en un SELECT — una base en modo
WAL necesita tocar sus ficheros auxiliares hasta para leer. La API del bot no
tiene ese problema, y de paso es un contrato estable: si cambia el esquema de
la base, el puente no se entera.

`glivo_memory.db` está en modo WAL (comprobado el 07/09/2026), así que dos
procesos escribiendo a la vez no se bloquean.

Para deshacerlo: borra este fichero y el estado en `datos/puente_glivo.json`.
No deja nada más. Los eventos ya apuntados en Glivo se borran a mano si hace
falta, buscando por `texto_original` los que acaben en `[bot ventas #<id>]`.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Iterable

RAIZ = Path(__file__).resolve().parent.parent
GLIVO = Path("/home/claudio/glivo")

# Los canales que Glivo acepta (CANALES_PERMITIDOS en registro_diario.py).
CANALES = {"vinted": "vinted", "wallapop": "wallapop"}

# La marca que deja el puente al final del texto, para poder reconocer
# después qué apuntes vinieron de aquí y no duplicarlos a mano.
MARCA = "[bot ventas #{id}]"


def canal_para_glivo(plataforma: str | None) -> str | None:
    """Traduce la plataforma del bot al canal que entiende Glivo."""
    if not plataforma:
        return None
    return CANALES.get(plataforma.strip().lower())


def texto_para_glivo(venta: dict[str, Any]) -> str:
    """Frase parecida a la que escribiría Claudio con `Registro:` a mano."""
    articulo = (venta.get("articulo") or "artículo sin identificar").strip()
    partes = [articulo]
    transportista = (venta.get("transportista") or "").strip()
    if transportista:
        partes.append(f"por {transportista}")
    partes.append(MARCA.format(id=venta["id"]))
    return " ".join(partes)


def leer_estado(ruta: Path) -> set[int]:
    """Ids de venta ya apuntados. Si el fichero no existe o está roto, vacío."""
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        return {int(i) for i in datos.get("apuntadas", [])}
    except (OSError, ValueError, TypeError):
        return set()


def escribir_estado(ruta: Path, apuntadas: Iterable[int]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        json.dumps({"apuntadas": sorted(apuntadas)}, indent=2), encoding="utf-8"
    )


def descargar_ventas(url_base: str, *, pagina: int = 200) -> list[dict[str, Any]]:
    """Baja todas las ventas del bot por su API, paginando."""
    todas: list[dict[str, Any]] = []
    desplazamiento = 0
    while True:
        url = f"{url_base}/ventas?limite={pagina}&desplazamiento={desplazamiento}"
        with urllib.request.urlopen(url, timeout=30) as respuesta:  # noqa: S310
            lote = json.loads(respuesta.read().decode("utf-8"))
        if not isinstance(lote, list) or not lote:
            break
        todas.extend(lote)
        if len(lote) < pagina:
            break
        desplazamiento += pagina
    return todas


def seleccionar(
    ventas: list[dict[str, Any]], ya_apuntadas: set[int]
) -> list[dict[str, Any]]:
    """Las que hay que apuntar: con precio, no canceladas y no apuntadas ya.

    Sin precio no se apunta: un evento de venta sin importe le crea a Glivo una
    fila en `ventas_pendientes` y te acaba preguntando el importe por Telegram,
    que es justo el trabajo manual que el bot viene a quitar. Cuando el precio
    llegue (por la fusión al recibir la etiqueta), entrará en la pasada siguiente.
    """
    elegidas = [
        v
        for v in ventas
        if v.get("precio_venta") is not None
        and v.get("estado") != "cancelado"
        and v.get("id") not in ya_apuntadas
    ]
    return sorted(elegidas, key=lambda v: v["id"])


def apuntar(
    ventas: list[dict[str, Any]],
    guardar_evento: Callable[..., int],
    *,
    simular: bool = False,
) -> tuple[list[int], list[str]]:
    """Apunta cada venta en Glivo. Devuelve (ids apuntados, problemas)."""
    apuntadas: list[int] = []
    problemas: list[str] = []

    for venta in ventas:
        canal = canal_para_glivo(venta.get("plataforma"))
        if canal is None:
            problemas.append(
                f"venta #{venta['id']}: plataforma {venta.get('plataforma')!r} "
                "no es un canal de Glivo; no se apunta"
            )
            continue

        texto = texto_para_glivo(venta)
        if simular:
            print(f"  [simulado] venta #{venta['id']}: "
                  f"{venta['precio_venta']} eur, canal {canal} — {texto}")
            apuntadas.append(venta["id"])
            continue

        # guardar_evento falla en silencio devolviendo -1: hay que mirarlo, o
        # las ventas se perderían sin que nadie se entere.
        evento_id = guardar_evento(
            tipo="venta",
            valor=float(venta["precio_venta"]),
            unidad="eur",
            canal=canal,
            texto_original=texto,
            fecha=(venta.get("fecha_registro") or "")[:10] or None,
        )
        if evento_id == -1:
            problemas.append(f"venta #{venta['id']}: Glivo la rechazó (devolvió -1)")
            continue
        apuntadas.append(venta["id"])

    return apuntadas, problemas


def main() -> int:
    parser = argparse.ArgumentParser(description="Apunta en Glivo las ventas del bot")
    parser.add_argument("--simular", action="store_true",
                        help="ensena lo que haria, sin escribir en Glivo")
    parser.add_argument("--url", default="http://127.0.0.1:8000",
                        help="API del bot de ventas")
    parser.add_argument("--estado", default=str(RAIZ / "datos" / "puente_glivo.json"),
                        help="fichero con los ids ya apuntados")
    parser.add_argument("--glivo", default=str(GLIVO),
                        help="carpeta de Glivo (de donde se importa registro_diario)")
    args = parser.parse_args()

    estado_path = Path(args.estado)
    ya = leer_estado(estado_path)

    try:
        todas = descargar_ventas(args.url.rstrip("/"))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"No he podido leer las ventas en {args.url}: {exc}")
        print("Comprueba que el bot esta vivo:  docker compose ps")
        return 1

    ventas = seleccionar(todas, ya)
    if not ventas:
        print(f"Nada nuevo que apuntar ({len(todas)} ventas en el bot, "
              f"{len(ya)} ya estaban en Glivo).")
        return 0

    print(f"Ventas nuevas con precio: {len(ventas)} (de {len(todas)} en el bot)")

    guardar_evento: Callable[..., int]
    if args.simular:
        def guardar_evento(**_: Any) -> int:
            return 0
    else:
        sys.path.insert(0, args.glivo)
        try:
            from registro_diario import guardar_evento as _guardar  # type: ignore
        except ImportError as exc:
            print(f"No puedo importar registro_diario desde {args.glivo}: {exc}")
            print("Este puente se ejecuta en el host, con el Python de Glivo:")
            print("  cd /home/claudio/glivo && ./.venv/bin/python \\")
            print("    /home/claudio/sistema/whatsapp-ventas/tools/puente_glivo.py")
            return 1
        guardar_evento = _guardar

    apuntadas, problemas = apuntar(ventas, guardar_evento, simular=args.simular)

    for problema in problemas:
        print(f"  AVISO: {problema}")

    if apuntadas and not args.simular:
        escribir_estado(estado_path, ya | set(apuntadas))

    sufijo = " (simulado, no se ha escrito nada)" if args.simular else ""
    print("")
    print(f"Apuntadas en Glivo: {len(apuntadas)}{sufijo}")
    if problemas:
        print(f"Con problemas: {len(problemas)} - se reintentaran en la proxima pasada.")
    return 0



if __name__ == "__main__":
    sys.exit(main())

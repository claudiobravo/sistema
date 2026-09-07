"""Persistencia en SQLite. Sin ORM: son cuatro tablas y una consulta por caso."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from .models import Estado, RegistroVenta
from .validacion import normalizar_codigo

ESQUEMA = """
CREATE TABLE IF NOT EXISTS ventas (
    id                        INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_registro            TEXT    NOT NULL,
    articulo                  TEXT,
    plataforma                TEXT    NOT NULL DEFAULT 'Otro',
    precio_venta              REAL,
    transportista             TEXT,
    codigo_seguimiento        TEXT,
    codigo_norm               TEXT,
    destinatario_o_punto_pack TEXT,
    estado                    TEXT    NOT NULL DEFAULT 'pendiente_envio',
    confianza                 REAL    NOT NULL DEFAULT 0,
    origen                    TEXT    NOT NULL DEFAULT 'texto',
    tipo_documento            TEXT    NOT NULL DEFAULT 'desconocido',
    mensaje_id                TEXT,
    remitente                 TEXT,
    avisos                    TEXT    NOT NULL DEFAULT '[]',
    creado_en                 TEXT    NOT NULL,
    actualizado_en            TEXT    NOT NULL
);

-- Una etiqueta puede llegar dos veces (reenvío, reintento del gateway) y la
-- captura de la venta suele llegar antes que el PDF: el tracking es la clave
-- natural para fusionar ambos en un único pedido.
CREATE UNIQUE INDEX IF NOT EXISTS ux_ventas_codigo
    ON ventas(codigo_norm) WHERE codigo_norm IS NOT NULL AND codigo_norm <> '';
CREATE INDEX IF NOT EXISTS ix_ventas_estado ON ventas(estado);
CREATE INDEX IF NOT EXISTS ix_ventas_fecha  ON ventas(fecha_registro);

CREATE TABLE IF NOT EXISTS mensajes_procesados (
    mensaje_id   TEXT PRIMARY KEY,
    procesado_en TEXT NOT NULL,
    resultado    TEXT
);
"""

_CAMPOS_FUSIONABLES = (
    "articulo",
    "precio_venta",
    "transportista",
    "codigo_seguimiento",
    "destinatario_o_punto_pack",
)


def _ahora() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Almacen:
    def __init__(self, ruta: str | Path) -> None:
        self.ruta = str(ruta)

    def inicializar(self) -> None:
        if self.ruta != ":memory:":
            Path(self.ruta).parent.mkdir(parents=True, exist_ok=True)
        with self._conexion() as con:
            con.executescript(ESQUEMA)

    @contextmanager
    def _conexion(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.ruta, timeout=15)
        con.row_factory = sqlite3.Row
        try:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA foreign_keys=ON")
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    # --- idempotencia -----------------------------------------------------
    def mensaje_visto(self, mensaje_id: str) -> bool:
        with self._conexion() as con:
            fila = con.execute(
                "SELECT 1 FROM mensajes_procesados WHERE mensaje_id = ?", (mensaje_id,)
            ).fetchone()
        return fila is not None

    def marcar_mensaje(self, mensaje_id: str, resultado: str) -> None:
        with self._conexion() as con:
            con.execute(
                "INSERT INTO mensajes_procesados (mensaje_id, procesado_en, resultado) "
                "VALUES (?, ?, ?) ON CONFLICT(mensaje_id) DO UPDATE SET "
                "procesado_en = excluded.procesado_en, resultado = excluded.resultado",
                (mensaje_id, _ahora(), resultado),
            )

    # --- ventas -----------------------------------------------------------
    def guardar(self, registro: RegistroVenta) -> tuple[RegistroVenta, bool]:
        """Inserta la venta, o la fusiona con la que ya tuviera ese tracking.

        Devuelve `(registro_final, creado)`.
        """
        codigo_norm = normalizar_codigo(registro.codigo_seguimiento) or None
        ahora = _ahora()
        with self._conexion() as con:
            existente = None
            if codigo_norm:
                existente = con.execute(
                    "SELECT * FROM ventas WHERE codigo_norm = ?", (codigo_norm,)
                ).fetchone()

            if existente is not None:
                cambios: dict[str, object] = {}
                for campo in _CAMPOS_FUSIONABLES:
                    nuevo = getattr(registro, campo)
                    if nuevo not in (None, "") and existente[campo] in (None, ""):
                        cambios[campo] = nuevo
                avisos = sorted(set(json.loads(existente["avisos"]) + registro.avisos))
                cambios["avisos"] = json.dumps(avisos, ensure_ascii=False)
                cambios["confianza"] = max(existente["confianza"], registro.confianza)
                cambios["actualizado_en"] = ahora
                asignaciones = ", ".join(f"{k} = ?" for k in cambios)
                con.execute(
                    f"UPDATE ventas SET {asignaciones} WHERE id = ?",
                    (*cambios.values(), existente["id"]),
                )
                fila = con.execute(
                    "SELECT * FROM ventas WHERE id = ?", (existente["id"],)
                ).fetchone()
                return _a_registro(fila), False

            cursor = con.execute(
                "INSERT INTO ventas (fecha_registro, articulo, plataforma, precio_venta,"
                " transportista, codigo_seguimiento, codigo_norm, destinatario_o_punto_pack,"
                " estado, confianza, origen, tipo_documento, mensaje_id, remitente, avisos,"
                " creado_en, actualizado_en)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    registro.fecha_registro,
                    registro.articulo,
                    registro.plataforma,
                    registro.precio_venta,
                    registro.transportista,
                    registro.codigo_seguimiento,
                    codigo_norm,
                    registro.destinatario_o_punto_pack,
                    registro.estado,
                    registro.confianza,
                    registro.origen,
                    registro.tipo_documento,
                    registro.mensaje_id,
                    registro.remitente,
                    json.dumps(registro.avisos, ensure_ascii=False),
                    ahora,
                    ahora,
                ),
            )
            fila = con.execute(
                "SELECT * FROM ventas WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
        return _a_registro(fila), True

    def obtener(self, venta_id: int) -> Optional[RegistroVenta]:
        with self._conexion() as con:
            fila = con.execute("SELECT * FROM ventas WHERE id = ?", (venta_id,)).fetchone()
        return _a_registro(fila) if fila else None

    def buscar_por_referencia(self, referencia: str) -> Optional[RegistroVenta]:
        """Busca por `#id`, por id a secas o por código de seguimiento."""
        referencia = referencia.strip().lstrip("#")
        with self._conexion() as con:
            if referencia.isdigit():
                fila = con.execute(
                    "SELECT * FROM ventas WHERE id = ?", (int(referencia),)
                ).fetchone()
                if fila:
                    return _a_registro(fila)
            norm = normalizar_codigo(referencia)
            if not norm:
                return None
            fila = con.execute(
                "SELECT * FROM ventas WHERE codigo_norm = ?", (norm,)
            ).fetchone()
        return _a_registro(fila) if fila else None

    def cambiar_estado(self, venta_id: int, estado: Estado) -> Optional[RegistroVenta]:
        with self._conexion() as con:
            con.execute(
                "UPDATE ventas SET estado = ?, actualizado_en = ? WHERE id = ?",
                (estado, _ahora(), venta_id),
            )
            fila = con.execute("SELECT * FROM ventas WHERE id = ?", (venta_id,)).fetchone()
        return _a_registro(fila) if fila else None

    def listar(
        self, *, estado: Estado | None = None, limite: int = 50, desplazamiento: int = 0
    ) -> list[RegistroVenta]:
        consulta = "SELECT * FROM ventas"
        parametros: list[object] = []
        if estado:
            consulta += " WHERE estado = ?"
            parametros.append(estado)
        consulta += " ORDER BY id DESC LIMIT ? OFFSET ?"
        parametros += [limite, desplazamiento]
        with self._conexion() as con:
            filas = con.execute(consulta, parametros).fetchall()
        return [_a_registro(f) for f in filas]

    def resumen(self) -> dict[str, object]:
        with self._conexion() as con:
            total = con.execute("SELECT COUNT(*) AS n FROM ventas").fetchone()["n"]
            pendientes = con.execute(
                "SELECT COUNT(*) AS n FROM ventas WHERE estado = 'pendiente_envio'"
            ).fetchone()["n"]
            ingresos = con.execute(
                "SELECT COALESCE(SUM(precio_venta), 0) AS s FROM ventas"
            ).fetchone()["s"]
        return {"total": total, "pendientes": pendientes, "ingresos": round(ingresos, 2)}


def _a_registro(fila: sqlite3.Row) -> RegistroVenta:
    datos = dict(fila)
    datos.pop("codigo_norm", None)
    datos.pop("creado_en", None)
    datos.pop("actualizado_en", None)
    datos["avisos"] = json.loads(datos.get("avisos") or "[]")
    return RegistroVenta(**datos)

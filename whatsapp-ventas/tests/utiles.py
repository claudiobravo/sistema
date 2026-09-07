"""Generador de PDFs mínimos para las pruebas (sin dependencias extra)."""

from __future__ import annotations


def _escapar(texto: str) -> str:
    return texto.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def pdf_de_prueba(lineas: list[str]) -> bytes:
    """Devuelve un PDF válido de una página con esas líneas de texto."""
    cuerpo_texto = "BT /F1 11 Tf 20 260 Td 14 TL\n"
    cuerpo_texto += "".join(f"({_escapar(linea)}) Tj T*\n" for linea in lineas)
    cuerpo_texto += "ET"
    flujo = cuerpo_texto.encode("latin-1", "replace")

    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 320 300] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(flujo)).encode() + b" >>\nstream\n" + flujo + b"\nendstream",
    ]

    salida = bytearray(b"%PDF-1.4\n")
    desplazamientos: list[int] = []
    for numero, objeto in enumerate(objetos, start=1):
        desplazamientos.append(len(salida))
        salida += f"{numero} 0 obj\n".encode() + objeto + b"\nendobj\n"

    inicio_xref = len(salida)
    salida += f"xref\n0 {len(objetos) + 1}\n".encode()
    salida += b"0000000000 65535 f \n"
    for desplazamiento in desplazamientos:
        salida += f"{desplazamiento:010d} 00000 n \n".encode()
    salida += f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{inicio_xref}\n%%EOF\n".encode()
    return bytes(salida)


PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000a49444154789c6360000002000100ffff0300000600"
    "0557bfabd40000000049454e44ae426082"
)

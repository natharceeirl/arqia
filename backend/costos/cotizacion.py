"""Importación de cotizaciones: CSV, Excel, PDF o imagen.

CSV y Excel se leen de forma directa. PDF e imágenes los interpreta Claude, y cada precio extraído de
un PDF se contrasta con el texto del documento: si no aparece, el ítem queda marcado para revisión.
"""
from __future__ import annotations

import base64
import csv
import io
import json
import logging
import os
import re
import uuid

from . import ItemCotizacion, _n, clasificar_partida

log = logging.getLogger("arqia.cotizacion")

CABECERAS = {
    "descripcion": ("descrip", "partida", "item", "concepto", "material", "detalle", "producto"),
    "unidad": ("unid", "und", "u.m", "um", "medida"),
    "cantidad": ("cant", "metrado"),
    "precio": ("p.u", "p/u", "precio unit", "costo unit", "valor unit", "precio", "pu"),
    "total": ("parcial", "subtotal", "total", "importe"),
}


def numero(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).replace("S/", "").replace("s/", "").replace("PEN", "").strip()
    t = re.sub(r"[^\d,.\-]", "", t)
    if not t or not re.search(r"\d", t):
        return None
    if "," in t and "." in t:
        t = t.replace(",", "") if t.rfind(".") > t.rfind(",") else t.replace(".", "").replace(",", ".")
    elif "," in t:
        partes = t.split(",")
        t = t.replace(",", "") if len(partes[-1]) == 3 and len(partes) > 1 else t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def _columnas(cab: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for i, c in enumerate(cab):
        cn = _n(str(c or ""))
        for clave, alias in CABECERAS.items():
            if clave not in out and any(a in cn for a in alias):
                # "precio" no debe tomar la columna "precio total"
                if clave == "precio" and any(a in cn for a in ("total", "parcial")):
                    continue
                out[clave] = i
                break
    return out


def _de_filas(filas: list[list], fuente: str) -> list[ItemCotizacion]:
    idx_cab, cols = None, {}
    for i, f in enumerate(filas[:30]):
        c = _columnas([str(x or "") for x in f])
        if "descripcion" in c and ("precio" in c or "total" in c):
            idx_cab, cols = i, c
            break
    if idx_cab is None:
        raise ValueError("No se encontró una fila de encabezados con descripción y precio.")
    items = []
    for f in filas[idx_cab + 1:]:
        get = lambda k: f[cols[k]] if k in cols and cols[k] < len(f) else None  # noqa: E731
        desc = str(get("descripcion") or "").strip()
        precio = numero(get("precio"))
        cant = numero(get("cantidad"))
        total = numero(get("total"))
        if precio is None and total is not None and cant:
            precio = total / cant
        if not desc or precio is None:
            continue
        items.append(ItemCotizacion(id=uuid.uuid4().hex[:8], descripcion=desc[:120], partida=clasificar_partida(desc),
                                    unidad=str(get("unidad") or "glb").strip() or "glb", cantidad=cant,
                                    cantidad_origen="usuario" if cant else "modelo", precio_unitario=round(precio, 4),
                                    fuente=fuente, verificado=True))
    return items


def _texto_pdf(datos: bytes) -> str:
    from pypdf import PdfReader
    r = PdfReader(io.BytesIO(datos))
    return "\n".join((p.extract_text() or "") for p in r.pages[:30])


def _aparece(precio: float, texto: str) -> bool:
    t = texto.replace(" ", "")
    formas = {f"{precio:.2f}", f"{precio:,.2f}", f"{precio:.2f}".replace(".", ","), f"{precio:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")}
    if float(precio).is_integer():
        formas |= {str(int(precio)), f"{int(precio):,}"}
    return any(f in t for f in formas)


HERRAMIENTA = {
    "name": "registrar_partidas",
    "description": "Registra las partidas de la cotización tal como aparecen en el documento. No inventes valores.",
    "input_schema": {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {
        "descripcion": {"type": "string"}, "unidad": {"type": "string"},
        "cantidad": {"type": ["number", "null"]}, "precio_unitario": {"type": "number"},
        "moneda": {"type": "string", "description": "PEN o USD"}}, "required": ["descripcion", "precio_unitario"]}}},
        "required": ["items"]},
}


def _con_claude(bloque: dict, fuente: str, texto_pdf: str | None) -> list[ItemCotizacion]:
    import anthropic
    from ia.entrevista import MODELO
    cliente = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=60.0, max_retries=1)
    resp = cliente.messages.create(
        model=MODELO, max_tokens=4000, tools=[HERRAMIENTA], tool_choice={"type": "auto"},
        system="Extraes partidas de cotizaciones de construcción. Responde únicamente llamando a registrar_partidas con los precios unitarios exactos del documento.",
        messages=[{"role": "user", "content": [bloque, {"type": "text", "text": "Extrae todas las partidas con su unidad, cantidad y precio unitario."}]}],
    )
    datos = next((b.input for b in resp.content if b.type == "tool_use"), {"items": []})
    items = []
    for d in datos.get("items", []):
        precio = numero(d.get("precio_unitario"))
        if precio is None or not d.get("descripcion"):
            continue
        cant = numero(d.get("cantidad"))
        items.append(ItemCotizacion(
            id=uuid.uuid4().hex[:8], descripcion=str(d["descripcion"])[:120], partida=clasificar_partida(d["descripcion"]),
            unidad=str(d.get("unidad") or "glb"), cantidad=cant, cantidad_origen="usuario" if cant else "modelo",
            precio_unitario=round(precio, 4), moneda=(d.get("moneda") or "PEN").upper()[:3], fuente=fuente,
            verificado=_aparece(precio, texto_pdf) if texto_pdf is not None else None))
    return items


def importar(nombre: str, datos: bytes) -> dict:
    ext = nombre.lower().rsplit(".", 1)[-1] if "." in nombre else ""
    avisos: list[str] = []
    if ext in ("csv", "txt"):
        try:
            texto = datos.decode("utf-8-sig")
        except UnicodeDecodeError:
            texto = datos.decode("latin-1")
        dialecto = csv.Sniffer().sniff(texto[:4000], delimiters=",;\t")
        items = _de_filas(list(csv.reader(io.StringIO(texto), dialecto)), nombre)
        metodo = "lectura directa"
    elif ext in ("xlsx", "xlsm"):
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(datos), data_only=True, read_only=True)
        items = []
        for ws in wb.worksheets:
            try:
                items = _de_filas([list(r) for r in ws.iter_rows(values_only=True)], f"{nombre} ({ws.title})")
                if items:
                    break
            except ValueError:
                continue
        if not items:
            raise ValueError("No se encontraron partidas con descripción y precio en el libro.")
        metodo = "lectura directa"
    elif ext == "pdf":
        texto = _texto_pdf(datos)
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise ValueError("Leer cotizaciones en PDF requiere el asistente con IA. Usa un archivo CSV o Excel.")
        bloque = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": base64.b64encode(datos).decode()}}
        items = _con_claude(bloque, nombre, texto)
        metodo = "extracción con IA y contraste con el texto del PDF"
        sin = sum(1 for i in items if i.verificado is False)
        if sin:
            avisos.append(f"{sin} precios no se encontraron en el texto del PDF: revísalos antes de usarlos.")
    elif ext in ("png", "jpg", "jpeg", "webp"):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise ValueError("Leer imágenes requiere el asistente con IA.")
        tipo = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
        bloque = {"type": "image", "source": {"type": "base64", "media_type": tipo, "data": base64.b64encode(datos).decode()}}
        items = _con_claude(bloque, nombre, None)
        metodo = "extracción con IA desde imagen"
        avisos.append("Los precios leídos de una imagen no se pueden contrastar automáticamente: revísalos.")
    else:
        raise ValueError("Formato no admitido. Usa CSV, Excel (.xlsx), PDF o imagen.")
    if any(i.moneda != "PEN" for i in items):
        avisos.append("Hay precios en moneda distinta de soles; conviértelos antes de sumarlos.")
    return {"archivo": nombre, "metodo": metodo, "items": [i.model_dump() for i in items], "avisos": avisos}

"""Paquete de proyecto ARQIA (.arqia): un zip con el modelo IFC y un archivo de datos.

modelo.ifc   alternativa elegida en IFC4, con la estimación de costos como IfcCostSchedule
datos.json   brief, alternativas, materiales, cotizaciones, terreno, decisiones y fuentes
LEEME.txt    descripción del contenido
"""
from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone

from motor import MOTOR_VERSION, generar
from motor.modelos import Alternativa, Brief

from .ifc import exportar_ifc

FORMATO = "arqia-paquete/1"

LEEME = """Paquete de proyecto ARQIA
=========================
modelo.ifc  Modelo BIM (IFC4) de la alternativa elegida. Incluye niveles, espacios, muros con vanos,
            puertas, ventanas, losas, escalera, propiedades de ARQIA y la estimación de costos
            (IfcCostSchedule). Se abre en Revit, Archicad, BIMvision, Bonsai y otros visores IFC.
datos.json  Datos del proyecto: brief, alternativas, especificación de materiales, cotizaciones,
            terreno, decisiones del cliente y fuentes de cada precio. ARQIA lo vuelve a importar.

Resultados preliminares: requieren revisión de profesionales competentes.
"""


def exportar(brief: Brief, alternativas: list[Alternativa], elegida: str, costos: dict | None, extra: dict) -> bytes:
    alt = next(a for a in alternativas if a.id == elegida)
    datos = {
        "formato": FORMATO,
        "creado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "motor_version": MOTOR_VERSION,
        "brief": brief.model_dump(mode="json"),
        "alternativa_elegida": elegida,
        "huellas": {a.id: a.huella for a in alternativas},
        "alternativas": [a.model_dump(mode="json") for a in alternativas],
        "costos": {"entrada": extra.get("costos_entrada"), "resultado": costos},
        "decisiones": extra.get("decisiones", []),
        "notas_cliente": extra.get("notas_cliente", ""),
        "colores": extra.get("colores", {}),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("modelo.ifc", exportar_ifc(brief, alt, costos))
        z.writestr("datos.json", json.dumps(datos, ensure_ascii=False, indent=1))
        z.writestr("LEEME.txt", LEEME)
    return buf.getvalue()


def importar(contenido: bytes) -> dict:
    try:
        z = zipfile.ZipFile(io.BytesIO(contenido))
    except zipfile.BadZipFile as e:
        raise ValueError("El archivo no es un paquete .arqia válido.") from e
    if "datos.json" not in z.namelist():
        raise ValueError("El paquete no contiene datos.json.")
    datos = json.loads(z.read("datos.json").decode("utf-8"))
    if datos.get("formato") != FORMATO:
        raise ValueError("Formato de paquete no reconocido.")
    brief = Brief(**datos["brief"])
    # reproducibilidad: se regenera el diseño y se comparan las huellas
    nuevas = {a.id: a.huella for a in generar(brief)}
    datos["reproducible"] = all(nuevas.get(k) == v for k, v in datos.get("huellas", {}).items())
    datos["tiene_ifc"] = "modelo.ifc" in z.namelist()
    return datos

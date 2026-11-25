"""API de ARQIA. Sirve también la interfaz compilada (frontend/dist) en la misma URL."""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import unicodedata
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from bim import paquete
from bim.ifc import exportar_ifc, verificar_ifc
from costos import EntradaCostos, calcular, tabla
from costos import cotizacion as cot
from ia import comparacion, entrevista
from motor import MOTOR_VERSION, BriefIncompleto, generar
from motor.modelos import Alternativa, Brief, ParametrosMotor
from motor.programa import completar_areas
from reglas import avisos_activos, verificaciones_contexto

logging.basicConfig(level=logging.INFO)
RAIZ = Path(__file__).resolve().parents[2]
DEMO = Path(__file__).resolve().parents[1] / "demo"

app = FastAPI(title="ARQIA", version=MOTOR_VERSION)
origenes = [o for o in os.environ.get("ARQIA_CORS", "*").split(",") if o]
app.add_middleware(CORSMiddleware, allow_origins=origenes, allow_methods=["*"], allow_headers=["*"])


class TurnoIn(BaseModel):
    brief: Brief
    historial: list[dict] = Field(default_factory=list)
    mensaje: str | None = None
    avisos_mostrados: list[str] = Field(default_factory=list)


class AplicarIn(BaseModel):
    brief: Brief
    cambios: dict


class GenerarIn(BaseModel):
    brief: Brief
    parametros: ParametrosMotor | None = None


class ExplicarIn(BaseModel):
    brief: dict
    alternativas: list[dict]


class IfcIn(BaseModel):
    brief: Brief
    alternativa: Alternativa
    costos: EntradaCostos | None = None


class CostosIn(BaseModel):
    alternativa: Alternativa
    entrada: EntradaCostos = Field(default_factory=EntradaCostos)


class ArchivoIn(BaseModel):
    nombre: str
    base64: str


class PaqueteIn(BaseModel):
    brief: Brief
    alternativas: list[Alternativa]
    elegida: str
    costos: EntradaCostos = Field(default_factory=EntradaCostos)
    decisiones: list[dict] = Field(default_factory=list)
    notas_cliente: str = ""
    colores: dict = Field(default_factory=dict)


@app.get("/api/salud")
def salud():
    return {"ok": True, "motor": MOTOR_VERSION, "asistente": bool(os.environ.get("ANTHROPIC_API_KEY")), "modelo": entrevista.MODELO}


@app.post("/api/entrevista/turno")
def turno(t: TurnoIn):
    try:
        return entrevista.turno(t.brief, t.historial, t.mensaje, t.avisos_mostrados)
    except Exception as e:  # noqa: BLE001
        logging.exception("Fallo en la entrevista con IA; se continúa en modo formulario")
        r = entrevista.turno_formulario(t.brief, t.avisos_mostrados)
        r.update(modo="formulario", brief=t.brief.model_dump(mode="json"), errores=[f"Asistente no disponible: {type(e).__name__}"],
                 estado=entrevista.estado(t.brief), avisos=avisos_activos(t.brief))
        return r


@app.post("/api/brief/aplicar")
def aplicar(a: AplicarIn):
    nuevo, errores = entrevista.aplicar(a.brief, a.cambios)
    return {"brief": nuevo.model_dump(mode="json"), "errores": errores, "estado": entrevista.estado(nuevo),
            "avisos": avisos_activos(nuevo), "siguiente": entrevista.turno_formulario(nuevo, [])}


@app.post("/api/alternativas")
def alternativas(g: GenerarIn):
    brief = completar_areas(g.brief)
    try:
        alts = generar(brief, g.parametros)
    except BriefIncompleto as e:
        raise HTTPException(422, {"mensaje": str(e), "faltantes": e.faltantes}) from e
    ctx = verificaciones_contexto(brief)
    salida = []
    for a in alts:
        a.verificaciones += ctx
        salida.append(a.model_dump(mode="json"))
    return {"brief": brief.model_dump(mode="json"), "alternativas": salida, "avisos": avisos_activos(brief)}


@app.post("/api/comparacion/explicar")
def explicar(e: ExplicarIn):
    return comparacion.explicar(e.brief, e.alternativas)


def _slug(t: str) -> str:
    t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower() or "proyecto"


@app.get("/api/costos/vuoe")
def vuoe():
    return tabla()


@app.post("/api/costos/calcular")
def costos(c: CostosIn):
    try:
        return calcular(c.alternativa, c.entrada)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@app.post("/api/cotizacion/importar")
def importar_cotizacion(a: ArchivoIn):
    datos = base64.b64decode(a.base64)
    if len(datos) > 15 * 1024 * 1024:
        raise HTTPException(413, "El archivo supera 15 MB.")
    try:
        return cot.importar(a.nombre, datos)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:  # noqa: BLE001
        logging.exception("Fallo al importar la cotización")
        raise HTTPException(500, f"No se pudo leer el archivo: {type(e).__name__}") from e


@app.post("/api/paquete/exportar")
def exportar_paquete(p: PaqueteIn):
    alt = next((a for a in p.alternativas if a.id == p.elegida), None)
    if not alt:
        raise HTTPException(422, "La alternativa elegida no existe.")
    res = calcular(alt, p.costos)
    z = paquete.exportar(p.brief, p.alternativas, p.elegida, res, {
        "costos_entrada": p.costos.model_dump(mode="json"), "decisiones": p.decisiones,
        "notas_cliente": p.notas_cliente, "colores": p.colores})
    return {"nombre": f"arqia-{_slug(p.brief.nombre_proyecto)}.arqia", "archivo_base64": base64.b64encode(z).decode(), "tamano_kb": round(len(z) / 1024, 1)}


@app.post("/api/paquete/importar")
def importar_paquete(a: ArchivoIn):
    try:
        return paquete.importar(base64.b64decode(a.base64))
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@app.post("/api/ifc")
def ifc(i: IfcIn):
    res = calcular(i.alternativa, i.costos) if i.costos else None
    datos = exportar_ifc(i.brief, i.alternativa, res)
    verif = verificar_ifc(datos, i.alternativa)
    nombre = f"arqia-{_slug(i.brief.nombre_proyecto)}-alternativa-{i.alternativa.id.lower()}.ifc"
    return {"nombre": nombre, "verificacion": verif, "archivo_base64": base64.b64encode(datos).decode()}


@app.get("/api/demo")
def demo():
    brief = Brief(**json.loads((DEMO / "brief_arequipa.json").read_text(encoding="utf-8")))
    conversacion = json.loads((DEMO / "conversacion_arequipa.json").read_text(encoding="utf-8"))
    gen = alternativas(GenerarIn(brief=brief))
    return {**gen, "conversacion": conversacion}


# ---------------------------------------------------------------- interfaz
DIST = RAIZ / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{ruta:path}")
    def spa(ruta: str):
        f = DIST / ruta
        if ruta and f.is_file():
            return FileResponse(f)
        return FileResponse(DIST / "index.html")

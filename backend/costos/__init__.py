"""Estimación de costos de ARQIA.

Base oficial: Cuadro de Valores Unitarios Oficiales de Edificación (VUOE) para la Costa, en soles por m²
de área techada y por partida. Las cotizaciones que importe el usuario se suman como partidas propias
o reemplazan una partida oficial. Todo el cálculo es determinista y muestra su fuente.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from motor.modelos import Alternativa

TABLA = Path(__file__).with_name("vuoe_costa_2026_11.json")
PARTIDAS = ["muros", "techos", "pisos", "puertas_ventanas", "revestimientos", "banos", "instalaciones"]
POR_AMBIENTE = ["pisos", "revestimientos"]  # partidas que se pueden elegir por ambiente


@lru_cache
def tabla() -> dict:
    return json.loads(TABLA.read_text(encoding="utf-8"))


def valor(partida: str, categoria: str) -> float:
    for p in tabla()["partidas"]:
        if p["id"] == partida:
            for c in p["categorias"]:
                if c["categoria"] == categoria:
                    return float(c["valor_m2"])
    raise ValueError(f"Categoría {categoria} no existe para la partida {partida}")


def _n(t: str) -> str:
    t = (t or "").lower()
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


class ItemCotizacion(BaseModel):
    id: str
    descripcion: str
    partida: str = "otros"  # una de PARTIDAS u "otros"
    unidad: str = "glb"
    cantidad: Optional[float] = None
    cantidad_origen: str = "modelo"  # "modelo" (se calcula) o "usuario"
    precio_unitario: float = 0.0
    moneda: str = "PEN"
    incluir: bool = True
    fuente: str = ""
    verificado: Optional[bool] = None  # el precio aparece en el documento original


class EntradaCostos(BaseModel):
    especificacion: dict[str, str] = Field(default_factory=dict)
    por_ambiente: dict[str, dict[str, str]] = Field(default_factory=dict)  # "nivel:nombre" -> {partida: categoria}
    cotizacion: list[ItemCotizacion] = Field(default_factory=list)
    reemplazos: list[str] = Field(default_factory=list)  # partidas oficiales sustituidas por la cotización
    terreno_valor_m2: Optional[float] = None
    terreno_fuente: Optional[str] = None


# ------------------------------------------------------------------ cantidades del modelo

def cantidades(alt: Alternativa) -> dict:
    q = dict(area_techada_m2=0.0, piso_m2=0.0, muro_m2=0.0, muro_ext_m2=0.0, muro_int_m2=0.0,
             losa_m2=0.0, losa_m3=0.0, puertas_und=0, ventanas_und=0, ventanas_m2=0.0, banos_und=0)
    for nv in alt.niveles:
        for e in nv.espacios:
            if e.funcion != "patio":
                q["area_techada_m2"] += e.area_m2
                q["piso_m2"] += e.area_m2
            if e.funcion == "servicio" and any(k in _n(e.nombre) for k in ("ss.hh", "sshh", "bano")):
                q["banos_und"] += 1
        vanos_por_muro: dict[str, float] = {}
        for v in nv.vanos:
            vanos_por_muro[v.muro_id] = vanos_por_muro.get(v.muro_id, 0) + v.ancho_m * v.alto_m
            if v.tipo == "puerta":
                q["puertas_und"] += 1
            else:
                q["ventanas_und"] += 1
                q["ventanas_m2"] += v.ancho_m * v.alto_m
        for m in nv.muros:
            L = math.hypot(m.b[0] - m.a[0], m.b[1] - m.a[1])
            neto = max(0.0, L * m.altura_m - vanos_por_muro.get(m.id, 0))
            q["muro_m2"] += neto
            q["muro_ext_m2" if m.exterior else "muro_int_m2"] += neto
        for lo in nv.losas:
            q["losa_m2"] += lo.area_m2
            q["losa_m3"] += lo.area_m2 * lo.espesor_m
    return {k: (round(v, 2) if isinstance(v, float) else v) for k, v in q.items()}


UNIDADES = {"m2": ("m2", "m²", "m^2", "mt2", "metro cuadrado", "metros cuadrados"), "m3": ("m3", "m³", "m^3"),
            "und": ("und", "u", "unid", "unidad", "pza", "pieza", "jgo", "juego"), "ml": ("ml", "m", "metro lineal"),
            "glb": ("glb", "global", "gb")}


def unidad_norm(u: str) -> str:
    u = _n(u).strip().rstrip(".")
    for k, alias in UNIDADES.items():
        if u in alias:
            return k
    return u or "glb"


def clasificar_partida(desc: str) -> str:
    d = _n(desc)
    reglas = [
        ("banos", ("inodoro", "lavatorio", "urinario", "ducha", "aparato sanitario", "griferia", "mayolica de bano")),
        ("instalaciones", ("cable", "tuberia", "tubo pvc", "tablero", "interruptor", "tomacorriente", "luminaria", "electric", "sanitari", "desague", "agua fria", "agua caliente")),
        ("puertas_ventanas", ("puerta", "ventana", "vidrio", "mampara", "cerradura", "carpinteria")),
        ("pisos", ("piso", "porcelanato", "ceramico", "ceramica", "parquet", "laminado", "contrapiso", "zocalo", "vinilico")),
        ("revestimientos", ("tarrajeo", "pintura", "enchape", "empaste", "cielo raso", "revestimiento", "solaqueo", "yeso")),
        ("techos", ("losa", "aligerado", "techo", "cobertura", "calamina", "vigueta")),
        ("muros", ("muro", "ladrillo", "columna", "viga", "placa", "albanileria", "concreto", "bloque", "drywall", "cemento", "fierro", "acero", "arena", "piedra")),
    ]
    for partida, claves in reglas:
        if any(k in d for k in claves):
            return partida
    return "otros"


def cantidad_modelo(item: ItemCotizacion, q: dict) -> Optional[float]:
    """Cantidad del modelo que corresponde a la partida y unidad del ítem; None si no hay una equivalente."""
    u, p, d = unidad_norm(item.unidad), item.partida, _n(item.descripcion)
    if u == "m2":
        if p == "muros":
            return q["muro_m2"]
        if p == "revestimientos":
            return round(q["muro_m2"] * 2, 2)  # supuesto: dos caras de muro
        if p == "pisos":
            return q["piso_m2"]
        if p == "techos":
            return q["losa_m2"]
        if p == "puertas_ventanas":
            return q["ventanas_m2"]
    if u == "m3" and p == "techos":
        return round(q["losa_m3"], 2)
    if u == "und":
        if p == "puertas_ventanas":
            if "ventana" in d:
                return q["ventanas_und"]
            if "puerta" in d:
                return q["puertas_und"]
            return q["ventanas_und"] + q["puertas_und"]
        if p == "banos":
            return q["banos_und"]
    return None


# ------------------------------------------------------------------ cálculo

def calcular(alt: Alternativa, entrada: EntradaCostos) -> dict:
    t = tabla()
    spec = {**t["especificacion_por_defecto"], **entrada.especificacion}
    q = cantidades(alt)
    espacios = []
    por_partida = {p: 0.0 for p in PARTIDAS}
    por_nivel: dict[int, float] = {}
    for nv in alt.niveles:
        for e in nv.espacios:
            if e.funcion == "patio":
                continue
            cats = {**spec, **entrada.por_ambiente.get(f"{nv.numero}:{e.nombre}", {})}
            detalle = {p: valor(p, cats[p]) for p in PARTIDAS}
            m2 = sum(detalle.values())
            for p in PARTIDAS:
                por_partida[p] += e.area_m2 * detalle[p]
            costo = e.area_m2 * m2
            por_nivel[nv.numero] = por_nivel.get(nv.numero, 0) + costo
            espacios.append({"id": e.id, "nombre": e.nombre, "nivel": nv.numero, "area_m2": e.area_m2,
                             "categorias": {p: cats[p] for p in POR_AMBIENTE}, "valor_m2": round(m2, 2),
                             "costo": round(costo, 2)})
    items = []
    for it in entrada.cotizacion:
        cant = it.cantidad
        auto = cantidad_modelo(it, q) if it.cantidad_origen == "modelo" else None
        if it.cantidad_origen == "modelo":
            cant = auto if auto is not None else (it.cantidad if it.cantidad is not None else 1.0)
        sub = (cant or 0) * it.precio_unitario
        items.append({**it.model_dump(), "cantidad": round(cant or 0, 2), "cantidad_modelo": auto, "subtotal": round(sub, 2)})
    vuoe_total = sum(por_partida.values())
    vuoe_incluido = sum(v for p, v in por_partida.items() if p not in entrada.reemplazos)
    cot_total = sum(i["subtotal"] for i in items if i["incluir"])
    area_terreno = alt.terreno[2][0] * alt.terreno[2][1]
    terreno = area_terreno * entrada.terreno_valor_m2 if entrada.terreno_valor_m2 else None
    construccion = vuoe_incluido + cot_total
    return {
        "moneda": "PEN",
        "especificacion": spec,
        "espacios": espacios,
        "por_partida": [{"partida": p, "nombre": next(x["nombre"] for x in t["partidas"] if x["id"] == p), "categoria": spec[p],
                         "valor_m2": valor(p, spec[p]), "monto": round(por_partida[p], 2), "reemplazada": p in entrada.reemplazos}
                        for p in PARTIDAS],
        "por_nivel": [{"nivel": k, "monto": round(v, 2)} for k, v in sorted(por_nivel.items())],
        "cantidades": q,
        "cotizacion": items,
        "totales": {
            "vuoe": round(vuoe_total, 2),
            "vuoe_incluido": round(vuoe_incluido, 2),
            "cotizacion": round(cot_total, 2),
            "construccion": round(construccion, 2),
            "construccion_m2": round(construccion / q["area_techada_m2"], 2) if q["area_techada_m2"] else 0,
            "terreno": round(terreno, 2) if terreno is not None else None,
            "total": round(construccion + (terreno or 0), 2),
        },
        "terreno": {"area_m2": round(area_terreno, 2), "valor_m2": entrada.terreno_valor_m2, "fuente": entrada.terreno_fuente},
        "fuente": t["fuente"],
    }

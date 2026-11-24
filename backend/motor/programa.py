"""Áreas sugeridas por defecto cuando el usuario no conoce el área de un ambiente.

Son supuestos declarados, no valores normativos: se marcan con origen "supuesto" y el
usuario puede corregirlos en el resumen.
"""
from __future__ import annotations

import unicodedata

from .modelos import Brief

TABLA = [
    (("ss.hh", "sshh", "baño", "bano", "servicio higien"), 6.0),
    (("kitchenette", "cocineta"), 8.0),
    (("archivo",), 10.0),
    (("almacen", "deposito", "bodega"), 16.0),
    (("recepcion", "caja", "hall de ingreso"), 16.0),
    (("gerencia", "direccion"), 22.0),
    (("sala de reunion", "reunion", "directorio"), 26.0),
    (("oficina",), 20.0),
    (("cocina",), 18.0),
    (("consultorio",), 14.0),
    (("dormitorio",), 12.0),
]


def _n(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def area_sugerida(nombre: str, tipo: str) -> float | None:
    n = _n(nombre)
    for claves, area in TABLA:
        if any(k in n for k in claves):
            return area
    return None


def completar_areas(brief: Brief) -> Brief:
    """Asigna áreas a los ambientes sin área. El ambiente público principal de cada nivel
    recibe el área que queda libre para que el programa ocupe el lote."""
    b = brief.model_copy(deep=True)
    if not (b.terreno.frente_m and b.terreno.fondo_m):
        return b
    util = b.terreno.frente_m * (b.terreno.fondo_m - (b.terreno.retiro_frontal_m or 0)) * 0.82
    for n in range(1, (b.niveles or 1) + 1):
        del_nivel = [a for a in b.ambientes if a.nivel == n]
        sin_area = [a for a in del_nivel if not a.area_objetivo_m2]
        for a in sin_area:
            v = area_sugerida(a.nombre, a.tipo)
            if v:
                a.area_objetivo_m2 = v
                b.origen[f"ambientes.{n}.{a.nombre}.area"] = "supuesto"
        restantes = [a for a in del_nivel if not a.area_objetivo_m2]
        if restantes:
            usado = sum(a.area_objetivo_m2 or 0 for a in del_nivel)
            libre = max(util - usado, 12.0 * len(restantes))
            for a in restantes:
                a.area_objetivo_m2 = round(libre / len(restantes), 1)
                b.origen[f"ambientes.{n}.{a.nombre}.area"] = "supuesto"
        # si el programa supuesto deja mucho lote libre, el ambiente principal supuesto lo absorbe
        supuestos = [a for a in del_nivel if b.origen.get(f"ambientes.{n}.{a.nombre}.area") == "supuesto" and a.tipo != "servicio"]
        deficit = util - sum(a.area_objetivo_m2 or 0 for a in del_nivel)
        if supuestos and deficit > 0.15 * util:
            principal = max(supuestos, key=lambda a: (a.tipo == "publico", a.area_objetivo_m2))
            principal.area_objetivo_m2 = round(principal.area_objetivo_m2 + deficit, 1)
    return b

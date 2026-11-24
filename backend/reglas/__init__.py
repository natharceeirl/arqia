"""Motor de reglas del lugar: decide qué avisos aplican a un brief y su estado de verificación.

Todo es determinista. Claude solo puede mencionar avisos que este módulo activa.
"""
from __future__ import annotations

import unicodedata
from functools import lru_cache
from pathlib import Path

import yaml

from motor.modelos import Brief, Verificacion

RUTA = Path(__file__).with_name("avisos.yaml")


def _norm(t: str | None) -> str:
    t = (t or "").strip().lower()
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


@lru_cache
def base() -> dict:
    return yaml.safe_load(RUTA.read_text(encoding="utf-8"))


def _valor(brief: Brief, campo: str):
    obj = brief
    for parte in campo.split("."):
        obj = getattr(obj, parte, None)
    return obj


def aplica(aviso: dict, brief: Brief) -> bool:
    cond = aviso.get("aplica_si", {})
    if cond.get("siempre"):
        return True
    contexto = [_norm(c) for c in brief.ubicacion.contexto]
    if "contexto_incluye" in cond and any(_norm(k) in c for c in contexto for k in cond["contexto_incluye"]):
        return True
    if "distrito_en" in cond and _norm(brief.ubicacion.distrito) in [_norm(d) for d in cond["distrito_en"]]:
        return True
    if "ciudad_en" in cond and _norm(brief.ubicacion.ciudad) in [_norm(d) for d in cond["ciudad_en"]]:
        return True
    if "tipo_proyecto_incluye" in cond and any(_norm(k) in _norm(brief.tipo_proyecto) for k in cond["tipo_proyecto_incluye"]):
        return True
    if "niveles_min" in cond and (brief.niveles or 0) >= cond["niveles_min"]:
        return True
    return False


def avisos_activos(brief: Brief) -> list[dict]:
    out = []
    for a in base()["avisos"]:
        if aplica(a, brief):
            out.append({k: a.get(k) for k in ("id", "titulo", "texto", "referencia", "url", "revisado_por", "tema")})
    return out


def verificaciones_contexto(brief: Brief) -> list[Verificacion]:
    out = []
    for a in base()["avisos"]:
        v = a.get("verificacion")
        if not v or not aplica(a, brief):
            continue
        if "campo" in v:
            valor = _valor(brief, v["campo"])
            if v.get("cumple_si_definido"):
                ok = valor is not None
            else:
                ok = valor in v.get("cumple_si", [])
            estado = "cumple" if ok else v.get("si_no", "pendiente")
            detalle = (f"Dato registrado: {valor}." if ok else "Falta este dato en el brief.") + " " + a["texto"]
        else:
            estado = v["estado"]
            detalle = a["texto"]
        out.append(Verificacion(id=a["id"], titulo=v["titulo"], estado=estado, detalle=detalle,
                                evidencia=[], fuente=a["referencia"] + (f" ({a['url']})" if a.get("url") else "")))
    return out

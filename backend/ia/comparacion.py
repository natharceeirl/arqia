"""Explicación de la comparación entre alternativas.

Los indicadores ya vienen calculados por el motor. El texto (de Claude o de las reglas de respaldo)
pasa por el verificador de cifras antes de mostrarse.
"""
from __future__ import annotations

import json
import logging
import os

from .entrevista import MODELO
from .verificador import permitidos, verificar_objeto

log = logging.getLogger("arqia.ia")

CRITERIOS = [
    # clave, ventaja, desventaja, unidad, mayor es mejor
    ("area_comercial_m2", "Mayor área de uso público", "Menor área de uso público", "m²", True),
    ("frente_comercial_m", "Mayor frente comercial a la calle", "Menor frente comercial a la calle", "m", True),
    ("ambientes_con_luz_pct", "Más ambientes habitables con luz natural", "Menos ambientes habitables con luz natural", "%", True),
    ("area_ventanas_m2", "Mayor área de ventanas", "Menor área de ventanas", "m²", True),
    ("acceso_directo_pct", "Más ambientes con acceso directo a la circulación", "Menos ambientes con acceso directo a la circulación", "%", True),
    ("circulacion_pct", "Menor proporción de área de circulación", "Mayor proporción de área de circulación", "%", False),
    ("cumplimiento_programa_pct", "Mejor ajuste al programa de áreas", "Menor ajuste al programa de áreas", "%", True),
]


def _f(v):
    return f"{v:.2f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v)


def explicar_reglas(resumen: list[dict], prefer_luz: str | None) -> dict:
    """Explicación determinista: cada ventaja nombra el indicador calculado que la respalda."""
    por = {a["id"]: {"id": a["id"], "ventajas": [], "desventajas": []} for a in resumen}
    for clave, bueno, malo, unidad, mayor in CRITERIOS:
        vals = {a["id"]: a["indicadores"][clave] for a in resumen}
        if len(set(vals.values())) == 1:
            continue
        top = max(vals.values()) if mayor else min(vals.values())
        bottom = min(vals.values()) if mayor else max(vals.values())
        ganadores = [k for k, v in vals.items() if v == top]
        perdedores = [k for k, v in vals.items() if v == bottom]
        if len(ganadores) == 1:
            por[ganadores[0]]["ventajas"].append(f"{bueno}: {_f(top)} {unidad}.")
        if len(perdedores) == 1:
            por[perdedores[0]]["desventajas"].append(f"{malo}: {_f(bottom)} {unidad}.")
    for a in resumen:
        if a["indicadores"].get("acceso_independiente_superior"):
            por[a["id"]]["ventajas"].append("Acceso independiente desde la calle a los niveles superiores.")
        nc = [v["titulo"] for v in a["verificaciones"] if v["estado"] == "no_cumple"]
        if nc:
            por[a["id"]]["desventajas"].append("Observaciones del motor: " + ", ".join(nc).lower() + ".")
    if prefer_luz == "alta":
        rec = max(resumen, key=lambda a: (a["indicadores"]["ambientes_con_luz_pct"], a["indicadores"]["area_ventanas_m2"]))
        motivo = "Indicaste que la luz natural es prioritaria, y es la alternativa con más ventanas entre las que iluminan más ambientes."
    else:
        rec = max(resumen, key=lambda a: a["indicadores"]["area_comercial_m2"])
        motivo = "Es la alternativa con más área de uso público."
    return {
        "resumen": "Las tres alternativas usan el mismo programa y el mismo lote; cambian la posición de la circulación, la escalera y el patio de luz.",
        "por_alternativa": list(por.values()),
        "recomendacion": {"id": rec["id"], "motivo": motivo},
        "fuente": "reglas",
    }


HERRAMIENTA = {
    "name": "redactar_comparacion",
    "description": "Redacta la comparación de alternativas usando solo los indicadores entregados.",
    "input_schema": {
        "type": "object",
        "properties": {
            "resumen": {"type": "string", "description": "Dos frases como máximo."},
            "por_alternativa": {"type": "array", "items": {"type": "object", "properties": {
                "id": {"type": "string"}, "ventajas": {"type": "array", "items": {"type": "string"}},
                "desventajas": {"type": "array", "items": {"type": "string"}}}, "required": ["id", "ventajas", "desventajas"]}},
            "recomendacion": {"type": "object", "properties": {"id": {"type": "string"}, "motivo": {"type": "string"}}, "required": ["id", "motivo"]},
        },
        "required": ["resumen", "por_alternativa", "recomendacion"],
    },
}


def explicar(brief: dict, alternativas: list[dict]) -> dict:
    resumen = [{"id": a["id"], "nombre": a["nombre"], "estrategia": a["estrategia"], "indicadores": a["indicadores"],
                "verificaciones": [{"titulo": v["titulo"], "estado": v["estado"]} for v in a["verificaciones"]]} for a in alternativas]
    pref = (brief.get("preferencias") or {}).get("luz_natural")
    clave = os.environ.get("ANTHROPIC_API_KEY")
    base = explicar_reglas(resumen, pref)
    if not clave:
        return base
    try:
        import anthropic
        cliente = anthropic.Anthropic(api_key=clave, timeout=30.0, max_retries=1)
        resp = cliente.messages.create(
            model=MODELO, max_tokens=1500, temperature=0.2, tools=[HERRAMIENTA],
            tool_choice={"type": "tool", "name": "redactar_comparacion"},
            system=("Eres el Asistente ARQIA. Explicas a un cliente, en español claro y breve, las diferencias entre alternativas "
                    "arquitectónicas preliminares. Usa solo los indicadores y verificaciones entregados; no inventes cifras ni "
                    "afirmes cumplimiento normativo. Cada alternativa: 2 o 3 ventajas y 1 o 2 desventajas. Nunca menciones que eres Claude."),
            messages=[{"role": "user", "content": json.dumps({"preferencias": brief.get("preferencias"), "alternativas": resumen}, ensure_ascii=False)}],
        )
        datos = next(b.input for b in resp.content if b.type == "tool_use")
        descartes: list[str] = []
        datos = verificar_objeto(dict(datos), permitidos(resumen, brief), descartes)
        if descartes:
            log.warning("Frases descartadas por el verificador: %s", descartes)
        datos["fuente"] = "asistente"
        datos["descartes_verificador"] = descartes
        if datos.get("recomendacion", {}).get("id") not in {a["id"] for a in resumen}:
            datos["recomendacion"] = base["recomendacion"]
        return datos
    except Exception as e:  # noqa: BLE001
        log.exception("Fallo de la API al explicar; se usa la explicación por reglas: %s", e)
        return base

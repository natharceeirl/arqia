"""Verificador de cifras: ningún número que muestre el asistente puede faltar en los datos calculados o dados."""
from __future__ import annotations

import json
import re

NUM = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)")
FRASES = re.compile(r"(?<=[.!?;])\s+")


def _numeros_de(obj) -> set[float]:
    texto = json.dumps(obj, ensure_ascii=False, default=str)
    out = set()
    for m in NUM.finditer(texto):
        try:
            v = float(m.group(1).replace(",", "."))
        except ValueError:
            continue
        out.add(round(v, 2))
        out.add(round(v, 1))
        out.add(round(v))
    return out


def permitidos(*fuentes) -> set[float]:
    s: set[float] = set(range(0, 11))  # conteos pequeños: "dos niveles", "3 alternativas"
    for f in fuentes:
        s |= _numeros_de(f)
    return s


def verificar_texto(texto: str, ok: set[float]) -> tuple[str, list[str]]:
    """Devuelve el texto sin las frases que contienen cifras sin origen, y la lista de frases descartadas."""
    if not texto:
        return texto, []
    frases = FRASES.split(texto.strip())
    quedan, fuera = [], []
    for f in frases:
        malos = []
        for m in NUM.finditer(f):
            v = float(m.group(1).replace(",", "."))
            if round(v, 2) not in ok and round(v, 1) not in ok and round(v) not in ok:
                malos.append(m.group(1))
        (fuera if malos else quedan).append(f)
    return " ".join(quedan), fuera


def verificar_objeto(obj, ok: set[float], descartes: list[str]):
    """Aplica el verificador a todas las cadenas de un objeto JSON."""
    if isinstance(obj, str):
        t, f = verificar_texto(obj, ok)
        descartes += f
        return t
    if isinstance(obj, list):
        return [x for x in (verificar_objeto(v, ok, descartes) for v in obj) if x not in ("", None)]
    if isinstance(obj, dict):
        return {k: verificar_objeto(v, ok, descartes) for k, v in obj.items()}
    return obj

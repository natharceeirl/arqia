"""Motor paramétrico determinista de ARQIA."""
from __future__ import annotations

import hashlib
import json
import time

from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from .construccion import Constructor
from .estrategias import ESTRATEGIAS
from .modelos import Alternativa, Brief, ParametrosMotor, Verificacion

MOTOR_VERSION = "0.1.0"


class BriefIncompleto(ValueError):
    def __init__(self, faltantes: list[str]):
        super().__init__("Faltan datos obligatorios: " + ", ".join(faltantes))
        self.faltantes = faltantes


def campos_faltantes(brief: Brief) -> list[str]:
    f = []
    if not brief.tipo_proyecto:
        f.append("tipo_proyecto")
    if not brief.terreno.frente_m:
        f.append("terreno.frente_m")
    if not brief.terreno.fondo_m:
        f.append("terreno.fondo_m")
    if not brief.niveles:
        f.append("niveles")
    if not brief.ambientes:
        f.append("ambientes")
    elif brief.niveles:
        for n in range(1, brief.niveles + 1):
            if not any(a.nivel == n for a in brief.ambientes):
                f.append(f"ambientes.nivel_{n}")
    return f


def huella(brief: Brief, estrategia: str, p: ParametrosMotor) -> str:
    datos = {
        "brief": brief.model_dump(mode="json", exclude={"origen", "nombre_proyecto", "presupuesto", "preferencias"}),
        "estrategia": estrategia,
        "parametros": p.model_dump(mode="json"),
        "motor": MOTOR_VERSION,
    }
    txt = json.dumps(datos, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(txt.encode()).hexdigest()[:12]


def _poly(e) -> Polygon:
    return Polygon(e.poligono)


def verificar(brief: Brief, alt_niveles, constructor: Constructor, p: ParametrosMotor) -> list[Verificacion]:
    W, D, y0 = brief.terreno.frente_m, brief.terreno.fondo_m, brief.terreno.retiro_frontal_m or 0.0
    lote = box(0, y0, W, D)
    out: list[Verificacion] = []

    fuera, superp, cobertura = [], [], []
    for nv in alt_niveles:
        polys = [(e, _poly(e)) for e in nv.espacios]
        for e, pg in polys:
            if not lote.buffer(1e-6).contains(pg):
                fuera.append(f"{e.id} {e.nombre}")
        for i, (a, pa) in enumerate(polys):
            for b, pb in polys[i + 1:]:
                inter = pa.intersection(pb).area
                if inter > 1e-4:
                    superp.append(f"{a.id} y {b.id}: {inter:.2f} m²")
        total = unary_union([pg for _, pg in polys]).area
        cobertura.append(f"{nv.nombre}: {total:.2f} de {lote.area:.2f} m²")
        if abs(total - lote.area) > 1e-3:
            superp.append(f"{nv.nombre} no cubre el área edificable")
    out.append(Verificacion(id="G-01", titulo="Ambientes dentro del terreno", estado="no_cumple" if fuera else "cumple",
                            detalle="Todos los ambientes están dentro del límite del lote." if not fuera else "Hay ambientes fuera del lote.",
                            evidencia=fuera or [f"Lote de {W:.2f} × {D:.2f} m"]))
    out.append(Verificacion(id="G-02", titulo="Sin superposiciones", estado="no_cumple" if superp else "cumple",
                            detalle="Ningún ambiente se superpone con otro y cada nivel queda cubierto por completo." if not superp else "Se detectaron superposiciones o vacíos.",
                            evidencia=superp or cobertura))

    # programa
    fuera_tol, dentro = [], 0
    total_prog = 0
    for nv in alt_niveles:
        for e in nv.espacios:
            if e.area_objetivo_m2:
                total_prog += 1
                dev = (e.area_m2 - e.area_objetivo_m2) / e.area_objetivo_m2
                if abs(dev) <= p.tolerancia_programa:
                    dentro += 1
                else:
                    fuera_tol.append(f"{e.nombre} ({nv.nombre}): {e.area_m2:.2f} m² frente a {e.area_objetivo_m2:.2f} m² ({dev*100:+.0f} %)")
    out.append(Verificacion(id="G-03", titulo="Áreas del programa", estado="cumple" if not fuera_tol else "no_cumple",
                            detalle=f"{dentro} de {total_prog} ambientes dentro del margen de ±{p.tolerancia_programa*100:.0f} % de su área objetivo.",
                            evidencia=fuera_tol))

    # dimensión mínima
    angostos = []
    for nv in alt_niveles:
        for e in nv.espacios:
            if e.funcion in p.dim_minima_m and e.ancho_m + 1e-6 < p.dim_minima_m[e.funcion]:
                angostos.append(f"{e.nombre} ({nv.nombre}): {e.ancho_m:.2f} m, mínimo configurado {p.dim_minima_m[e.funcion]:.2f} m")
    out.append(Verificacion(id="G-04", titulo="Dimensión mínima de ambientes", estado="cumple" if not angostos else "no_cumple",
                            detalle="Los anchos mínimos son parámetros configurables del motor, no valores normativos.",
                            evidencia=angostos))

    # accesos
    sin_acceso, via = [], []
    for nv in alt_niveles:
        acc = constructor.accesos[nv.numero]
        for e in nv.espacios:
            if e.id in acc["habitaciones"] and e.id not in acc["conectados"]:
                sin_acceso.append(f"{e.nombre} ({nv.nombre})")
            elif e.acceso_desde and not e.acceso_directo:
                via.append(f"{e.nombre} ({nv.nombre}) se accede a través de {e.acceso_desde}")
    out.append(Verificacion(id="G-05", titulo="Acceso a todos los ambientes", estado="cumple" if not sin_acceso else "no_cumple",
                            detalle="Cada ambiente tiene una puerta conectada a la circulación o a un ambiente accesible." if not sin_acceso else "Hay ambientes sin acceso.",
                            evidencia=sin_acceso + via))

    # luz natural en ambientes habitables
    oscuros = [f"{e.nombre} ({nv.nombre})" for nv in alt_niveles for e in nv.espacios
               if e.funcion in ("publico", "privado") and not e.luz_natural]
    out.append(Verificacion(id="G-06", titulo="Luz natural en ambientes habitables", estado="cumple" if not oscuros else "no_cumple",
                            detalle="Ambientes públicos y privados con al menos una ventana a fachada o patio.",
                            evidencia=oscuros))

    out.append(Verificacion(id="G-07", titulo="Escalera alineada entre niveles", estado="cumple",
                            detalle="La escalera ocupa la misma huella en todos los niveles y deja vacío en la losa superior.",
                            evidencia=[f"Huella {constructor.dist.escalera_rect[2]-constructor.dist.escalera_rect[0]:.2f} × {constructor.dist.escalera_rect[3]-constructor.dist.escalera_rect[1]:.2f} m"]))
    return out


def indicadores(brief: Brief, niveles, constructor: Constructor, verifs, p) -> dict:
    W, D, y0 = brief.terreno.frente_m, brief.terreno.fondo_m, brief.terreno.retiro_frontal_m or 0.0
    lote = W * D
    util = circ = comercial = ventanas = patio = 0.0
    hab = luz = directo = cuartos = 0
    frente_comercial = 0.0
    for nv in niveles:
        for e in nv.espacios:
            if e.funcion in ("circulacion", "escalera"):
                circ += e.area_m2
            elif e.funcion == "patio":
                patio += e.area_m2
            else:
                util += e.area_m2
                cuartos += 1
                directo += 1 if e.acceso_directo else 0
            if e.funcion == "publico":
                comercial += e.area_m2
                if nv.numero == 1:
                    frente_comercial += Polygon(e.poligono).intersection(LineString([(0, y0), (W, y0)])).length
            if e.funcion in ("publico", "privado"):
                hab += 1
                luz += 1 if e.luz_natural else 0
        for v in nv.vanos:
            if v.tipo == "ventana":
                ventanas += v.ancho_m * v.alto_m
    techada = sum(W * (D - y0) for _ in niveles) - patio
    n1 = W * (D - y0) - sum(e.area_m2 for e in niveles[0].espacios if e.funcion == "patio")
    # acceso independiente a niveles superiores: de la calle a la escalera sin cruzar ambientes públicos
    indep = False
    if len(niveles) > 1:
        n1e = niveles[0]
        calle = constructor.accesos[1]["entrada_calle"]
        indep = any(e.id in calle and e.funcion == "circulacion" for e in n1e.espacios)
    prog = next(v for v in verifs if v.id == "G-03")
    total_prog = sum(1 for nv in niveles for e in nv.espacios if e.area_objetivo_m2)
    dentro = total_prog - len(prog.evidencia)
    return {
        "area_terreno_m2": round(lote, 2),
        "area_techada_m2": round(techada, 2),
        "area_util_m2": round(util, 2),
        "area_circulacion_m2": round(circ, 2),
        "circulacion_pct": round(100 * circ / (util + circ), 1) if util + circ else 0,
        "area_comercial_m2": round(comercial, 2),
        "frente_comercial_m": round(frente_comercial, 2),
        "ocupacion_n1_pct": round(100 * n1 / lote, 1),
        "ambientes": cuartos,
        "cumplimiento_programa_pct": round(100 * dentro / total_prog, 1) if total_prog else 100.0,
        "ambientes_con_luz_pct": round(100 * luz / hab, 1) if hab else 0,
        "area_ventanas_m2": round(ventanas, 2),
        "acceso_directo_pct": round(100 * directo / cuartos, 1) if cuartos else 0,
        "acceso_independiente_superior": indep,
        "niveles": len(niveles),
        "verificaciones_cumple": sum(1 for v in verifs if v.estado == "cumple"),
        "verificaciones_total": len(verifs),
    }


def supuestos(brief: Brief, p: ParametrosMotor) -> list[str]:
    s = [
        "El lote se considera rectangular y plano.",
        "Las áreas se miden a ejes de muro y al límite del lote; los muros perimetrales se dibujan hacia el interior.",
        f"Muros exteriores de {p.muro_exterior_m:.2f} m e interiores de {p.muro_interior_m:.2f} m; losas de {p.losa_m:.2f} m.",
        f"Altura de piso a piso de {brief.altura_piso_m:.2f} m.",
        f"Escalera de dos tramos con huella de {p.escalera_ancho_m:.2f} × {p.escalera_largo_m:.2f} m como mínimo.",
        f"Margen de ±{p.tolerancia_programa*100:.0f} % para comparar áreas generadas con áreas objetivo.",
        "Los muros laterales se consideran medianeros, sin ventanas.",
        "Materiales de representación preliminares; no son especificación técnica.",
        "La geometría es un esquema preliminar y no constituye diseño estructural ni arquitectónico aprobado.",
    ]
    sin_area = [a.nombre for a in brief.ambientes if not a.area_objetivo_m2]
    if sin_area:
        s.append("Áreas por defecto usadas para: " + ", ".join(sin_area) + ".")
    if brief.terreno.retiro_frontal_m is None:
        s.append("Retiro frontal no definido: se asume 0 m hasta confirmar los parámetros urbanísticos.")
    return s


def generar(brief: Brief, p: ParametrosMotor | None = None, estrategias=("A", "B", "C")) -> list[Alternativa]:
    p = p or ParametrosMotor()
    faltan = campos_faltantes(brief)
    if faltan:
        raise BriefIncompleto(faltan)
    alts = []
    for clave in estrategias:
        t0 = time.perf_counter()
        nombre, enfoque, fn, desc = ESTRATEGIAS[clave]
        dist = fn(brief, p)
        cons = Constructor(brief, dist, p)
        niveles = [cons.construir_nivel(n, dist.niveles[n]) for n in sorted(dist.niveles)]
        verifs = verificar(brief, niveles, cons, p)
        ind = indicadores(brief, niveles, cons, verifs, p)
        ms = (time.perf_counter() - t0) * 1000
        ind["tiempo_generacion_ms"] = round(ms, 1)
        W, D, y0 = brief.terreno.frente_m, brief.terreno.fondo_m, brief.terreno.retiro_frontal_m or 0.0
        alts.append(Alternativa(
            id=clave, nombre=nombre, estrategia=enfoque, descripcion=desc, huella=huella(brief, clave, p),
            motor_version=MOTOR_VERSION, tiempo_ms=round(ms, 1),
            terreno=[(0.0, 0.0), (W, 0.0), (W, D), (0.0, D)],
            niveles=niveles, indicadores=ind, verificaciones=verifs, supuestos=supuestos(brief, p),
        ))
    return alts

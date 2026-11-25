"""Estrategias de distribución por franjas sobre un lote rectangular.

Ejes: x a lo ancho del frente (0 → frente), y hacia el fondo (0 = fachada principal).
Cada estrategia devuelve, por nivel, una lista de celdas rectangulares que
cubren exactamente el área edificable del nivel. Las celdas se convierten luego
en espacios, muros, vanos y losas.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from .modelos import Ambiente, Brief, ParametrosMotor

Rect = tuple[float, float, float, float]  # x0, y0, x1, y1

FUNCIONES_CIRCULACION = {"circulacion", "escalera"}


@dataclass
class Celda:
    nombre: str
    funcion: str  # publico | privado | servicio | circulacion | escalera | patio
    rect: Rect
    area_objetivo: Optional[float] = None
    orden: int = 0
    extra: dict = field(default_factory=dict)

    @property
    def area(self) -> float:
        x0, y0, x1, y1 = self.rect
        return (x1 - x0) * (y1 - y0)


@dataclass
class Distribucion:
    estrategia: str
    niveles: dict[int, list[Celda]]
    escalera_rect: Rect
    escalera_entrada: str  # lado por donde se entra a la escalera: "y0" o "x0"
    patio_rect: Optional[Rect] = None
    notas: list[str] = field(default_factory=list)


def _r(v: float) -> float:
    return round(v, 4)


def area_de(amb: Ambiente, p: ParametrosMotor) -> float:
    return amb.area_objetivo_m2 if amb.area_objetivo_m2 else p.area_por_defecto_m2[amb.tipo]


def cortar_en_x(x0: float, x1: float, y0: float, y1: float, items: list[tuple[Ambiente, float]], p: ParametrosMotor, orden0: int = 0) -> list[Celda]:
    """Corta la franja en rectángulos con anchos proporcionales a las áreas objetivo."""
    if not items:
        return []
    total = sum(a for _, a in items)
    ancho = x1 - x0
    celdas: list[Celda] = []
    x = x0
    for i, (amb, a) in enumerate(items):
        xf = x1 if i == len(items) - 1 else x + ancho * a / total
        celdas.append(Celda(amb.nombre, amb.tipo, (_r(x), _r(y0), _r(xf), _r(y1)), amb.area_objetivo_m2 or None, orden0 + i, {"ambiente": amb}))
        x = xf
    return celdas


def llenar_zona(zona: Rect, lado_circ: str, items: list[Ambiente], p: ParametrosMotor, orden0: int = 0,
                nombre_vestibulo: str = "Vestíbulo", lejano_fachada: bool = False) -> list[Celda]:
    """Llena una zona rectangular con ambientes cuidando sus proporciones.

    Los ambientes grandes se cortan a lo ancho y ocupan la zona desde la cara
    opuesta a la circulación (normalmente la fachada). Los pequeños, que en un
    corte simple quedarían como franjas muy angostas, se agrupan en una fila
    pegada a la circulación; si la fila no se completa, el resto queda como
    vestíbulo de circulación.
    """
    if not items:
        return []
    X0, Y0, X1, Y1 = zona
    if lado_circ in ("y0", "y1"):
        largo_u, prof = X1 - X0, Y1 - Y0
    else:
        largo_u, prof = Y1 - Y0, X1 - X0

    def a_global(u0, u1, v0, v1) -> Rect:
        if lado_circ == "y1":
            r = (X0 + u0, Y1 - v1, X0 + u1, Y1 - v0)
        elif lado_circ == "y0":
            r = (X0 + u0, Y0 + v0, X0 + u1, Y0 + v1)
        elif lado_circ == "x0":
            r = (X0 + v0, Y0 + u0, X0 + v1, Y0 + u1)
        else:
            r = (X1 - v1, Y0 + u0, X1 - v0, Y0 + u1)
        return tuple(_r(v) for v in r)  # type: ignore

    areas = [(a, area_de(a, p)) for a in items]
    total = sum(x[1] for x in areas)
    escala = (largo_u * prof) / total
    # pequeños: los que cortados a lo ancho quedarían más angostos que su mínimo
    def minimo(a):
        return p.dim_minima_m[a.tipo] if a.tipo == "servicio" else max(p.dim_minima_m[a.tipo], 2.4)
    grandes = [(a, s) for a, s in areas if s * escala / prof >= minimo(a)]
    pequenos = [(a, s) for a, s in areas if (a, s) not in grandes]
    if not grandes:
        mayor = max(areas, key=lambda x: x[1])
        grandes, pequenos = [mayor], [x for x in areas if x is not mayor]
    celdas: list[Celda] = []
    grupo = lambda a: f"{a.nivel}:{a.nombre}"  # noqa: E731
    ds = us = 0.0
    al_fondo = False
    if pequenos:
        suma_p = sum(s * escala for _, s in pequenos)
        ds = max(max(p.dim_minima_m[a.tipo] for a, _ in pequenos), min(4.0, prof * 0.45))
        ds = min(ds, prof * 0.45)
        # los privados pequeños van hacia la fachada para tener luz; el resto, junto a la circulación
        al_fondo = lejano_fachada and any(a.tipo == "privado" for a, _ in pequenos)
        reserva = 2.6 if al_fondo else 1.5  # tramo de fachada que conserva el ambiente grande
        if suma_p / ds > largo_u - reserva:
            ds = min(suma_p / (largo_u - reserva), prof - 1.5)
        v0, v1 = (prof - ds, prof) if al_fondo else (0, ds)
        u = 0.0
        for i, (a, s) in enumerate(pequenos):
            w = min(s * escala / ds, largo_u - u)
            celdas.append(Celda(a.nombre, a.tipo, a_global(u, u + w, v0, v1), a.area_objetivo_m2, orden0 + len(grandes) + i,
                                {"ambiente": a, "grupo": grupo(a)}))
            u += w
        us = u
    # los grandes ocupan la región restante: la franja completa junto a la fila de pequeños (A)
    # y el rectángulo sobre esa fila (B). B se asigna a un ambiente de área parecida, o el
    # ambiente mayor lo incorpora y queda en forma de L.
    region = largo_u * prof - us * ds
    suma_g = sum(s for _, s in grandes)
    cuotas = {id(a): s / suma_g * region for a, s in grandes}
    sobre = us * (prof - ds)
    bv0, bv1 = (0, prof - ds) if al_fondo else (ds, prof)
    solo_b = None
    if sobre > 0 and len(grandes) > 1:
        cand = min(grandes, key=lambda x: abs(cuotas[id(x[0])] - sobre))
        if abs(cuotas[id(cand[0])] - sobre) / cuotas[id(cand[0])] < 0.35:
            solo_b = cand
    if solo_b:
        a, s = solo_b
        celdas.append(Celda(a.nombre, a.tipo, a_global(0, us, bv0, bv1), a.area_objetivo_m2, orden0, {"ambiente": a, "grupo": grupo(a)}))
        resto = [g for g in grandes if g is not solo_b]
        anchos = [cuotas[id(a)] / prof for a, _ in resto]
        envuelve = False
    else:
        resto = grandes
        anchos = [max(1.0 if sobre > 0 else 0.0, (cuotas[id(resto[0][0])] - sobre) / prof)] + [cuotas[id(a)] / prof for a, _ in resto[1:]]
        envuelve = sobre > 0
    factor = (largo_u - us) / sum(anchos) if sum(anchos) > 0 else 1.0
    anchos = [w * factor for w in anchos]
    u = us
    for i, ((a, s), w) in enumerate(zip(resto, anchos)):
        uf = largo_u if i == len(resto) - 1 else u + w
        celdas.append(Celda(a.nombre, a.tipo, a_global(u, uf, 0, prof), a.area_objetivo_m2, orden0 + i, {"ambiente": a, "grupo": grupo(a)}))
        if i == 0 and envuelve:
            celdas.append(Celda(a.nombre, a.tipo, a_global(0, us, bv0, bv1), a.area_objetivo_m2, orden0 + i, {"ambiente": a, "grupo": grupo(a)}))
        u = uf
    return celdas


def separar_frente_fondo(ambs: list[Ambiente], capacidad_fondo: float, p: ParametrosMotor) -> tuple[list[Ambiente], list[Ambiente]]:
    """Servicios al fondo; si sobra capacidad, se mueven privados pequeños. Lo público siempre al frente."""
    fondo = [a for a in ambs if a.tipo == "servicio"]
    frente = [a for a in ambs if a.tipo != "servicio"]
    suma = sum(area_de(a, p) for a in fondo)
    principal = max(frente, key=lambda a: area_de(a, p)) if frente else None
    candidatos = sorted([a for a in frente if a is not principal], key=lambda a: (a.tipo == "publico", area_de(a, p)))
    while suma < 0.85 * capacidad_fondo and candidatos:
        c = candidatos.pop(0)
        if suma + area_de(c, p) <= 1.25 * capacidad_fondo:
            frente.remove(c)
            fondo.append(c)
            suma += area_de(c, p)
    if not frente and fondo:
        mayor = max(fondo, key=lambda a: area_de(a, p))
        fondo.remove(mayor)
        frente.append(mayor)
    # orden estable: público primero, luego privado por tamaño descendente
    frente.sort(key=lambda a: (0 if a.tipo == "publico" else 1, -area_de(a, p)))
    return frente, fondo


def _ambientes_por_nivel(brief: Brief) -> dict[int, list[Ambiente]]:
    niveles = brief.niveles or 1
    out: dict[int, list[Ambiente]] = {n: [] for n in range(1, niveles + 1)}
    for a in brief.ambientes:
        if a.nivel in out:
            out[a.nivel].append(a)
    return out


def _celda_vacia(nombre: str, x0, y0, x1, y1) -> Celda:
    return Celda(nombre, "privado", (_r(x0), _r(y0), _r(x1), _r(y1)), None, 99, {"por_asignar": True})


# ------------------------------------------------------------ estrategia A
def estrategia_a(brief: Brief, p: ParametrosMotor) -> Distribucion:
    """Franja comercial al frente, pasillo transversal, servicios y escalera al fondo."""
    W, D = brief.terreno.frente_m, brief.terreno.fondo_m
    y0 = brief.terreno.retiro_frontal_m or 0.0
    c, sw, sd = p.ancho_pasillo_m, p.escalera_ancho_m, p.escalera_largo_m
    Wb = W - sw
    por_nivel = _ambientes_por_nivel(brief)
    serv = max([sum(area_de(a, p) for a in v if a.tipo == "servicio") for v in por_nivel.values()] + [0])
    bd = max(sd, serv / Wb)
    bd = min(bd, max(sd, (D - y0) - c - 3.0))
    fd = (D - y0) - c - bd
    yf, yc, yb = y0 + fd, y0 + fd + c, D
    esc = (_r(Wb), _r(yc), _r(W), _r(yb))
    niveles: dict[int, list[Celda]] = {}
    for n, ambs in por_nivel.items():
        frente, fondo = separar_frente_fondo(ambs, Wb * bd, p)
        celdas = llenar_zona((0, y0, W, yf), "y1", frente, p, lejano_fachada=True)
        if not celdas:
            celdas.append(_celda_vacia("Área por asignar", 0, y0, W, yf))
        celdas.append(Celda("Hall de distribución" if n == 1 else f"Hall nivel {n}", "circulacion", (0, _r(yf), _r(W), _r(yc)), None, 50))
        cf = llenar_zona((0, yc, Wb, yb), "y0", fondo, p, 20, "Vestíbulo de servicio", lejano_fachada=True)
        celdas += cf or [_celda_vacia("Área por asignar", 0, yc, Wb, yb)]
        celdas.append(Celda("Escalera", "escalera", esc, None, 60))
        niveles[n] = celdas
    return Distribucion("A", niveles, esc, "y0")


# ------------------------------------------------------------ estrategia C
def estrategia_c(brief: Brief, p: ParametrosMotor) -> Distribucion:
    """Como A, con un patio de luz que atraviesa todos los niveles en la franja posterior."""
    W, D = brief.terreno.frente_m, brief.terreno.fondo_m
    y0 = brief.terreno.retiro_frontal_m or 0.0
    c, sw, sd = p.ancho_pasillo_m, p.escalera_ancho_m, p.escalera_largo_m
    Wb = W - sw
    por_nivel = _ambientes_por_nivel(brief)
    serv = max([sum(area_de(a, p) for a in v if a.tipo == "servicio") for v in por_nivel.values()] + [0])
    bd = max(sd, (serv + p.patio_area_objetivo_m2) / Wb)
    bd = min(bd, max(sd, (D - y0) - c - 3.0))
    fd = (D - y0) - c - bd
    yf, yc, yb = y0 + fd, y0 + fd + c, D
    pw = min(max(p.patio_area_objetivo_m2 / bd, 2.0), Wb * 0.5)
    esc = (0.0, _r(yc), _r(sw), _r(yb))
    # patio centrado en la franja posterior disponible
    px0 = sw + (Wb - pw) / 2
    patio = (_r(px0), _r(yc), _r(px0 + pw), _r(yb))
    niveles: dict[int, list[Celda]] = {}
    for n, ambs in por_nivel.items():
        frente, fondo = separar_frente_fondo(ambs, Wb * bd - pw * bd, p)
        celdas = llenar_zona((0, y0, W, yf), "y1", frente, p, lejano_fachada=True)
        if not celdas:
            celdas.append(_celda_vacia("Área por asignar", 0, y0, W, yf))
        celdas.append(Celda("Hall de distribución" if n == 1 else f"Hall nivel {n}", "circulacion", (0, _r(yf), _r(W), _r(yc)), None, 50))
        izq, der = [], []
        # reparto a cada lado del patio, equilibrando áreas
        for a in sorted(fondo, key=lambda a: -area_de(a, p)):
            (izq if sum(area_de(x, p) for x in izq) <= sum(area_de(x, p) for x in der) else der).append(a)
        izq.sort(key=lambda a: brief.ambientes.index(a))
        der.sort(key=lambda a: brief.ambientes.index(a))
        ci = llenar_zona((sw, yc, px0, yb), "y0", izq, p, 20, "Vestíbulo de servicio", lejano_fachada=True)
        cd = llenar_zona((px0 + pw, yc, W, yb), "y0", der, p, 30, "Vestíbulo de servicio", lejano_fachada=True)
        celdas += ci or [_celda_vacia("Área por asignar", sw, yc, px0, yb)]
        celdas += cd or [_celda_vacia("Área por asignar", px0 + pw, yc, W, yb)]
        celdas.append(Celda("Patio de luz" if n == 1 else "Vacío del patio de luz", "patio", patio, None, 70))
        celdas.append(Celda("Escalera", "escalera", esc, None, 60))
        niveles[n] = celdas
    return Distribucion("C", niveles, esc, "y0", patio_rect=patio)


# ------------------------------------------------------------ estrategia B
def estrategia_b(brief: Brief, p: ParametrosMotor) -> Distribucion:
    """Pasillo lateral continuo desde la fachada: acceso independiente a los niveles superiores."""
    W, D = brief.terreno.frente_m, brief.terreno.fondo_m
    y0 = brief.terreno.retiro_frontal_m or 0.0
    cl, sw, sd = p.ancho_pasillo_lateral_m, p.escalera_ancho_m, p.escalera_largo_m
    ws = W - cl
    wr = ws - sw
    por_nivel = _ambientes_por_nivel(brief)
    serv = max([sum(area_de(a, p) for a in v if a.tipo == "servicio") for v in por_nivel.values()] + [0])
    bd = max(sd, serv / wr)
    bd = min(bd, max(sd, (D - y0) - 4.0))
    ytop = D - bd
    esc = (_r(cl), _r(ytop), _r(cl + sw), _r(D))
    niveles: dict[int, list[Celda]] = {}
    for n, ambs in por_nivel.items():
        frente, fondo = separar_frente_fondo(ambs, wr * bd, p)
        celdas: list[Celda] = [Celda("Pasillo de acceso" if n == 1 else f"Pasillo nivel {n}", "circulacion", (0.0, _r(y0), _r(cl), _r(D)), None, 50)]
        celdas += llenar_zona((cl, y0, W, ytop), "x0", frente, p)
        if not frente:
            celdas.append(_celda_vacia("Área por asignar", cl, y0, W, ytop))
        cf = llenar_zona((cl + sw, ytop, W, D), "x0", fondo, p, 20, "Vestíbulo de servicio")
        celdas += cf or [_celda_vacia("Área por asignar", cl + sw, ytop, W, D)]
        celdas.append(Celda("Escalera", "escalera", esc, None, 60))
        niveles[n] = celdas
    return Distribucion("B", niveles, esc, "x0")


ESTRATEGIAS = {
    "A": ("Alternativa A", "Prioriza el área comercial", estrategia_a,
          "Franja frontal a todo el ancho para el uso principal, hall transversal y servicios con escalera al fondo."),
    "B": ("Alternativa B", "Prioriza la circulación", estrategia_b,
          "Pasillo lateral continuo desde la fachada que da acceso independiente a la escalera y a todos los ambientes."),
    "C": ("Alternativa C", "Prioriza la luz natural", estrategia_c,
          "Patio de luz que atraviesa todos los niveles en la franja posterior, con ventanas hacia el patio."),
}

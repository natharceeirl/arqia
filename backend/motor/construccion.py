"""Convierte las celdas de una distribución en elementos constructivos:
espacios, puertas, ventanas, muros, losas y escalera."""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Optional

from shapely.geometry import box as shp_box
from shapely.ops import unary_union

from .estrategias import FUNCIONES_CIRCULACION, Celda, Distribucion, Rect
from .modelos import Brief, Escalera, Espacio, Losa, Muro, Nivel, ParametrosMotor, Peldano, Vano

EPS = 1e-6
MATERIAL_MURO_EXT = "Albañilería (preliminar)"
MATERIAL_MURO_INT = "Albañilería (preliminar)"
MATERIAL_MURO_PATIO = "Albañilería (preliminar)"


def r3(v: float) -> float:
    return round(v + 0.0, 3)


def compartido(a: Rect, b: Rect) -> Optional[tuple[tuple[float, float], tuple[float, float]]]:
    """Segmento compartido entre dos rectángulos adyacentes, o None."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    # borde vertical compartido
    for xa in (ax0, ax1):
        for xb in (bx0, bx1):
            if abs(xa - xb) < 1e-4:
                lo, hi = max(ay0, by0), min(ay1, by1)
                if hi - lo > 1e-3 and not (abs(ax0 - bx0) < 1e-4 and abs(ax1 - bx1) < 1e-4):
                    if (xa == ax1 and xb == bx0) or (xa == ax0 and xb == bx1):
                        return ((xa, lo), (xa, hi))
    for ya in (ay0, ay1):
        for yb in (by0, by1):
            if abs(ya - yb) < 1e-4:
                lo, hi = max(ax0, bx0), min(ax1, bx1)
                if hi - lo > 1e-3:
                    if (ya == ay1 and yb == by0) or (ya == ay0 and yb == by1):
                        return ((lo, ya), (hi, ya))
    return None


def largo(seg) -> float:
    (x0, y0), (x1, y1) = seg
    return math.hypot(x1 - x0, y1 - y0)


def bordes(r: Rect):
    x0, y0, x1, y1 = r
    return {
        "y0": ((x0, y0), (x1, y0)),
        "y1": ((x0, y1), (x1, y1)),
        "x0": ((x0, y0), (x0, y1)),
        "x1": ((x1, y0), (x1, y1)),
    }


class Constructor:
    def __init__(self, brief: Brief, dist: Distribucion, p: ParametrosMotor):
        self.brief, self.dist, self.p = brief, dist, p
        self.W = brief.terreno.frente_m
        self.D = brief.terreno.fondo_m
        self.y0 = brief.terreno.retiro_frontal_m or 0.0
        self.H = brief.altura_piso_m
        self.accesos: dict[int, dict] = {}

    # ------------------------------------------------------------------
    def es_fachada(self, seg) -> Optional[str]:
        (x0, y0), (x1, y1) = seg
        if abs(y0 - y1) < EPS:
            if abs(y0 - self.y0) < 1e-4:
                return "frontal"
            if abs(y0 - self.D) < 1e-4:
                return "posterior"
        return None

    def en_limite(self, seg) -> bool:
        (x0, y0), (x1, y1) = seg
        if abs(x0 - x1) < EPS and (abs(x0) < 1e-4 or abs(x0 - self.W) < 1e-4):
            return True
        return self.es_fachada(seg) is not None

    # ------------------------------------------------------------------
    def construir_nivel(self, n: int, celdas: list[Celda]) -> Nivel:
        H = self.H
        cota = (n - 1) * H
        celdas = sorted(celdas, key=lambda c: c.orden)
        # grupos: un ambiente puede estar formado por varias celdas (forma en L)
        grupos: dict[str, list[Celda]] = {}
        gkey: dict[int, str] = {}
        for c in celdas:
            k = c.extra.get("grupo") or f"_{id(c)}"
            gkey[id(c)] = k
            grupos.setdefault(k, []).append(c)
        orden_g = list(grupos.keys())
        gid = {k: f"N{n}-SP-{i:03d}" for i, k in enumerate(orden_g, start=1)}
        ids = {id(c): gid[gkey[id(c)]] for c in celdas}
        g0 = {k: v[0] for k, v in grupos.items()}  # celda representativa

        # adyacencias entre grupos distintos
        ady: dict[str, list[tuple[str, tuple]]] = defaultdict(list)
        for i, a in enumerate(celdas):
            for b in celdas[i + 1:]:
                if gkey[id(a)] == gkey[id(b)]:
                    continue
                s = compartido(a.rect, b.rect)
                if s:
                    ady[gkey[id(a)]].append((gkey[id(b)], s))
                    ady[gkey[id(b)]].append((gkey[id(a)], s))

        vanos: list[Vano] = []
        puertas_en: list[tuple[tuple, float, str]] = []
        contador = {"PU": 0, "VE": 0}

        def nuevo_id(t):
            contador[t] += 1
            return f"N{n}-{t}-{contador[t]:03d}"

        def poner_puerta(seg, ancho, nombre, entre, alto=2.1):
            (x0, y0), (x1, y1) = seg
            L = largo(seg)
            ancho = min(ancho, max(0.7, L - 0.3))
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            vid = nuevo_id("PU")
            vanos.append(Vano(id=vid, tipo="puerta", nombre=nombre, muro_id="", centro=(r3(cx), r3(cy)),
                              ancho_m=r3(ancho), alto_m=alto, alfeizar_m=0.0, entre=entre))
            puertas_en.append((seg, ancho, vid))
            return vid

        fun = {k: g0[k].funcion for k in grupos}
        nom = {k: g0[k].nombre for k in grupos}
        es_circ = lambda k: fun[k] in FUNCIONES_CIRCULACION  # noqa: E731
        conectados: set[str] = {k for k in grupos if es_circ(k)}
        acceso: dict[str, tuple[bool, Optional[str]]] = {}
        entrada_calle: list[str] = []
        if n == 1:
            for k, cs in grupos.items():
                if fun[k] not in ("publico", "circulacion"):
                    continue
                segs = [seg for c in cs for seg in bordes(c.rect).values() if self.es_fachada(seg) == "frontal"]
                if segs:
                    seg = max(segs, key=largo)
                    pub = fun[k] == "publico"
                    poner_puerta(seg, 1.8 if pub else 1.2, "Ingreso principal" if pub else "Ingreso independiente",
                                 [gid[k], "exterior"], 2.4 if pub else 2.1)
                    entrada_calle.append(k)
        habit = [k for k in grupos if not es_circ(k) and fun[k] != "patio"]
        for k in habit:
            mejor = None
            for b, s in ady[k]:
                if es_circ(b) and largo(s) >= 0.9 and (mejor is None or largo(s) > largo(mejor[1])):
                    mejor = (b, s)
            if mejor:
                ancho = 1.2 if fun[k] == "publico" else (0.8 if fun[k] == "servicio" else 0.9)
                poner_puerta(mejor[1], ancho, f"Puerta {nom[k]}", [gid[k], gid[mejor[0]]])
                conectados.add(k)
                acceso[k] = (True, nom[mejor[0]])
        pendientes = [k for k in habit if k not in conectados]
        prioridad = {"publico": 0, "privado": 1, "servicio": 2}
        cambio = True
        while pendientes and cambio:
            cambio = False
            for k in list(pendientes):
                vecinos = [(b, s) for b, s in ady[k] if b in conectados and fun[b] in prioridad and largo(s) >= 0.9]
                if not vecinos:
                    continue
                b, s = sorted(vecinos, key=lambda v: (prioridad[fun[v[0]]], -largo(v[1])))[0]
                poner_puerta(s, 0.8 if fun[k] == "servicio" else 0.9, f"Puerta {nom[k]}", [gid[k], gid[b]])
                conectados.add(k)
                acceso[k] = (False, nom[b])
                pendientes.remove(k)
                cambio = True

        # luz natural y ventanas
        patios = [c for c in celdas if c.funcion == "patio"]
        luz: dict[str, bool] = {}
        for k, cs in grupos.items():
            if fun[k] == "patio":
                continue
            segs = []
            for c in cs:
                segs += [seg for seg in bordes(c.rect).values() if self.es_fachada(seg)]
                for pc in patios:
                    s = compartido(c.rect, pc.rect)
                    if s:
                        segs.append(s)
            con_ventana = False
            for seg in segs:
                frontal = self.es_fachada(seg) == "frontal"
                for (a, b) in self._tramos_libres(seg, puertas_en):
                    L = largo((a, b))
                    vitrina = fun[k] == "publico" and n == 1 and frontal
                    if L < (0.6 if vitrina else 1.0):
                        continue
                    if fun[k] == "servicio":
                        ancho, alto, alf = min(L - 0.4, 1.2), 0.6, 1.5
                    elif vitrina:
                        ancho, alto, alf = max(0.5, L - 0.2), 2.4, 0.3
                    elif es_circ(k):
                        ancho, alto, alf = min(L - 0.4, 1.2), 1.2, 1.0
                    else:
                        ancho, alto, alf = max(0.8, min(L - 0.6, L * 0.6)), 1.4, 0.9
                    cx, cy = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
                    etiqueta = "Vitrina" if vitrina else ("Ventana alta" if fun[k] == "servicio" else "Ventana")
                    vanos.append(Vano(id=nuevo_id("VE"), tipo="ventana", nombre=f"{etiqueta} {nom[k]}", muro_id="",
                                      centro=(r3(cx), r3(cy)), ancho_m=r3(ancho), alto_m=alto, alfeizar_m=alf, entre=[gid[k]]))
                    con_ventana = True
            luz[k] = con_ventana

        espacios: list[Espacio] = []
        for k in orden_g:
            cs = grupos[k]
            pg = unary_union([shp_box(*c.rect) for c in cs]).simplify(1e-6)
            coords = [(r3(x), r3(y)) for x, y in list(pg.exterior.coords)[:-1]]
            principal = max(cs, key=lambda c: c.area)
            x0, y0, x1, y1 = principal.rect
            bx0, by0, bx1, by1 = pg.bounds
            ad, desde = acceso.get(k, (es_circ(k), None))
            espacios.append(Espacio(
                id=gid[k], nombre=nom[k], funcion=fun[k], poligono=coords, area_m2=r3(pg.area),
                ancho_m=r3(min(x1 - x0, y1 - y0)), largo_m=r3(max(bx1 - bx0, by1 - by0)),
                area_objetivo_m2=g0[k].area_objetivo, luz_natural=luz.get(k, fun[k] == "patio"),
                acceso_directo=bool(ad), acceso_desde=desde,
            ))

        self.accesos[n] = {
            "conectados": {gid[k] for k in conectados},
            "habitaciones": {gid[k] for k in habit},
            "entrada_calle": [gid[k] for k in entrada_calle],
        }
        self._gkey = gkey
        muros = self._muros(n, celdas, ids, vanos)
        losas = self._losas(n, cota)
        escaleras = self._escalera(n, cota) if n < (self.brief.niveles or 1) else []
        return Nivel(numero=n, nombre=f"Nivel {n}", cota_m=r3(cota), altura_m=H, espacios=espacios,
                     muros=muros, vanos=vanos, losas=losas, escaleras=escaleras)

    # ------------------------------------------------------------------
    def _tramos_libres(self, seg, puertas_en):
        (ax, ay), (bx, by) = seg
        L = largo(seg)
        if L < EPS:
            return []
        ux, uy = (bx - ax) / L, (by - ay) / L
        ocupados = []
        for (s, ancho, _) in puertas_en:
            (sx0, sy0), (sx1, sy1) = s
            # puerta sobre la misma línea
            cx, cy = (sx0 + sx1) / 2, (sy0 + sy1) / 2
            dist_linea = abs((cx - ax) * uy - (cy - ay) * ux)
            if dist_linea > 1e-4:
                continue
            t = (cx - ax) * ux + (cy - ay) * uy
            if -ancho / 2 <= t <= L + ancho / 2:
                ocupados.append((t - ancho / 2 - 0.3, t + ancho / 2 + 0.3))
        ocupados.sort()
        libres, t = [], 0.3
        for o0, o1 in ocupados:
            if o0 > t:
                libres.append((t, o0))
            t = max(t, o1)
        if L - 0.3 > t:
            libres.append((t, L - 0.3))
        return [((ax + ux * t0, ay + uy * t0), (ax + ux * t1, ay + uy * t1)) for t0, t1 in libres if t1 - t0 > 0]

    def _muros(self, n, celdas, ids, vanos) -> list[Muro]:
        p, H = self.p, self.H
        segmentos = []  # (orientacion, coord, s0, s1, exterior, espacios)
        # muros entre celdas
        for i, a in enumerate(celdas):
            for b in celdas[i + 1:]:
                s = compartido(a.rect, b.rect)
                if not s:
                    continue
                if a.funcion in FUNCIONES_CIRCULACION and b.funcion in FUNCIONES_CIRCULACION:
                    continue  # circulación abierta
                if self._gkey[id(a)] == self._gkey[id(b)]:
                    continue  # mismo ambiente
                ext = "patio" in (a.funcion, b.funcion)
                segmentos.append(self._seg(s, ext, [ids[id(a)], ids[id(b)]]))
        # muros perimetrales
        for c in celdas:
            for lado, seg in bordes(c.rect).items():
                if self.en_limite(seg):
                    if c.funcion == "patio":
                        continue
                    segmentos.append(self._seg(seg, True, [ids[id(c)]], perimetral=True))
        # fusionar tramos colineales contiguos
        grupos = defaultdict(list)
        for s in segmentos:
            grupos[(s[0], round(s[1], 4), s[4], s[5])].append(s)
        muros: list[Muro] = []
        k = 0
        for (ori, coord, ext, per), lista in sorted(grupos.items()):
            lista.sort(key=lambda s: s[2])
            actual = None
            for s in lista:
                if actual and s[2] <= actual[1] + 1e-4:
                    actual = [actual[0], max(actual[1], s[3]), actual[2] | set(s[6])]
                else:
                    if actual:
                        muros.append(self._muro(n, k := k + 1, ori, coord, actual, ext, per))
                    actual = [s[2], s[3], set(s[6])]
            if actual:
                muros.append(self._muro(n, k := k + 1, ori, coord, actual, ext, per))
        # asignar vanos a muros y calcular piezas
        for v in vanos:
            for m in muros:
                if self._contiene(m, v.centro):
                    v.muro_id = m.id
                    break
        for m in muros:
            m.piezas = self._piezas(m, [v for v in vanos if v.muro_id == m.id])
        return muros

    def _seg(self, seg, ext, esp, perimetral=False):
        (x0, y0), (x1, y1) = seg
        if abs(x0 - x1) < EPS:
            return ("v", x0, min(y0, y1), max(y0, y1), ext, perimetral, esp)
        return ("h", y0, min(x0, x1), max(x0, x1), ext, perimetral, esp)

    def _muro(self, n, k, ori, coord, actual, ext, perimetral) -> Muro:
        p = self.p
        t = p.muro_exterior_m if ext else p.muro_interior_m
        c = coord
        if perimetral:  # el muro perimetral se dibuja hacia el interior del lote
            if ori == "v":
                c = coord + t / 2 if abs(coord) < 1e-4 else coord - t / 2
            else:
                c = coord + t / 2 if abs(coord - self.y0) < 1e-4 else coord - t / 2
        s0, s1 = actual[0], actual[1]
        a, b = ((c, s0), (c, s1)) if ori == "v" else ((s0, c), (s1, c))
        return Muro(id=f"N{n}-MU-{k:03d}", a=(r3(a[0]), r3(a[1])), b=(r3(b[0]), r3(b[1])), espesor_m=t,
                    altura_m=self.H, exterior=ext, material=MATERIAL_MURO_EXT if ext else MATERIAL_MURO_INT,
                    espacios=sorted(actual[2]), piezas=[])

    def _contiene(self, m: Muro, punto) -> bool:
        (ax, ay), (bx, by) = m.a, m.b
        px, py = punto
        tol = m.espesor_m / 2 + 0.2
        if abs(ax - bx) < EPS:
            return abs(px - ax) <= tol and min(ay, by) - 1e-3 <= py <= max(ay, by) + 1e-3
        return abs(py - ay) <= tol and min(ax, bx) - 1e-3 <= px <= max(ax, bx) + 1e-3

    def _piezas(self, m: Muro, vanos: list[Vano]):
        (ax, ay), (bx, by) = m.a, m.b
        L = math.hypot(bx - ax, by - ay)
        H = m.altura_m
        cortes = []
        for v in vanos:
            t = math.hypot(v.centro[0] - ax, v.centro[1] - ay)
            cortes.append((max(0, t - v.ancho_m / 2), min(L, t + v.ancho_m / 2), v.alfeizar_m, v.alfeizar_m + v.alto_m))
        cortes.sort()
        piezas, s = [], 0.0
        for c0, c1, z0, z1 in cortes:
            if c0 > s + 1e-3:
                piezas.append((r3(s), r3(c0), 0.0, H))
            if z0 > 1e-3:
                piezas.append((r3(c0), r3(c1), 0.0, r3(z0)))
            if z1 < H - 1e-3:
                piezas.append((r3(c0), r3(c1), r3(z1), H))
            s = max(s, c1)
        if L > s + 1e-3:
            piezas.append((r3(s), r3(L), 0.0, H))
        return piezas

    def _losas(self, n, cota) -> list[Losa]:
        p = self.p
        lote = [(0.0, self.y0), (self.W, self.y0), (self.W, self.D), (0.0, self.D)]
        lote_area = self.W * (self.D - self.y0)
        vacios = []
        if self.dist.patio_rect:
            x0, y0, x1, y1 = self.dist.patio_rect
            vacios.append([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
        if n > 1:
            x0, y0, x1, y1 = self.dist.escalera_rect
            vacios.append([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
        area = lote_area - sum((v[1][0] - v[0][0]) * (v[2][1] - v[1][1]) for v in vacios)
        losas = [Losa(id=f"N{n}-LO-001", nombre="Losa de piso" if n > 1 else "Losa de piso (contrapiso)",
                      poligono=lote, vacios=vacios, espesor_m=p.losa_m, cota_m=r3(cota), area_m2=r3(area))]
        if n == (self.brief.niveles or 1):
            vac = [v for v in vacios[:1]] if self.dist.patio_rect else []
            area_t = lote_area - sum((v[1][0] - v[0][0]) * (v[2][1] - v[1][1]) for v in vac)
            losas.append(Losa(id=f"N{n}-LO-002", nombre="Losa de techo", poligono=lote, vacios=vac,
                              espesor_m=p.losa_m, cota_m=r3(cota + self.H), area_m2=r3(area_t)))
        return losas

    def _escalera(self, n, cota) -> list[Escalera]:
        H = self.H
        x0, y0, x1, y1 = self.dist.escalera_rect
        num = math.ceil(H / 0.18)
        r = H / num
        paso = 0.28
        n1 = math.ceil(num / 2)
        n2 = num - n1
        mid = (x0 + x1) / 2
        peld = []
        for i in range(n1):
            peld.append(Peldano(x0=r3(x0), y0=r3(y0 + i * paso), x1=r3(mid), y1=r3(y0 + (i + 1) * paso),
                                z0=r3(cota), z1=r3(cota + (i + 1) * r)))
        yl = y0 + n1 * paso
        yl1 = min(y1, yl + 1.2)
        peld.append(Peldano(x0=r3(x0), y0=r3(yl), x1=r3(x1), y1=r3(yl1), z0=r3(cota), z1=r3(cota + n1 * r)))
        for j in range(n2):
            peld.append(Peldano(x0=r3(mid), y0=r3(yl - (j + 1) * paso), x1=r3(x1), y1=r3(yl - j * paso),
                                z0=r3(cota), z1=r3(cota + (n1 + j + 1) * r)))
        return [Escalera(id=f"ES-{n:03d}", nivel_desde=n, nivel_hasta=n + 1,
                         huella=[(x0, y0), (x1, y0), (x1, y1), (x0, y1)], peldanos=peld,
                         contrapaso_m=r3(r), paso_m=paso, numero_contrapasos=num)]

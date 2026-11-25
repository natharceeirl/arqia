"""Exportación de una alternativa de ARQIA a IFC4 con IfcOpenShell, y verificación del archivo."""
from __future__ import annotations

import logging
import math
import tempfile
import uuid
from collections import Counter
from pathlib import Path

import ifcopenshell
import ifcopenshell.api.aggregate
import ifcopenshell.api.context
import ifcopenshell.api.feature
import ifcopenshell.api.geometry
import ifcopenshell.api.material
import ifcopenshell.api.pset
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import ifcopenshell.api.unit
import ifcopenshell.guid
import ifcopenshell.validate
import numpy as np
from ifcopenshell.util.shape_builder import ShapeBuilder

from motor.modelos import Alternativa, Brief

NS = uuid.UUID("6f1c8f2e-3a51-4c58-9b1a-a51c0a0a7a10")


def _matriz(x, y, z, dx=1.0, dy=0.0):
    m = np.eye(4)
    n = math.hypot(dx, dy) or 1.0
    ux, uy = dx / n, dy / n
    m[0][0], m[1][0] = ux, uy
    m[0][1], m[1][1] = -uy, ux
    m[0][3], m[1][3], m[2][3] = x, y, z
    return m


class ExportadorIFC:
    def __init__(self, brief: Brief, alt: Alternativa, costos: dict | None = None):
        self.brief, self.alt, self.costos = brief, alt, costos
        self.f = ifcopenshell.api.root.create_entity  # alias corto
        self.m = ifcopenshell.file(schema="IFC4")
        self.sb = ShapeBuilder(self.m)

    def _crear(self, clase, nombre, clave, **kw):
        e = ifcopenshell.api.root.create_entity(self.m, ifc_class=clase, name=nombre, **kw)
        e.GlobalId = ifcopenshell.guid.compress(uuid.uuid5(NS, f"{self.alt.huella}:{clave}").hex)
        return e

    def _pset(self, prod, nombre, props):
        ps = ifcopenshell.api.pset.add_pset(self.m, product=prod, name=nombre)
        ifcopenshell.api.pset.edit_pset(self.m, pset=ps, properties=props)

    def _arqia(self, prod, ident, fuente="Motor paramétrico ARQIA"):
        self._pset(prod, "Pset_ARQIA", {
            "Identificador": ident, "Alternativa": self.alt.id, "Huella": self.alt.huella,
            "VersionMotor": self.alt.motor_version, "Fuente": fuente, "Estado": "Preliminar, requiere revisión profesional",
        })

    def _caja(self, prod, largo, alto, espesor, ctx):
        rep = ifcopenshell.api.geometry.add_wall_representation(self.m, context=ctx, length=largo, height=alto,
                                                                thickness=espesor, offset=-espesor / 2)
        ifcopenshell.api.geometry.assign_representation(self.m, product=prod, representation=rep)

    def _costos(self, proyecto):
        """Estimación de costos como IfcCostSchedule con un IfcCostItem por partida e ítem de cotización."""
        import ifcopenshell.api.control
        import ifcopenshell.api.cost
        m, c = self.m, self.costos
        moneda = ifcopenshell.api.unit.add_monetary_unit(m, currency="PEN")
        ifcopenshell.api.unit.assign_unit(m, units=[moneda])
        cron = ifcopenshell.api.cost.add_cost_schedule(m, name=f"Estimación referencial ARQIA, {self.alt.nombre}", predefined_type="ESTIMATE")
        fuente = c["fuente"]
        raiz = ifcopenshell.api.cost.add_cost_item(m, cost_schedule=cron)
        ifcopenshell.api.cost.edit_cost_item(m, cost_item=raiz, attributes={
            "Name": "Costo de construcción", "Identification": "ARQIA",
            "Description": f"{fuente['nombre']}. {fuente['vigencia']}. {fuente['naturaleza']}."[:255]})

        def item(padre, ident, nombre, monto, desc=""):
            it = ifcopenshell.api.cost.add_cost_item(m, cost_item=padre)
            ifcopenshell.api.cost.edit_cost_item(m, cost_item=it, attributes={"Name": nombre[:120], "Identification": ident, "Description": desc[:255]})
            v = ifcopenshell.api.cost.add_cost_value(m, parent=it)
            ifcopenshell.api.cost.edit_cost_value(m, cost_value=v, attributes={"AppliedValue": float(monto), "Name": "Monto (PEN)"})
            return it

        for p in c["por_partida"]:
            if not p["reemplazada"]:
                item(raiz, f"VUOE-{p['partida']}", f"{p['nombre']} (categoría {p['categoria']})", p["monto"],
                     f"{p['valor_m2']} soles por m² de área techada")
        for i in c["cotizacion"]:
            if i["incluir"]:
                item(raiz, f"COT-{i['id']}", i["descripcion"], i["subtotal"],
                     f"{i['cantidad']} {i['unidad']} a {i['precio_unitario']}; fuente: {i['fuente']}")
        if c["totales"].get("terreno"):
            item(raiz, "TERRENO", "Terreno (valor arancelario)", c["totales"]["terreno"], c["terreno"].get("fuente") or "")

    def exportar(self) -> bytes:
        m, alt, b = self.m, self.alt, self.brief
        proyecto = self._crear("IfcProject", b.nombre_proyecto, "proyecto")
        ifcopenshell.api.unit.assign_unit(m)
        modelo = ifcopenshell.api.context.add_context(m, context_type="Model")
        body = ifcopenshell.api.context.add_context(m, context_type="Model", context_identifier="Body",
                                                    target_view="MODEL_VIEW", parent=modelo)
        sitio = self._crear("IfcSite", "Terreno", "sitio")
        edif = self._crear("IfcBuilding", f"{b.tipo_proyecto or 'Edificación'} — {alt.nombre}", "edificio")
        ifcopenshell.api.aggregate.assign_object(m, relating_object=proyecto, products=[sitio])
        ifcopenshell.api.aggregate.assign_object(m, relating_object=sitio, products=[edif])
        for e in (sitio, edif):
            ifcopenshell.api.geometry.edit_object_placement(m, product=e, matrix=np.eye(4))
        self._pset(sitio, "Pset_ARQIA_Terreno", {
            "Frente": b.terreno.frente_m, "Fondo": b.terreno.fondo_m,
            "Ubicacion": ", ".join(x for x in [b.ubicacion.distrito, b.ubicacion.ciudad, b.ubicacion.pais] if x),
        })
        self._pset(edif, "Pset_ARQIA_Alternativa", {
            "Alternativa": alt.nombre, "Estrategia": alt.estrategia, "Huella": alt.huella,
            "Supuestos": " | ".join(alt.supuestos)[:2000],
        })

        mat_muro = ifcopenshell.api.material.add_material(m, name="Albañilería (preliminar)", category="brick")
        mat_losa = ifcopenshell.api.material.add_material(m, name="Concreto (preliminar)", category="concrete")
        mat_vidrio = ifcopenshell.api.material.add_material(m, name="Vidrio (preliminar)", category="glass")
        mat_madera = ifcopenshell.api.material.add_material(m, name="Madera (preliminar)", category="wood")

        muros_ifc, losas_ifc, puertas, ventanas = [], [], [], []
        for nv in alt.niveles:
            piso = self._crear("IfcBuildingStorey", nv.nombre, f"nivel-{nv.numero}")
            piso.Elevation = nv.cota_m
            ifcopenshell.api.aggregate.assign_object(m, relating_object=edif, products=[piso])
            ifcopenshell.api.geometry.edit_object_placement(m, product=piso, matrix=_matriz(0, 0, nv.cota_m))
            contenidos = []

            # espacios
            espacios = []
            for e in nv.espacios:
                sp = self._crear("IfcSpace", e.nombre, e.id)
                sp.LongName = e.nombre
                ifcopenshell.api.geometry.edit_object_placement(m, product=sp, matrix=_matriz(0, 0, nv.cota_m))
                rep = ifcopenshell.api.geometry.add_slab_representation(m, context=body, depth=nv.altura_m - 0.2,
                                                                        polyline=[tuple(p) for p in e.poligono])
                ifcopenshell.api.geometry.assign_representation(m, product=sp, representation=rep)
                self._pset(sp, "Pset_SpaceCommon", {"Reference": e.id, "IsExternal": e.funcion == "patio",
                                                     "PubliclyAccessible": e.funcion in ("publico", "circulacion")})
                qto = ifcopenshell.api.pset.add_qto(m, product=sp, name="Qto_SpaceBaseQuantities")
                ifcopenshell.api.pset.edit_qto(m, qto=qto, properties={"NetFloorArea": e.area_m2, "Height": nv.altura_m})
                self._arqia(sp, e.id)
                self._pset(sp, "Pset_ARQIA_Ambiente", {
                    "Funcion": e.funcion, "AreaObjetivo": e.area_objetivo_m2 or 0.0,
                    "LuzNatural": e.luz_natural, "AccesoDirecto": e.acceso_directo,
                })
                espacios.append(sp)
            ifcopenshell.api.aggregate.assign_object(m, relating_object=piso, products=espacios)

            # muros con vanos
            por_muro = {}
            for v in nv.vanos:
                por_muro.setdefault(v.muro_id, []).append(v)
            for mu in nv.muros:
                (ax, ay), (bx, by) = mu.a, mu.b
                L = math.hypot(bx - ax, by - ay)
                w = self._crear("IfcWall", f"Muro {'exterior' if mu.exterior else 'interior'} {mu.id}", mu.id,
                                predefined_type="STANDARD" if not mu.exterior else "SOLIDWALL")
                ifcopenshell.api.geometry.edit_object_placement(m, product=w, matrix=_matriz(ax, ay, nv.cota_m, bx - ax, by - ay))
                self._caja(w, L, mu.altura_m, mu.espesor_m, body)
                ifcopenshell.api.material.assign_material(m, products=[w], material=mat_muro)
                self._pset(w, "Pset_WallCommon", {"IsExternal": mu.exterior, "Reference": mu.id, "LoadBearing": False})
                self._arqia(w, mu.id)
                contenidos.append(w)
                muros_ifc.append(w)
                for v in por_muro.get(mu.id, []):
                    s = math.hypot(v.centro[0] - ax, v.centro[1] - ay)
                    ux, uy = (bx - ax) / L, (by - ay) / L
                    x0, y0 = ax + ux * (s - v.ancho_m / 2), ay + uy * (s - v.ancho_m / 2)
                    op = self._crear("IfcOpeningElement", f"Vano {v.id}", f"vano-{v.id}")
                    ifcopenshell.api.geometry.edit_object_placement(
                        m, product=op, matrix=_matriz(x0, y0, nv.cota_m + v.alfeizar_m, ux, uy))
                    self._caja(op, v.ancho_m, v.alto_m, mu.espesor_m + 0.1, body)
                    ifcopenshell.api.feature.add_feature(m, feature=op, element=w)
                    clase = "IfcDoor" if v.tipo == "puerta" else "IfcWindow"
                    el = self._crear(clase, v.nombre, v.id)
                    el.OverallWidth, el.OverallHeight = v.ancho_m, v.alto_m
                    ifcopenshell.api.geometry.edit_object_placement(
                        m, product=el, matrix=_matriz(x0, y0, nv.cota_m + v.alfeizar_m, ux, uy))
                    self._caja(el, v.ancho_m, v.alto_m, 0.05, body)
                    ifcopenshell.api.material.assign_material(m, products=[el], material=mat_madera if v.tipo == "puerta" else mat_vidrio)
                    ifcopenshell.api.feature.add_filling(m, opening=op, element=el)
                    self._arqia(el, v.id)
                    contenidos.append(el)
                    (puertas if v.tipo == "puerta" else ventanas).append(el)

            # losas
            for lo in nv.losas:
                s = self._crear("IfcSlab", lo.nombre, lo.id, predefined_type="ROOF" if "techo" in lo.nombre.lower() else "FLOOR")
                ifcopenshell.api.geometry.edit_object_placement(m, product=s, matrix=_matriz(0, 0, lo.cota_m - lo.espesor_m))
                rep = ifcopenshell.api.geometry.add_slab_representation(m, context=body, depth=lo.espesor_m,
                                                                        polyline=[tuple(p) for p in lo.poligono])
                ifcopenshell.api.geometry.assign_representation(m, product=s, representation=rep)
                ifcopenshell.api.material.assign_material(m, products=[s], material=mat_losa)
                for i, vac in enumerate(lo.vacios):
                    op = self._crear("IfcOpeningElement", f"Vacío {lo.id}-{i+1}", f"vacio-{lo.id}-{i}")
                    ifcopenshell.api.geometry.edit_object_placement(m, product=op, matrix=_matriz(0, 0, lo.cota_m - lo.espesor_m - 0.05))
                    r2 = ifcopenshell.api.geometry.add_slab_representation(m, context=body, depth=lo.espesor_m + 0.1,
                                                                           polyline=[tuple(p) for p in vac])
                    ifcopenshell.api.geometry.assign_representation(m, product=op, representation=r2)
                    ifcopenshell.api.feature.add_feature(m, feature=op, element=s)
                self._pset(s, "Pset_SlabCommon", {"Reference": lo.id, "IsExternal": "techo" in lo.nombre.lower()})
                self._arqia(s, lo.id)
                contenidos.append(s)
                losas_ifc.append(s)

            # escalera
            for es in nv.escaleras:
                st = self._crear("IfcStair", f"Escalera {es.id}", es.id, predefined_type="HALF_TURN_STAIR")
                ifcopenshell.api.geometry.edit_object_placement(m, product=st, matrix=np.eye(4))
                items = []
                for p in es.peldanos:
                    perfil = self.sb.rectangle(size=(p.x1 - p.x0, p.y1 - p.y0))
                    items.append(self.sb.extrude(perfil, magnitude=max(0.05, p.z1 - p.z0), position=(p.x0, p.y0, p.z0)))
                rep = self.sb.get_representation(body, items)
                ifcopenshell.api.geometry.assign_representation(m, product=st, representation=rep)
                ifcopenshell.api.material.assign_material(m, products=[st], material=mat_losa)
                self._pset(st, "Pset_StairCommon", {"Reference": es.id, "NumberOfRiser": es.numero_contrapasos,
                                                     "RiserHeight": es.contrapaso_m, "TreadLength": es.paso_m})
                self._arqia(st, es.id)
                contenidos.append(st)

            ifcopenshell.api.spatial.assign_container(m, relating_structure=piso, products=contenidos)

        if self.costos:
            self._costos(proyecto)

        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as tmp:
            ruta = tmp.name
        m.write(ruta)
        datos = Path(ruta).read_bytes()
        Path(ruta).unlink(missing_ok=True)
        return datos


def exportar_ifc(brief: Brief, alt: Alternativa, costos: dict | None = None) -> bytes:
    return ExportadorIFC(brief, alt, costos).exportar()


def verificar_ifc(datos: bytes, alt: Alternativa) -> dict:
    """Vuelve a abrir el archivo, lo valida contra el esquema y compara cantidades con el modelo."""
    with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as tmp:
        tmp.write(datos)
        ruta = tmp.name
    f = ifcopenshell.open(ruta)
    Path(ruta).unlink(missing_ok=True)

    errores: list[str] = []

    class Captura(logging.Handler):
        def emit(self, record):
            errores.append(record.getMessage()[:300])

    log = logging.getLogger("arqia.ifc.validacion")
    log.handlers = [Captura()]
    log.propagate = False
    log.setLevel(logging.ERROR)
    ifcopenshell.validate.validate(f, log)

    clases = ["IfcBuildingStorey", "IfcSpace", "IfcWall", "IfcSlab", "IfcDoor", "IfcWindow", "IfcOpeningElement", "IfcStair"]
    conteo = Counter({c: len(f.by_type(c)) for c in clases})
    esperado = {
        "IfcBuildingStorey": len(alt.niveles),
        "IfcSpace": sum(len(n.espacios) for n in alt.niveles),
        "IfcWall": sum(len(n.muros) for n in alt.niveles),
        "IfcSlab": sum(len(n.losas) for n in alt.niveles),
        "IfcDoor": sum(1 for n in alt.niveles for v in n.vanos if v.tipo == "puerta"),
        "IfcWindow": sum(1 for n in alt.niveles for v in n.vanos if v.tipo == "ventana"),
        "IfcStair": sum(len(n.escaleras) for n in alt.niveles),
    }
    import ifcopenshell.util.element as ue

    area_ifc = 0.0
    for sp in f.by_type("IfcSpace"):
        q = ue.get_psets(sp).get("Qto_SpaceBaseQuantities", {})
        area_ifc += float(q.get("NetFloorArea", 0.0))
    area_modelo = sum(e.area_m2 for n in alt.niveles for e in n.espacios)
    coincide = all(conteo[k] == v for k, v in esperado.items()) and abs(area_ifc - area_modelo) < 0.05
    return {
        "esquema": f.schema,
        "valido": not errores,
        "errores": errores[:20],
        "elementos": dict(conteo),
        "esperado": esperado,
        "area_espacios_ifc_m2": round(area_ifc, 2),
        "area_espacios_modelo_m2": round(area_modelo, 2),
        "coincide_con_modelo": coincide,
        "tamano_kb": round(len(datos) / 1024, 1),
    }

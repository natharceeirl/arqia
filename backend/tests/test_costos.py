import base64
import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from bim import paquete
from costos import EntradaCostos, ItemCotizacion, calcular, cantidades, valor
from costos.cotizacion import importar, numero
from motor import generar
from motor.modelos import Brief

DEMO = Path(__file__).resolve().parents[1] / "demo" / "brief_arequipa.json"


@pytest.fixture(scope="module")
def brief():
    return Brief(**json.loads(DEMO.read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def alts(brief):
    return generar(brief)


def test_costo_es_area_por_valor_oficial(alts):
    r = calcular(alts[0], EntradaCostos())
    m2 = sum(p["valor_m2"] for p in r["por_partida"])
    assert m2 == pytest.approx(991.07, abs=0.01)  # C, C, D, D, F, D, D del cuadro de noviembre de 2026
    assert r["totales"]["vuoe"] == pytest.approx(400 * 991.07, abs=0.05)
    assert sum(e["costo"] for e in r["espacios"]) == pytest.approx(r["totales"]["vuoe"], abs=0.5)


def test_material_por_ambiente_cambia_solo_ese_ambiente(alts):
    base = calcular(alts[0], EntradaCostos())
    otro = calcular(alts[0], EntradaCostos(por_ambiente={"1:Tienda": {"pisos": "A"}}))
    tienda = next(e for e in otro["espacios"] if e["nombre"] == "Tienda")
    dif = (valor("pisos", "A") - valor("pisos", "D")) * tienda["area_m2"]
    assert otro["totales"]["vuoe"] - base["totales"]["vuoe"] == pytest.approx(dif, abs=0.05)


def test_cotizacion_reemplaza_partida_con_cantidad_del_modelo(alts):
    q = cantidades(alts[0])
    e = EntradaCostos(cotizacion=[ItemCotizacion(id="p", descripcion="Porcelanato 60x60", partida="pisos", unidad="m²", precio_unitario=80)],
                      reemplazos=["pisos"])
    r = calcular(alts[0], e)
    assert r["cotizacion"][0]["cantidad"] == q["piso_m2"]
    assert r["totales"]["construccion"] == pytest.approx(r["totales"]["vuoe"] - next(p["monto"] for p in r["por_partida"] if p["partida"] == "pisos") + 80 * q["piso_m2"], abs=0.05)


def test_terreno(alts):
    r = calcular(alts[0], EntradaCostos(terreno_valor_m2=500))
    assert r["totales"]["terreno"] == 100000
    assert r["totales"]["total"] == pytest.approx(r["totales"]["construccion"] + 100000, abs=0.01)


def test_numeros_en_formatos_locales():
    assert numero("S/ 1,234.50") == 1234.5
    assert numero("1.234,50") == 1234.5
    assert numero("85") == 85
    assert numero("12,5") == 12.5


def test_importar_csv_y_excel():
    csv = "Descripción;Unidad;Cantidad;Precio unitario\nPorcelanato 60x60;m2;;85.50\nPuerta contraplacada;und;6;350\n".encode()
    r = importar("cotizacion.csv", csv)
    assert [i["partida"] for i in r["items"]] == ["pisos", "puertas_ventanas"]
    assert r["items"][0]["cantidad_origen"] == "modelo" and r["items"][1]["cantidad"] == 6
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["COTIZACIÓN FERRETERÍA"])
    ws.append(["Item", "Und", "Cant.", "P.U.", "Parcial"])
    ws.append(["Ladrillo King Kong", "mil", 3, 1200, 3600])
    ws.append(["Cemento portland tipo I", "bls", 50, None, 1450])
    buf = io.BytesIO()
    wb.save(buf)
    r = importar("cot.xlsx", buf.getvalue())
    assert r["items"][1]["precio_unitario"] == 29.0
    assert r["items"][0]["partida"] == "muros"


def test_paquete_ida_y_vuelta(brief, alts):
    res = calcular(alts[2], EntradaCostos())
    z = paquete.exportar(brief, alts, "C", res, {"decisiones": [{"fecha": "hoy", "texto": "Elige C"}]})
    datos = paquete.importar(z)
    assert datos["reproducible"] and datos["tiene_ifc"] and datos["alternativa_elegida"] == "C"
    assert datos["costos"]["resultado"]["totales"]["vuoe"] == res["totales"]["vuoe"]


def test_api_costos_y_paquete(brief, alts):
    c = TestClient(app)
    alt = alts[0].model_dump(mode="json")
    r = c.post("/api/costos/calcular", json={"alternativa": alt, "entrada": {"especificacion": {"pisos": "B"}}}).json()
    assert r["especificacion"]["pisos"] == "B"
    p = c.post("/api/paquete/exportar", json={"brief": brief.model_dump(mode="json"), "alternativas": [a.model_dump(mode="json") for a in alts], "elegida": "A"}).json()
    i = c.post("/api/paquete/importar", json={"nombre": p["nombre"], "base64": p["archivo_base64"]}).json()
    assert i["reproducible"]
    bad = c.post("/api/cotizacion/importar", json={"nombre": "x.doc", "base64": base64.b64encode(b"hola").decode()})
    assert bad.status_code == 422

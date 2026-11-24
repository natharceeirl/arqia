import json
from pathlib import Path

import pytest
from shapely.geometry import Polygon

from motor import BriefIncompleto, generar
from motor.modelos import Brief

DEMO = Path(__file__).resolve().parents[1] / "demo" / "brief_arequipa.json"


@pytest.fixture(scope="module")
def brief():
    return Brief(**json.loads(DEMO.read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def alternativas(brief):
    return generar(brief)


def test_tres_alternativas(alternativas):
    assert [a.id for a in alternativas] == ["A", "B", "C"]


def test_cada_nivel_cubre_el_lote_sin_superposiciones(alternativas):
    for alt in alternativas:
        for nv in alt.niveles:
            polys = [Polygon(e.poligono) for e in nv.espacios]
            assert sum(p.area for p in polys) == pytest.approx(200.0, abs=1e-3)
            for i, a in enumerate(polys):
                for b in polys[i + 1:]:
                    assert a.intersection(b).area < 1e-4


def test_verificaciones_geometricas_cumplen(alternativas):
    for alt in alternativas:
        estados = {v.id: v.estado for v in alt.verificaciones}
        assert estados["G-01"] == "cumple"
        assert estados["G-02"] == "cumple"
        assert estados["G-05"] == "cumple", alt.id
        assert estados["G-07"] == "cumple"


def test_escalera_alineada(alternativas):
    for alt in alternativas:
        huellas = {tuple(map(tuple, e.poligono)) for nv in alt.niveles for e in nv.espacios if e.funcion == "escalera"}
        assert len(huellas) == 1


def test_determinista(brief, alternativas):
    otra = generar(brief)
    for a, b in zip(alternativas, otra):
        assert a.huella == b.huella
        assert [e.model_dump() for nv in a.niveles for e in nv.espacios] == [e.model_dump() for nv in b.niveles for e in nv.espacios]


def test_cada_puerta_y_ventana_tiene_muro(alternativas):
    for alt in alternativas:
        for nv in alt.niveles:
            ids = {m.id for m in nv.muros}
            for v in nv.vanos:
                assert v.muro_id in ids, (alt.id, v.nombre)


def test_acceso_independiente_solo_en_b(alternativas):
    ind = {a.id: a.indicadores["acceso_independiente_superior"] for a in alternativas}
    assert ind == {"A": False, "B": True, "C": False}


def test_c_tiene_mas_ventanas_que_a(alternativas):
    a, _, c = alternativas
    assert c.indicadores["area_ventanas_m2"] > a.indicadores["area_ventanas_m2"]


def test_brief_incompleto():
    with pytest.raises(BriefIncompleto) as e:
        generar(Brief(tipo_proyecto="Local comercial"))
    assert "terreno.frente_m" in e.value.faltantes


def test_otros_lotes_no_rompen_el_motor(brief):
    for frente, fondo, niveles in [(8, 25, 2), (15, 30, 3), (12, 12, 1)]:
        b = brief.model_copy(deep=True)
        b.terreno.frente_m, b.terreno.fondo_m, b.niveles = frente, fondo, niveles
        if niveles == 3:
            b.ambientes += [a.model_copy(update={"nivel": 3}) for a in brief.ambientes if a.nivel == 2]
        if niveles == 1:
            b.ambientes = [a for a in brief.ambientes if a.nivel == 1]
        for alt in generar(b):
            estados = {v.id: v.estado for v in alt.verificaciones}
            assert estados["G-01"] == "cumple" and estados["G-02"] == "cumple"

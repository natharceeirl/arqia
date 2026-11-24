"""Prueba del bucle de la entrevista con un cliente simulado (sin llamar a la API real)."""
import sys
import types
from types import SimpleNamespace as NS

from ia import entrevista
from motor.modelos import Brief


class ClienteFalso:
    def __init__(self, *a, **k):
        self.llamadas = 0
        self.messages = self

    def create(self, **kw):
        self.llamadas += 1
        assert kw["tools"] and kw["messages"][0]["role"] == "user"
        if self.llamadas == 1:
            return NS(content=[
                NS(type="tool_use", id="t1", name="actualizar_brief",
                   input={"tipo_proyecto": "Local comercial", "niveles": 2, "distrito": "Sachaca", "contexto": ["campiña"]}),
                NS(type="tool_use", id="t2", name="mostrar_aviso", input={"ids": ["AV-CAMPINA", "INVENTADO"]}),
            ])
        return NS(content=[NS(type="tool_use", id="t3", name="preguntar",
                              input={"comentario": "Registré tu local de 2 niveles. El lote mide 37 m.",
                                     "pregunta": "¿Qué ambientes necesitas?", "opciones": []})])


def test_turno_con_herramientas(monkeypatch):
    falso = types.ModuleType("anthropic")
    falso.Anthropic = ClienteFalso
    monkeypatch.setitem(sys.modules, "anthropic", falso)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "prueba")
    r = entrevista.turno(Brief(), [], "Quiero un local comercial de dos pisos en Sachaca, cerca de la campiña", [])
    assert r["modo"] == "asistente"
    assert r["brief"]["tipo_proyecto"] == "Local comercial"
    assert r["brief"]["niveles"] == 2
    assert r["avisos_nuevos"] == ["AV-CAMPINA"]  # el aviso inventado se rechaza
    # la cifra 37 no está en ningún dato: el verificador descarta esa frase
    assert "37" not in (r["comentario"] or "")
    assert r["descartes_verificador"]
    assert r["pregunta"] == "¿Qué ambientes necesitas?"

"""Entrevista guiada de requerimientos.

El servidor sabe qué falta y qué tema toca; Claude formula la pregunta, interpreta la respuesta y
propone cambios al brief mediante herramientas que el servidor valida. Sin clave de API, la
entrevista funciona como formulario guiado con las mismas preguntas.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from pydantic import ValidationError

from motor.modelos import Ambiente, Brief
from reglas import avisos_activos

from .verificador import permitidos, verificar_texto

log = logging.getLogger("arqia.ia")

MODELO = os.environ.get("ARQIA_MODELO", "claude-sonnet-5-5")

TEMAS = [
    ("tipo", "Tipo de proyecto", ["tipo_proyecto"]),
    ("ubicacion", "Ubicación", ["ubicacion.distrito"]),
    ("programa", "Programa de ambientes", ["niveles", "ambientes"]),
    ("terreno", "Terreno y suelo", ["terreno.frente_m", "terreno.fondo_m", "terreno.estudio_suelos", "terreno.retiro_frontal_m"]),
    ("presupuesto", "Presupuesto", ["presupuesto.monto"]),
    ("preferencias", "Preferencias", ["preferencias.luz_natural"]),
    ("revision", "Revisión final", ["confirmado"]),
]

OBLIGATORIOS = {"tipo_proyecto", "terreno.frente_m", "terreno.fondo_m", "niveles", "ambientes"}

PREGUNTAS = {
    "tipo_proyecto": ("¿Qué tipo de proyecto quieres desarrollar?", "Con esto ARQIA elige las estrategias de distribución adecuadas.",
                      ["Local comercial", "Oficinas", "Restaurante", "Vivienda"], "texto"),
    "ubicacion.distrito": ("¿En qué distrito y ciudad está el terreno? Si está cerca de la campiña o en ladera, cuéntamelo.",
                           "La ubicación activa avisos sobre zonificación, suelos y sismicidad.", [], "texto"),
    "niveles": ("¿Cuántos niveles quieres construir?", "El motor mantiene la escalera alineada en todos los niveles.", ["1", "2", "3"], "numero"),
    "ambientes": ("¿Qué ambientes necesitas en cada nivel? Si conoces el área aproximada de alguno, indícala.",
                  "Si no conoces las áreas, ARQIA usa valores de referencia marcados como supuestos.", [], "ambientes"),
    "terreno.frente_m": ("¿Cuánto mide el frente del terreno, en metros?", "Se asume un lote rectangular.", [], "numero"),
    "terreno.fondo_m": ("¿Cuánto mide el fondo del terreno, en metros?", "Se asume un lote rectangular.", [], "numero"),
    "terreno.estudio_suelos": ("¿El terreno cuenta con un estudio de mecánica de suelos?",
                               "El estudio define la cimentación; ARQIA no puede deducirlo de la ubicación.",
                               ["Sí, ya lo tengo", "Todavía no", "No sé qué es"], "opciones"),
    "terreno.retiro_frontal_m": ("¿Conoces el retiro frontal que exige la municipalidad para tu lote?",
                                 "Figura en el certificado de parámetros urbanísticos.", ["No exige retiro", "No lo sé todavía"], "numero"),
    "presupuesto.monto": ("¿Tienes un presupuesto referencial en soles?", "Solo se usa como referencia; ARQIA no estima costos en esta versión.",
                          ["No lo sé todavía"], "numero"),
    "preferencias.luz_natural": ("¿Qué tan importante es la luz natural para ti?", "Influye en cuál alternativa se recomienda.",
                                 ["Alta", "Media", "Baja"], "opciones"),
    "confirmado": ("Revisa el resumen de la derecha. ¿Genero las alternativas?", "Puedes editar cualquier dato antes de continuar.",
                   ["Sí, generar alternativas", "Quiero cambiar algo"], "opciones"),
}


def _valor(brief: Brief, campo: str):
    obj: Any = brief
    for p in campo.split("."):
        obj = getattr(obj, p, None)
    return obj


def respondido(brief: Brief, campo: str) -> bool:
    if campo == "confirmado":
        return brief.origen.get("confirmado") == "usuario"
    if campo == "ambientes":
        n = brief.niveles or 0
        return bool(brief.ambientes) and all(any(a.nivel == k for a in brief.ambientes) for k in range(1, n + 1))
    v = _valor(brief, campo)
    return v is not None or campo in brief.origen


def estado(brief: Brief) -> dict:
    temas = []
    actual = None
    for clave, nombre, campos in TEMAS:
        falt = [c for c in campos if not respondido(brief, c)]
        completo = not falt
        temas.append({"id": clave, "nombre": nombre, "completo": completo, "faltan": falt})
        if not completo and actual is None:
            actual = clave
    faltan_oblig = [c for c in OBLIGATORIOS if not respondido(brief, c)]
    return {"temas": temas, "tema_actual": actual, "faltan_obligatorios": faltan_oblig,
            "listo_para_generar": not faltan_oblig and brief.origen.get("confirmado") == "usuario",
            "completos": sum(1 for t in temas if t["completo"]), "total": len(temas)}


def siguiente_campo(brief: Brief) -> str | None:
    for _, _, campos in TEMAS:
        for c in campos:
            if not respondido(brief, c):
                return c
    return None


# --------------------------------------------------------------- aplicar cambios

def aplicar(brief: Brief, cambios: dict) -> tuple[Brief, list[str]]:
    """Aplica un parche propuesto y lo valida. Devuelve el brief nuevo y los errores encontrados."""
    datos = brief.model_dump(mode="json")
    errores: list[str] = []
    origen = datos.setdefault("origen", {})
    fuente = cambios.get("origen", "usuario")
    mapa = {
        "tipo_proyecto": ("tipo_proyecto",), "nombre_proyecto": ("nombre_proyecto",),
        "distrito": ("ubicacion", "distrito"), "ciudad": ("ubicacion", "ciudad"),
        "frente_m": ("terreno", "frente_m"), "fondo_m": ("terreno", "fondo_m"),
        "retiro_frontal_m": ("terreno", "retiro_frontal_m"), "estudio_suelos": ("terreno", "estudio_suelos"),
        "niveles": ("niveles",), "altura_piso_m": ("altura_piso_m",),
        "presupuesto_soles": ("presupuesto", "monto"), "luz_natural": ("preferencias", "luz_natural"),
        "estilo": ("preferencias", "estilo"), "acceso_independiente_n2": ("preferencias", "acceso_independiente_n2"),
        "notas": ("preferencias", "notas"),
    }
    for k, ruta in mapa.items():
        if k in cambios and cambios[k] is not None:
            d = datos
            for p in ruta[:-1]:
                d = d.setdefault(p, {})
            d[ruta[-1]] = cambios[k]
            origen[".".join(ruta) if ruta[0] != "presupuesto" else "presupuesto.monto"] = fuente
    if cambios.get("contexto"):
        ctx = set(datos["ubicacion"].get("contexto") or [])
        ctx |= set(cambios["contexto"])
        datos["ubicacion"]["contexto"] = sorted(ctx)
    for q in cambios.get("ambientes_quitar") or []:
        datos["ambientes"] = [a for a in datos["ambientes"]
                              if not (a["nombre"].lower() == str(q.get("nombre", "")).lower() and a["nivel"] == q.get("nivel"))]
    for a in cambios.get("ambientes_agregar") or []:
        try:
            nuevo = Ambiente(**a).model_dump(mode="json")
        except ValidationError as e:
            errores.append(f"Ambiente no válido {a}: {e.errors()[0]['msg']}")
            continue
        datos["ambientes"] = [x for x in datos["ambientes"]
                              if not (x["nombre"].lower() == nuevo["nombre"].lower() and x["nivel"] == nuevo["nivel"])]
        datos["ambientes"].append(nuevo)
        if nuevo["area_objetivo_m2"]:
            origen[f"ambientes.{nuevo['nivel']}.{nuevo['nombre']}.area"] = fuente
    for c in cambios.get("desconocidos") or []:
        if c in {"terreno.retiro_frontal_m", "terreno.estudio_suelos", "presupuesto.monto", "preferencias.luz_natural", "ubicacion.distrito"}:
            origen[c] = "desconocido"
            if c == "terreno.estudio_suelos" and datos["terreno"].get("estudio_suelos") is None:
                datos["terreno"]["estudio_suelos"] = "desconoce"
    if cambios.get("confirmar"):
        origen["confirmado"] = "usuario"
    try:
        return Brief(**datos), errores
    except ValidationError as e:
        errores += [f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors()]
        return brief, errores


# --------------------------------------------------------------- herramientas para Claude

HERRAMIENTAS = [
    {
        "name": "actualizar_brief",
        "description": "Registra en el brief lo que el usuario acaba de decir. Solo valores que el usuario dijo; nunca inventes medidas ni áreas. Usa 'desconocidos' cuando el usuario diga que no sabe un dato.",
        "input_schema": {
            "type": "object",
            "properties": {
                "tipo_proyecto": {"type": "string"},
                "nombre_proyecto": {"type": "string"},
                "distrito": {"type": "string"},
                "ciudad": {"type": "string"},
                "contexto": {"type": "array", "items": {"type": "string"}, "description": "Entorno declarado: campiña, ladera, centro histórico, avenida principal…"},
                "frente_m": {"type": "number"},
                "fondo_m": {"type": "number"},
                "retiro_frontal_m": {"type": "number"},
                "estudio_suelos": {"type": "string", "enum": ["si", "no", "desconoce"]},
                "niveles": {"type": "integer", "minimum": 1, "maximum": 4},
                "altura_piso_m": {"type": "number"},
                "presupuesto_soles": {"type": "number"},
                "luz_natural": {"type": "string", "enum": ["baja", "media", "alta"]},
                "estilo": {"type": "string"},
                "acceso_independiente_n2": {"type": "boolean"},
                "notas": {"type": "string"},
                "ambientes_agregar": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "nombre": {"type": "string"},
                            "nivel": {"type": "integer"},
                            "tipo": {"type": "string", "enum": ["publico", "privado", "servicio"],
                                     "description": "publico: atención al cliente; privado: trabajo o estancia; servicio: baños, almacén, archivo, cocina"},
                            "area_objetivo_m2": {"type": ["number", "null"], "description": "Solo si el usuario la indicó"},
                        },
                        "required": ["nombre", "nivel", "tipo"],
                    },
                },
                "ambientes_quitar": {"type": "array", "items": {"type": "object", "properties": {"nombre": {"type": "string"}, "nivel": {"type": "integer"}}}},
                "desconocidos": {"type": "array", "items": {"type": "string", "enum": ["terreno.retiro_frontal_m", "terreno.estudio_suelos", "presupuesto.monto", "preferencias.luz_natural", "ubicacion.distrito"]}},
                "confirmar": {"type": "boolean", "description": "true solo si el usuario confirma que quiere generar las alternativas"},
            },
        },
    },
    {
        "name": "mostrar_aviso",
        "description": "Destaca avisos del lugar que el servidor activó, cuando sean pertinentes a lo que se está conversando.",
        "input_schema": {"type": "object", "properties": {"ids": {"type": "array", "items": {"type": "string"}}}, "required": ["ids"]},
    },
    {
        "name": "preguntar",
        "description": "Formula la siguiente pregunta al usuario. Termina tu turno con esta herramienta.",
        "input_schema": {
            "type": "object",
            "properties": {
                "comentario": {"type": "string", "description": "Una o dos frases breves sobre lo que registraste o un punto a considerar. Sin cifras que no estén en el brief."},
                "pregunta": {"type": "string", "description": "Una sola pregunta, clara y concreta."},
                "contexto": {"type": "string", "description": "Una línea que explique por qué importa la pregunta."},
                "opciones": {"type": "array", "items": {"type": "string"}, "maxItems": 4, "description": "De 2 a 4 respuestas rápidas, o vacío si la respuesta es libre."},
            },
            "required": ["pregunta"],
        },
    },
]

SISTEMA = """Eres el Asistente ARQIA, un asistente de arquitectura que entrevista a un cliente para preparar un brief de proyecto.
Hablas siempre en español, con frases cortas, tono profesional y cercano. Nunca menciones que eres Claude ni un modelo de lenguaje.

Cómo trabajas en cada turno:
1. Si el mensaje del usuario contiene datos, regístralos con actualizar_brief. Registra solo lo que el usuario dijo. Si dice que no sabe un dato opcional, usa 'desconocidos'.
2. Si hay avisos activos pertinentes al tema que se conversa y aún no se mostraron, usa mostrar_aviso con sus identificadores.
3. Responde solo mediante herramientas, nunca con texto suelto. Termina siempre con preguntar: una sola pregunta sobre el siguiente dato que falta (se te indica cuál), con 2 a 4 opciones rápidas cuando tenga sentido.

Reglas estrictas:
- No inventes medidas, áreas, costos ni resultados. Las áreas y la geometría las calcula el motor de ARQIA, no tú.
- No afirmes que algo cumple una norma. Puedes decir que un punto requiere revisión profesional.
- No des datos técnicos que no estén en los avisos activos o en el brief.
- Clasifica ambientes así: público = atención al cliente (tienda, recepción); privado = trabajo o estancia (oficinas, gerencia, sala de reuniones); servicio = baños, almacén, archivo, cocina.
- Cuando el usuario confirme, usa actualizar_brief con confirmar=true y pregunta si desea ver las alternativas."""


def _texto_estado(brief: Brief, st: dict, avisos: list[dict], mostrados: list[str]) -> str:
    campo = siguiente_campo(brief)
    return json.dumps({
        "brief": brief.model_dump(mode="json", exclude={"origen"}),
        "tema_actual": st["tema_actual"],
        "siguiente_dato": campo,
        "pregunta_sugerida": PREGUNTAS.get(campo, (None,))[0] if campo else None,
        "faltan_obligatorios": st["faltan_obligatorios"],
        "avisos_activos": [{"id": a["id"], "titulo": a["titulo"], "texto": a["texto"]} for a in avisos],
        "avisos_ya_mostrados": mostrados,
    }, ensure_ascii=False)


SERVICIO = ("baño", "bano", "ss.hh", "sshh", "servicio", "almac", "archivo", "deposito", "depósito", "cocina", "kitchen", "lavander", "cuarto de")
PUBLICO = ("tienda", "recepci", "caja", "venta", "exhib", "comedor", "salón", "salon", "atención", "atencion", "local")
NUM_RE = __import__("re").compile(r"(\d+(?:[.,]\d+)?)")


def _numeros(t: str) -> list[float]:
    return [float(x.replace(",", ".")) for x in NUM_RE.findall(t.replace(" 000", "000"))]


def _tipo(nombre: str) -> str:
    n = nombre.lower()
    if any(k in n for k in SERVICIO):
        return "servicio"
    if any(k in n for k in PUBLICO):
        return "publico"
    return "privado"


def interpretar(campo: str, texto: str) -> dict:
    """Interpreta de forma determinista la respuesta del modo formulario para el campo preguntado."""
    t = (texto or "").strip()
    tl = t.lower()
    nums = _numeros(t)
    no_se = any(k in tl for k in ("no sé", "no se", "no lo sé", "no lo se", "desconozco", "todavía no lo", "no tengo"))
    if campo == "tipo_proyecto":
        return {"tipo_proyecto": t[:60]}
    if campo == "ubicacion.distrito":
        partes = [p.strip() for p in t.split(",") if p.strip()]
        c: dict = {"distrito": partes[0][:40] if partes else t[:40]}
        if len(partes) > 1:
            c["ciudad"] = partes[1][:40]
        ctx = [k for k in ("campiña", "ladera", "centro histórico", "avenida") if k in tl or k.replace("ñ", "n") in tl]
        if ctx:
            c["contexto"] = ctx
            c["distrito"] = c["distrito"].split(" cerca")[0]
        return c
    if campo == "niveles" and nums:
        return {"niveles": int(nums[0])}
    if campo in ("terreno.frente_m", "terreno.fondo_m") and nums:
        if len(nums) >= 2:
            return {"frente_m": nums[0], "fondo_m": nums[1]}
        return {campo.split(".")[1]: nums[0]}
    if campo == "terreno.estudio_suelos":
        if tl.startswith("sí") or tl.startswith("si"):
            return {"estudio_suelos": "si"}
        if "qué es" in tl or "que es" in tl or no_se:
            return {"estudio_suelos": "desconoce", "desconocidos": ["terreno.estudio_suelos"]}
        return {"estudio_suelos": "no"}
    if campo == "terreno.retiro_frontal_m":
        if "no exige" in tl or "sin retiro" in tl:
            return {"retiro_frontal_m": 0}
        if nums and not no_se:
            return {"retiro_frontal_m": nums[0]}
        return {"desconocidos": ["terreno.retiro_frontal_m"]}
    if campo == "presupuesto.monto":
        if nums and not no_se:
            return {"presupuesto_soles": max(nums)}
        return {"desconocidos": ["presupuesto.monto"]}
    if campo == "preferencias.luz_natural":
        for k in ("alta", "media", "baja"):
            if k in tl:
                return {"luz_natural": k}
        return {"desconocidos": ["preferencias.luz_natural"]}
    if campo == "confirmado":
        return {"confirmar": tl.startswith("sí") or tl.startswith("si")}
    if campo == "ambientes":
        import re
        agregar = []
        nivel = 1
        for bloque in re.split(r"[;\n]", t):
            m = re.match(r"\s*(?:nivel|piso)?\s*(\d)\s*[:\-]\s*(.*)", bloque, re.I)
            if m:
                nivel, bloque = int(m.group(1)), m.group(2)
            for item in [x.strip() for x in re.split(r",| y ", bloque) if x.strip()]:
                n = _numeros(item)
                nombre = NUM_RE.sub("", item).replace("m2", "").replace("m²", "").strip(" .:-")
                if nombre:
                    agregar.append({"nombre": nombre[:1].upper() + nombre[1:60], "nivel": nivel, "tipo": _tipo(nombre),
                                    "area_objetivo_m2": n[0] if n else None})
        return {"ambientes_agregar": agregar} if agregar else {}
    return {}


def turno_formulario(brief: Brief, mostrados: list[str]) -> dict:
    """Turno sin IA: pregunta el siguiente dato con las opciones del banco de preguntas."""
    campo = siguiente_campo(brief)
    avisos = avisos_activos(brief)
    nuevos = [a["id"] for a in avisos if a["id"] not in mostrados]
    if campo is None:
        return {"comentario": "El brief está completo.", "pregunta": None, "contexto": None, "opciones": [], "campo": None,
                "tipo_entrada": None, "avisos_nuevos": nuevos}
    p, c, ops, tipo = PREGUNTAS[campo]
    return {"comentario": None, "pregunta": p, "contexto": c, "opciones": ops, "campo": campo, "tipo_entrada": tipo, "avisos_nuevos": nuevos}


def turno(brief: Brief, historial: list[dict], mensaje: str | None, mostrados: list[str]) -> dict:
    """Un turno de la entrevista con Claude. Si no hay clave de API, usa el modo formulario."""
    clave = os.environ.get("ANTHROPIC_API_KEY")
    if not clave:
        errores: list[str] = []
        if mensaje:
            campo = siguiente_campo(brief)
            if campo:
                brief, errores = aplicar(brief, interpretar(campo, mensaje))
        r = turno_formulario(brief, mostrados)
        r.update(modo="formulario", brief=brief.model_dump(mode="json"), errores=errores, estado=estado(brief),
                 avisos=avisos_activos(brief))
        return r
    if False:
        r = turno_formulario(brief, mostrados)
        r.update(modo="formulario", brief=brief.model_dump(mode="json"), errores=[], estado=estado(brief),
                 avisos=avisos_activos(brief))
        return r

    import anthropic

    cliente = anthropic.Anthropic(api_key=clave, timeout=30.0, max_retries=1)
    mensajes = []
    for h in historial[-12:]:
        rol = "user" if h.get("rol") == "usuario" else "assistant"
        if h.get("texto"):
            if mensajes and mensajes[-1]["role"] == rol:
                mensajes[-1]["content"] += "\n" + h["texto"]
            else:
                mensajes.append({"role": rol, "content": h["texto"]})
    avisos = avisos_activos(brief)
    actual = brief
    errores: list[str] = []
    destacados: list[str] = []
    pregunta: dict | None = None
    contenido_usuario = f"[Estado del brief]\n{_texto_estado(actual, estado(actual), avisos, mostrados)}\n\n[Mensaje del usuario]\n{mensaje or '(inicio de la entrevista)'}"
    if mensajes and mensajes[-1]["role"] == "user":
        mensajes[-1]["content"] += "\n" + contenido_usuario
    else:
        mensajes.append({"role": "user", "content": contenido_usuario})
    if mensajes[0]["role"] != "user":
        mensajes.insert(0, {"role": "user", "content": "(inicio)"})

    for _ in range(4):
        resp = cliente.messages.create(model=MODELO, max_tokens=1200, system=SISTEMA, tools=HERRAMIENTAS,
                                       tool_choice={"type": "auto"}, messages=mensajes)
        bloques = []
        for b in resp.content:
            if b.type == "text" and b.text:
                bloques.append({"type": "text", "text": b.text})
            elif b.type == "tool_use":
                bloques.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
        mensajes.append({"role": "assistant", "content": bloques})
        if not any(b["type"] == "tool_use" for b in bloques):
            # respondió solo con texto: se usa como pregunta (pasa por el verificador más abajo)
            texto = " ".join(b["text"] for b in bloques if b["type"] == "text").strip()
            if texto:
                pregunta = {"pregunta": texto, "opciones": []}
            break
        resultados = []
        for b in resp.content:
            if b.type != "tool_use":
                continue
            if b.name == "actualizar_brief":
                actual, errs = aplicar(actual, dict(b.input))
                errores += errs
                avisos = avisos_activos(actual)
                res = {"ok": not errs, "errores": errs, "estado": _texto_estado(actual, estado(actual), avisos, mostrados + destacados)}
            elif b.name == "mostrar_aviso":
                validos = {a["id"] for a in avisos}
                ok = [i for i in b.input.get("ids", []) if i in validos]
                destacados += [i for i in ok if i not in destacados]
                res = {"mostrados": ok, "rechazados": [i for i in b.input.get("ids", []) if i not in validos]}
            elif b.name == "preguntar":
                pregunta = dict(b.input)
                res = {"ok": True}
            else:
                res = {"error": "herramienta desconocida"}
            resultados.append({"type": "tool_result", "tool_use_id": b.id, "content": json.dumps(res, ensure_ascii=False)})
        if pregunta:
            break
        mensajes.append({"role": "user", "content": resultados})

    if not pregunta:
        r = turno_formulario(actual, mostrados + destacados)
        pregunta = {"comentario": r["comentario"], "pregunta": r["pregunta"], "contexto": r["contexto"], "opciones": r["opciones"]}

    # verificador de cifras sobre todo lo que el asistente dirá
    ok = permitidos(actual.model_dump(mode="json"), [h.get("texto") for h in historial], mensaje or "", avisos)
    descartes: list[str] = []
    for k in ("comentario", "pregunta", "contexto"):
        if pregunta.get(k):
            pregunta[k], f = verificar_texto(pregunta[k], ok)
            descartes += f
    if descartes:
        log.warning("Frases descartadas por el verificador: %s", descartes)
    campo = siguiente_campo(actual)
    return {
        "modo": "asistente",
        "comentario": pregunta.get("comentario"), "pregunta": pregunta.get("pregunta"),
        "contexto": pregunta.get("contexto"), "opciones": pregunta.get("opciones") or [],
        "campo": campo, "tipo_entrada": PREGUNTAS[campo][3] if campo else None,
        "avisos_nuevos": [i for i in destacados if i not in mostrados],
        "brief": actual.model_dump(mode="json"), "errores": errores, "descartes_verificador": descartes,
        "estado": estado(actual), "avisos": avisos,
    }

import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { fmt, useArqia } from "./store";
import type { Ambiente, Aviso, Brief, TipoAmbiente } from "./tipos";

const NOMBRE_TIPO: Record<TipoAmbiente, string> = { publico: "Público", privado: "Privado", servicio: "Servicio" };

export default function Entrevista() {
  const s = useArqia();
  const [texto, setTexto] = useState("");
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hiloRef = useRef<HTMLDivElement>(null);

  async function enviar(mensaje: string | null) {
    setCargando(true);
    setError(null);
    const historial = mensaje ? [...s.historial, { rol: "usuario" as const, texto: mensaje }] : s.historial;
    if (mensaje) s.set({ historial });
    try {
      const r = await api.turno(s.brief, s.historial, mensaje, s.avisosMostrados);
      const texto = [r.comentario, r.pregunta].filter(Boolean).join(" ");
      const nuevos = r.avisos_nuevos.length ? r.avisos_nuevos : r.avisos.map((a) => a.id).filter((id) => !s.avisosMostrados.includes(id));
      s.set({
        brief: r.brief, entrevista: r.estado, avisos: r.avisos, modo: r.modo,
        avisosMostrados: [...s.avisosMostrados, ...nuevos],
        pendiente: { pregunta: r.pregunta, opciones: r.opciones, campo: r.campo, tipo_entrada: r.tipo_entrada },
        historial: texto ? [...historial, { rol: "asistente", texto, opciones: r.opciones, avisos: nuevos, contexto: r.contexto }] : historial,
      });
      if (r.errores.length) setError(r.errores.join(" "));
    } catch (e) {
      setError(`No se pudo contactar al servidor. ${(e as Error).message}`);
    } finally {
      setCargando(false);
    }
  }

  useEffect(() => {
    if (!s.historial.length && !cargando) enviar(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    hiloRef.current?.scrollTo({ top: hiloRef.current.scrollHeight, behavior: "smooth" });
  }, [s.historial.length, cargando]);

  async function generar() {
    setCargando(true);
    setError(null);
    try {
      const r = await api.alternativas(s.brief);
      s.set({ brief: r.brief, alternativas: r.alternativas, avisos: r.avisos, activa: "A", nivel: 1, pantalla: "trabajo", seleccion: null, explicacion: null });
      s.decidir("Se generaron las alternativas A, B y C a partir del brief.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setCargando(false);
    }
  }

  const ultimo = s.historial[s.historial.length - 1];
  const est = s.entrevista;
  const puedeGenerar = !!est && est.faltan_obligatorios.length === 0;

  return (
    <div className="entrevista">
      <main className="conversa">
        <div className="temas">
          <span>Temas</span>
          {est?.temas.map((t) => (
            <span key={t.id} className={t.completo ? "hecho" : t.id === est.tema_actual ? "actual" : ""}>
              {t.completo ? "✓ " : ""}{t.nombre}
            </span>
          ))}
        </div>
        <div className="hilo" ref={hiloRef}>
          {s.historial.map((m, i) => {
            const esUltimo = m === ultimo && m.rol === "asistente";
            if (m.rol === "usuario")
              return (
                <div key={i} className="msg-tu"><span className="quien">Tú</span><p>{m.texto}</p></div>
              );
            return (
              <div key={i} className={`msg-ia ${esUltimo ? "actual" : ""}`}>
                <span className="quien">ARQIA</span>
                <p className={esUltimo ? "preg" : ""}>{m.texto}</p>
                {esUltimo && m.contexto && <p className="ctx">{m.contexto}</p>}
                {m.avisos && m.avisos.length > 0 && (
                  <p className="ctx">Agregué {m.avisos.length === 1 ? "un punto" : `${m.avisos.length} puntos`} a tener en cuenta en el resumen.</p>
                )}
                {esUltimo && m.opciones && m.opciones.length > 0 && !cargando && (
                  <div className="opciones">
                    {m.opciones.map((o) => <button key={o} onClick={() => (o.startsWith("Sí, generar") && puedeGenerar ? enviar(o).then(generar) : enviar(o))}>{o}</button>)}
                  </div>
                )}
              </div>
            );
          })}
          {cargando && <p className="pensando">ARQIA está procesando…</p>}
          {error && <p className="error">{error}</p>}
        </div>
        <form className="entrada" onSubmit={(e) => { e.preventDefault(); if (texto.trim()) { enviar(texto.trim()); setTexto(""); } }}>
          <label htmlFor="resp">
            {s.pendiente?.tipo_entrada === "ambientes"
              ? "Ejemplo: Nivel 1: tienda 120, almacén, baños; Nivel 2: oficinas, sala de reuniones"
              : "Responde con tus palabras"}
            {s.modo === "formulario" && " (modo formulario: el asistente con IA no está disponible)"}
          </label>
          <div className="fila">
            <textarea id="resp" rows={s.pendiente?.tipo_entrada === "ambientes" ? 3 : 1} value={texto} onChange={(e) => setTexto(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); (e.currentTarget.form as HTMLFormElement).requestSubmit(); } }}
              placeholder="Escribe tu respuesta…" disabled={cargando} />
            <button className="btn oscuro" disabled={cargando || !texto.trim()} style={{ minHeight: 44 }}>Enviar</button>
          </div>
        </form>
      </main>
      <Resumen onGenerar={generar} puedeGenerar={puedeGenerar} cargando={cargando} />
    </div>
  );
}

function Resumen({ onGenerar, puedeGenerar, cargando }: { onGenerar: () => void; puedeGenerar: boolean; cargando: boolean }) {
  const s = useArqia();
  const b = s.brief;
  const est = s.entrevista;
  const [editando, setEditando] = useState<string | null>(null);
  const pct = est ? (100 * est.completos) / est.total : 0;
  const origen = (k: string) => (b.origen[k] === "supuesto" ? "supuesto" : b.origen[k] === "desconocido" ? "por confirmar" : null);

  async function cambiar(cambios: Record<string, unknown>) {
    const r = await api.aplicar(b, cambios);
    s.set({ brief: r.brief, entrevista: r.estado, avisos: r.avisos });
    s.decidir(`Se editó el brief: ${Object.keys(cambios).join(", ")}.`);
  }

  return (
    <aside className="resumen">
      <div>
        <h2 style={{ margin: 0, fontSize: 17 }}>Resumen de la propuesta</h2>
        <p style={{ margin: "4px 0 0", fontSize: 13, color: "var(--texto-2)" }}>Se actualiza con cada respuesta. Puedes editar cualquier dato.</p>
        <div className="barra" style={{ marginTop: 12 }}><div style={{ width: `${pct}%` }} /></div>
        <p style={{ margin: "6px 0 0", fontSize: 12, color: "var(--texto-2)" }}>{est?.completos ?? 0} de {est?.total ?? 7} temas completos</p>
      </div>

      <Seccion titulo="Proyecto" onEditar={() => setEditando("proyecto")}>
        {editando === "proyecto" ? (
          <EditorProyecto b={b} onGuardar={(c) => { cambiar(c); setEditando(null); }} onCancelar={() => setEditando(null)} />
        ) : (
          <dl className="dl">
            <dt>Tipo</dt><dd>{b.tipo_proyecto ?? "—"}</dd>
            <dt>Niveles</dt><dd className="num">{b.niveles ?? "—"}</dd>
            <dt>Ubicación</dt><dd>{[b.ubicacion.distrito, b.ubicacion.ciudad].filter(Boolean).join(", ") || "—"}</dd>
            {b.ubicacion.contexto.length > 0 && (<><dt>Contexto</dt><dd>{b.ubicacion.contexto.join(", ")}</dd></>)}
          </dl>
        )}
      </Seccion>

      <Seccion titulo="Terreno" onEditar={() => setEditando("terreno")}>
        {editando === "terreno" ? (
          <EditorTerreno b={b} onGuardar={(c) => { cambiar(c); setEditando(null); }} onCancelar={() => setEditando(null)} />
        ) : (
          <dl className="dl">
            <dt>Frente</dt><dd className="num">{b.terreno.frente_m ? `${fmt(b.terreno.frente_m)} m` : "—"}</dd>
            <dt>Fondo</dt><dd className="num">{b.terreno.fondo_m ? `${fmt(b.terreno.fondo_m)} m` : "—"}</dd>
            <dt>Área</dt><dd className="num">{b.terreno.frente_m && b.terreno.fondo_m ? `${fmt(b.terreno.frente_m * b.terreno.fondo_m)} m²` : "—"}</dd>
            <dt>Retiro frontal</dt><dd>{b.terreno.retiro_frontal_m !== null ? <span className="num">{fmt(b.terreno.retiro_frontal_m)} m</span> : origen("terreno.retiro_frontal_m") ?? "—"}</dd>
            <dt>Estudio de suelos</dt>
            <dd style={{ color: b.terreno.estudio_suelos === "si" ? "var(--ok)" : b.terreno.estudio_suelos ? "var(--pendiente)" : undefined }}>
              {b.terreno.estudio_suelos === "si" ? "Disponible" : b.terreno.estudio_suelos ? "Pendiente" : "—"}
            </dd>
          </dl>
        )}
      </Seccion>

      <Seccion titulo="Programa de ambientes" onEditar={() => setEditando("programa")}>
        {editando === "programa" ? (
          <EditorProgramaSimple b={b} onGuardar={(c) => { cambiar(c); setEditando(null); }} onCancelar={() => setEditando(null)} />
        ) : b.ambientes.length === 0 ? (
          <p style={{ margin: 0, color: "var(--texto-2)", fontSize: 13 }}>Aún sin ambientes.</p>
        ) : (
          <dl className="dl">
            {Array.from(new Set(b.ambientes.map((a) => a.nivel))).sort().map((n) => (
              <Fila key={n} n={n} ambs={b.ambientes.filter((a) => a.nivel === n)} />
            ))}
          </dl>
        )}
      </Seccion>

      <Seccion titulo="Presupuesto y preferencias" onEditar={() => setEditando("pref")}>
        {editando === "pref" ? (
          <EditorPref b={b} onGuardar={(c) => { cambiar(c); setEditando(null); }} onCancelar={() => setEditando(null)} />
        ) : (
          <dl className="dl">
            <dt>Presupuesto</dt><dd>{b.presupuesto.monto ? <span className="num">S/ {b.presupuesto.monto.toLocaleString("es-PE")}</span> : origen("presupuesto.monto") ?? "—"}</dd>
            <dt>Luz natural</dt><dd>{b.preferencias.luz_natural ? b.preferencias.luz_natural[0].toUpperCase() + b.preferencias.luz_natural.slice(1) : "—"}</dd>
          </dl>
        )}
      </Seccion>

      <button className="btn primario" disabled={!puedeGenerar || cargando} onClick={onGenerar} style={{ minHeight: 44 }}>
        Generar alternativas
      </button>
      {!puedeGenerar && est && <p style={{ margin: 0, fontSize: 12, color: "var(--texto-2)" }}>Faltan datos obligatorios: {est.faltan_obligatorios.map(nombreCampo).join(", ")}.</p>}

      {s.avisos.length > 0 && <Avisos avisos={s.avisos} nuevos={s.historial[s.historial.length - 1]?.avisos ?? []} />}
    </aside>
  );
}

function Fila({ n, ambs }: { n: number; ambs: Ambiente[] }) {
  return (
    <>
      <dt>Nivel {n}</dt>
      <dd style={{ lineHeight: 1.6 }}>
        {ambs.map((a, i) => (
          <span key={a.nombre}>
            {a.nombre}{a.area_objetivo_m2 ? <span className="num" style={{ color: "var(--texto-2)" }}> {fmt(a.area_objetivo_m2, 0)} m²</span> : null}
            {i < ambs.length - 1 ? ", " : ""}
          </span>
        ))}
      </dd>
    </>
  );
}

export function Avisos({ avisos, nuevos = [] }: { avisos: Aviso[]; nuevos?: string[] }) {
  return (
    <section style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <h2 style={{ margin: 0, fontSize: 15 }}>A tener en cuenta en esta ubicación</h2>
      {avisos.map((a) => (
        <div key={a.id} className={`aviso ${nuevos.includes(a.id) ? "nuevo" : ""}`}>
          <b>{a.titulo}</b>
          <span>{a.texto}</span>
          <small>Referencia: {a.url ? <a href={a.url} target="_blank" rel="noreferrer">{a.referencia}</a> : a.referencia}</small>
        </div>
      ))}
      <p style={{ margin: 0, fontSize: 12, lineHeight: 1.5, color: "var(--texto-2)" }}>Avisos de la base de reglas de ARQIA. No reemplazan la consulta profesional ni municipal.</p>
    </section>
  );
}

function Seccion({ titulo, onEditar, children }: { titulo: string; onEditar: () => void; children: React.ReactNode }) {
  return (
    <div className="tarjeta">
      <div className="tarjeta-cab"><h3 className="etiqueta">{titulo}</h3><button className="enlace" onClick={onEditar}>Editar</button></div>
      <div className="tarjeta-cuerpo">{children}</div>
    </div>
  );
}

const nombreCampo = (c: string) => ({ tipo_proyecto: "tipo de proyecto", "terreno.frente_m": "frente", "terreno.fondo_m": "fondo", niveles: "niveles", ambientes: "ambientes" } as Record<string, string>)[c] ?? c;

type Ed = { b: Brief; onGuardar: (c: Record<string, unknown>) => void; onCancelar: () => void };

function Botones({ onCancelar }: { onCancelar: () => void }) {
  return (
    <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
      <button className="btn chico oscuro" type="submit">Guardar</button>
      <button className="btn chico" type="button" onClick={onCancelar}>Cancelar</button>
    </div>
  );
}

function EditorProyecto({ b, onGuardar, onCancelar }: Ed) {
  const [v, setV] = useState({ tipo: b.tipo_proyecto ?? "", niveles: b.niveles ?? 1, distrito: b.ubicacion.distrito ?? "", ciudad: b.ubicacion.ciudad ?? "", contexto: b.ubicacion.contexto.join(", ") });
  return (
    <form onSubmit={(e) => { e.preventDefault(); onGuardar({ tipo_proyecto: v.tipo, niveles: Number(v.niveles), distrito: v.distrito, ciudad: v.ciudad, contexto: v.contexto.split(",").map((x) => x.trim()).filter(Boolean) }); }}>
      <div className="dl">
        <label htmlFor="e-tipo">Tipo</label><input id="e-tipo" className="campo" value={v.tipo} onChange={(e) => setV({ ...v, tipo: e.target.value })} />
        <label htmlFor="e-niv">Niveles</label><input id="e-niv" className="campo" type="number" min={1} max={4} value={v.niveles} onChange={(e) => setV({ ...v, niveles: Number(e.target.value) })} />
        <label htmlFor="e-dis">Distrito</label><input id="e-dis" className="campo" value={v.distrito} onChange={(e) => setV({ ...v, distrito: e.target.value })} />
        <label htmlFor="e-ciu">Ciudad</label><input id="e-ciu" className="campo" value={v.ciudad} onChange={(e) => setV({ ...v, ciudad: e.target.value })} />
        <label htmlFor="e-ctx">Contexto</label><input id="e-ctx" className="campo" value={v.contexto} placeholder="campiña, ladera…" onChange={(e) => setV({ ...v, contexto: e.target.value })} />
      </div>
      <Botones onCancelar={onCancelar} />
    </form>
  );
}

function EditorTerreno({ b, onGuardar, onCancelar }: Ed) {
  const [v, setV] = useState({ frente: b.terreno.frente_m ?? "", fondo: b.terreno.fondo_m ?? "", retiro: b.terreno.retiro_frontal_m ?? "", suelos: b.terreno.estudio_suelos ?? "no" });
  return (
    <form onSubmit={(e) => { e.preventDefault(); onGuardar({ frente_m: Number(v.frente) || null, fondo_m: Number(v.fondo) || null, retiro_frontal_m: v.retiro === "" ? null : Number(v.retiro), estudio_suelos: v.suelos }); }}>
      <div className="dl">
        <label htmlFor="t-fr">Frente (m)</label><input id="t-fr" className="campo" type="number" step="0.01" value={v.frente} onChange={(e) => setV({ ...v, frente: e.target.value })} />
        <label htmlFor="t-fo">Fondo (m)</label><input id="t-fo" className="campo" type="number" step="0.01" value={v.fondo} onChange={(e) => setV({ ...v, fondo: e.target.value })} />
        <label htmlFor="t-re">Retiro frontal (m)</label><input id="t-re" className="campo" type="number" step="0.01" value={v.retiro} onChange={(e) => setV({ ...v, retiro: e.target.value })} />
        <label htmlFor="t-su">Estudio de suelos</label>
        <select id="t-su" className="campo" value={v.suelos} onChange={(e) => setV({ ...v, suelos: e.target.value as typeof v.suelos })}>
          <option value="si">Disponible</option><option value="no">Todavía no</option><option value="desconoce">No sabe</option>
        </select>
      </div>
      <Botones onCancelar={onCancelar} />
    </form>
  );
}

function EditorPref({ b, onGuardar, onCancelar }: Ed) {
  const [v, setV] = useState({ monto: b.presupuesto.monto ?? "", luz: b.preferencias.luz_natural ?? "alta" });
  return (
    <form onSubmit={(e) => { e.preventDefault(); onGuardar({ presupuesto_soles: Number(v.monto) || null, luz_natural: v.luz }); }}>
      <div className="dl">
        <label htmlFor="p-m">Presupuesto (S/)</label><input id="p-m" className="campo" type="number" value={v.monto} onChange={(e) => setV({ ...v, monto: e.target.value })} />
        <label htmlFor="p-l">Luz natural</label>
        <select id="p-l" className="campo" value={v.luz} onChange={(e) => setV({ ...v, luz: e.target.value as typeof v.luz })}>
          <option value="alta">Alta</option><option value="media">Media</option><option value="baja">Baja</option>
        </select>
      </div>
      <Botones onCancelar={onCancelar} />
    </form>
  );
}

export function EditorProgramaSimple({ b, onGuardar, onCancelar }: Ed) {
  const [filas, setFilas] = useState<Ambiente[]>(b.ambientes.map((a) => ({ ...a })));
  const niveles = b.niveles ?? 1;
  const upd = (i: number, p: Partial<Ambiente>) => setFilas(filas.map((f, j) => (j === i ? { ...f, ...p } : f)));
  return (
    <form onSubmit={(e) => {
      e.preventDefault();
      const validas = filas.filter((f) => f.nombre.trim());
      onGuardar({ ambientes_quitar: b.ambientes.map((a) => ({ nombre: a.nombre, nivel: a.nivel })), ambientes_agregar: validas });
    }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {filas.map((f, i) => (
          <div key={i} style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) 64px 92px 72px 28px", gap: 6 }}>
            <input aria-label="Nombre" className="campo" style={{ minHeight: 34, padding: "4px 8px" }} value={f.nombre} onChange={(e) => upd(i, { nombre: e.target.value })} />
            <select aria-label="Nivel" className="campo" style={{ minHeight: 34, padding: "4px" }} value={f.nivel} onChange={(e) => upd(i, { nivel: Number(e.target.value) })}>
              {Array.from({ length: niveles }, (_, k) => <option key={k} value={k + 1}>N{k + 1}</option>)}
            </select>
            <select aria-label="Tipo" className="campo" style={{ minHeight: 34, padding: "4px" }} value={f.tipo} onChange={(e) => upd(i, { tipo: e.target.value as TipoAmbiente })}>
              {(["publico", "privado", "servicio"] as TipoAmbiente[]).map((t) => <option key={t} value={t}>{NOMBRE_TIPO[t]}</option>)}
            </select>
            <input aria-label="Área m²" className="campo num" style={{ minHeight: 34, padding: "4px 8px" }} type="number" placeholder="m²" value={f.area_objetivo_m2 ?? ""} onChange={(e) => upd(i, { area_objetivo_m2: e.target.value ? Number(e.target.value) : null })} />
            <button type="button" className="enlace" aria-label={`Quitar ${f.nombre}`} onClick={() => setFilas(filas.filter((_, j) => j !== i))}>✕</button>
          </div>
        ))}
        <button type="button" className="enlace" style={{ alignSelf: "flex-start" }} onClick={() => setFilas([...filas, { nombre: "", nivel: 1, tipo: "privado", area_objetivo_m2: null }])}>Agregar ambiente</button>
      </div>
      <Botones onCancelar={onCancelar} />
    </form>
  );
}

import { useEffect, useState } from "react";
import { api } from "./api";
import Planta from "./Planta";
import { fmt, useArqia } from "./store";

const FILAS: { k: string; nombre: string; u: string; d: number; mayor: boolean }[] = [
  { k: "area_techada_m2", nombre: "Área techada", u: "m²", d: 2, mayor: true },
  { k: "area_util_m2", nombre: "Área útil", u: "m²", d: 2, mayor: true },
  { k: "area_comercial_m2", nombre: "Área de uso público", u: "m²", d: 2, mayor: true },
  { k: "frente_comercial_m", nombre: "Frente comercial", u: "m", d: 2, mayor: true },
  { k: "area_circulacion_m2", nombre: "Área de circulación", u: "m²", d: 2, mayor: false },
  { k: "circulacion_pct", nombre: "Proporción de circulación", u: "%", d: 1, mayor: false },
  { k: "ambientes_con_luz_pct", nombre: "Ambientes habitables con luz", u: "%", d: 0, mayor: true },
  { k: "area_ventanas_m2", nombre: "Área de ventanas", u: "m²", d: 2, mayor: true },
  { k: "acceso_directo_pct", nombre: "Acceso directo a circulación", u: "%", d: 1, mayor: true },
  { k: "cumplimiento_programa_pct", nombre: "Ajuste al programa (±15 %)", u: "%", d: 0, mayor: true },
  { k: "verificaciones_cumple", nombre: "Verificaciones geométricas que cumplen", u: "", d: 0, mayor: true },
  { k: "tiempo_generacion_ms", nombre: "Tiempo de generación", u: "ms", d: 1, mayor: false },
];

export default function Comparador() {
  const s = useArqia();
  const [cargando, setCargando] = useState(false);
  useEffect(() => {
    if (!s.explicacion && s.alternativas.length) {
      setCargando(true);
      api.explicar(s.brief, s.alternativas).then((e) => s.set({ explicacion: e })).finally(() => setCargando(false));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [s.alternativas]);
  const alts = s.alternativas;
  const exp = s.explicacion;

  function elegir(id: string) {
    s.set({ elegida: id, activa: id });
    s.decidir(`El cliente eligió la ${alts.find((a) => a.id === id)?.nombre}.`);
  }

  return (
    <div className="comparador">
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: 16, justifyContent: "space-between" }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22 }}>Comparación de alternativas</h1>
          <p style={{ margin: "4px 0 0", color: "var(--texto-2)" }}>Mismo lote y mismo programa. Todos los indicadores salen del modelo; nada se estima con IA.</p>
        </div>
        <button className="btn" onClick={() => s.set({ pantalla: "ficha" })} disabled={!s.elegida}>Ver ficha comercial</button>
      </div>

      <div className="mini">
        {alts.map((a) => (
          <div key={a.id} className={`tarjeta ${s.elegida === a.id ? "elegida" : ""}`}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
              <b>{a.nombre}</b>
              {exp?.recomendacion.id === a.id && <span style={{ fontSize: 12, color: "var(--acento)", fontWeight: 600 }}>Recomendada</span>}
            </div>
            <span style={{ color: "var(--texto-2)", fontSize: 13 }}>{a.estrategia}</span>
            <div style={{ display: "grid", gridTemplateColumns: `repeat(${a.niveles.length}, minmax(0,1fr))`, gap: 8 }}>
              {a.niveles.map((n) => (
                <div key={n.numero} style={{ cursor: "pointer" }} onClick={() => s.set({ activa: a.id, nivel: n.numero, pantalla: "trabajo" })}>
                  <Planta alt={a} nivel={n} escala={14} etiquetas={false} cotas={false} ajustar />
                  <div style={{ fontSize: 12, color: "var(--texto-2)", textAlign: "center" }}>{n.nombre}</div>
                </div>
              ))}
            </div>
            <button className={`btn chico ${s.elegida === a.id ? "primario" : ""}`} onClick={() => elegir(a.id)}>
              {s.elegida === a.id ? "Alternativa elegida" : "Elegir esta alternativa"}
            </button>
          </div>
        ))}
      </div>

      <table className="tabla">
        <thead><tr><th>Indicador</th>{alts.map((a) => <th key={a.id}>{a.nombre}</th>)}</tr></thead>
        <tbody>
          {FILAS.map((f) => {
            const vals = alts.map((a) => Number(a.indicadores[f.k]));
            const mejor = f.mayor ? Math.max(...vals) : Math.min(...vals);
            const unico = vals.filter((v) => v === mejor).length === 1;
            return (
              <tr key={f.k}>
                <td>{f.nombre}</td>
                {alts.map((a, i) => (
                  <td key={a.id} className={`num ${unico && vals[i] === mejor ? "mejor" : ""}`}>{fmt(vals[i], f.d)}{f.u ? ` ${f.u}` : ""}</td>
                ))}
              </tr>
            );
          })}
          <tr>
            <td>Acceso independiente a niveles superiores</td>
            {alts.map((a) => <td key={a.id}>{a.indicadores.acceso_independiente_superior ? "Sí" : "No"}</td>)}
          </tr>
        </tbody>
      </table>
      <p style={{ margin: "-8px 0 0", fontSize: 12, color: "var(--texto-2)" }}>En color, el mejor valor cuando una sola alternativa lo alcanza.</p>

      <div className="tarjeta" style={{ padding: 20, display: "flex", flexDirection: "column", gap: 14 }}>
        <h2 className="etiqueta">Lectura del Asistente ARQIA</h2>
        {cargando && <p className="pensando">Preparando la explicación…</p>}
        {exp && (
          <>
            <p style={{ margin: 0, lineHeight: 1.55 }}>{exp.resumen}</p>
            <div className="mini">
              {exp.por_alternativa.map((p) => (
                <div key={p.id} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <b>{alts.find((a) => a.id === p.id)?.nombre}</b>
                  <ul className="lista" style={{ fontSize: 13 }}>{p.ventajas.map((v) => <li key={v}>{v}</li>)}</ul>
                  {p.desventajas.length > 0 && <ul className="lista" style={{ fontSize: 13, color: "var(--texto-2)" }}>{p.desventajas.map((v) => <li key={v}>{v}</li>)}</ul>}
                </div>
              ))}
            </div>
            <p style={{ margin: 0, lineHeight: 1.55 }}><b>Recomendación: {alts.find((a) => a.id === exp.recomendacion.id)?.nombre}.</b> {exp.recomendacion.motivo}</p>
            <p style={{ margin: 0, fontSize: 12, color: "var(--texto-2)" }}>
              {exp.fuente === "asistente" ? "Texto redactado por el asistente y revisado por el verificador de cifras de ARQIA." : "Texto generado por reglas a partir de los indicadores calculados."}
              {exp.descartes_verificador && exp.descartes_verificador.length > 0 ? ` Se descartaron ${exp.descartes_verificador.length} frases con cifras sin origen.` : ""}
            </p>
          </>
        )}
      </div>

      <div className="tarjeta" style={{ padding: 20, display: "flex", flexDirection: "column", gap: 10 }}>
        <label htmlFor="notas" className="etiqueta">Observaciones del cliente</label>
        <textarea id="notas" className="campo" rows={3} value={s.notasCliente} onChange={(e) => s.set({ notasCliente: e.target.value })}
          onBlur={() => s.notasCliente.trim() && s.decidir(`Observación del cliente: ${s.notasCliente.trim()}`)} placeholder="Escribe aquí lo que el cliente comenta sobre las alternativas…" />
      </div>
    </div>
  );
}

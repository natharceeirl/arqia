import Planta from "./Planta";
import { fmt, soles, useArqia } from "./store";
import { EstadoFila } from "./Trabajo";

export default function Ficha({ onIfc }: { onIfc: () => void }) {
  const s = useArqia();
  const alt = s.alternativas.find((a) => a.id === (s.elegida ?? s.activa)) ?? s.alternativas[0];
  if (!alt) return null;
  const b = s.brief;
  const ind = alt.indicadores as Record<string, number>;
  const hoy = new Date().toLocaleDateString("es-PE", { day: "numeric", month: "long", year: "numeric" });
  const pendientes = alt.verificaciones.filter((v) => v.estado !== "cumple");
  const res = s.costos[alt.id];
  const supuestosBrief = Object.entries(b.origen).filter(([, v]) => v === "supuesto" || v === "desconocido").length;

  return (
    <div style={{ padding: "0 16px" }}>
      <div className="no-imprimir" style={{ maxWidth: 900, margin: "24px auto 0", display: "flex", gap: 8, justifyContent: "flex-end" }}>
        <button className="btn" onClick={onIfc}>Exportar IFC</button>
        <button className="btn primario" onClick={() => window.print()}>Imprimir o guardar PDF</button>
      </div>
      <article className="ficha">
        <header style={{ display: "flex", justifyContent: "space-between", gap: 20, flexWrap: "wrap" }}>
          <div>
            <p className="etiqueta" style={{ marginBottom: 6 }}>Ficha técnica y comercial preliminar</p>
            <h1 contentEditable suppressContentEditableWarning className="editable">{b.nombre_proyecto}</h1>
            <p style={{ margin: "6px 0 0", color: "var(--texto-2)" }}>{alt.nombre}: {alt.estrategia.toLowerCase()}</p>
          </div>
          <div style={{ textAlign: "right", fontSize: 12, color: "var(--texto-2)", lineHeight: 1.6 }}>
            <div>ARQIA</div><div>{hoy}</div><div className="num">Huella {alt.huella}</div>
          </div>
        </header>

        <section className="dos">
          <div>
            <h2>Requerimientos del cliente</h2>
            <dl className="dl">
              <dt>Tipo</dt><dd>{b.tipo_proyecto}</dd>
              <dt>Ubicación</dt><dd>{[b.ubicacion.distrito, b.ubicacion.ciudad].filter(Boolean).join(", ")}</dd>
              <dt>Terreno</dt><dd className="num">{fmt(b.terreno.frente_m)} × {fmt(b.terreno.fondo_m)} m</dd>
              <dt>Niveles</dt><dd className="num">{b.niveles}</dd>
              {b.presupuesto.monto ? (<><dt>Presupuesto</dt><dd className="num">S/ {b.presupuesto.monto.toLocaleString("es-PE")} (referencial)</dd></>) : null}
              <dt>Preferencias</dt><dd>Luz natural {b.preferencias.luz_natural ?? "no indicada"}</dd>
            </dl>
          </div>
          <div>
            <h2>Indicadores calculados</h2>
            <dl className="dl">
              <dt>Área techada</dt><dd className="num">{fmt(ind.area_techada_m2)} m²</dd>
              <dt>Área útil</dt><dd className="num">{fmt(ind.area_util_m2)} m²</dd>
              <dt>Uso público</dt><dd className="num">{fmt(ind.area_comercial_m2)} m²</dd>
              <dt>Circulación</dt><dd className="num">{fmt(ind.area_circulacion_m2)} m² ({fmt(ind.circulacion_pct, 1)} %)</dd>
              <dt>Ambientes con luz</dt><dd className="num">{fmt(ind.ambientes_con_luz_pct, 0)} %</dd>
              <dt>Generado en</dt><dd className="num">{fmt(alt.tiempo_ms, 1)} ms</dd>
            </dl>
          </div>
        </section>

        <section>
          <h2>Plantas</h2>
          <div style={{ display: "grid", gridTemplateColumns: `repeat(${alt.niveles.length}, minmax(0,1fr))`, gap: 20 }}>
            {alt.niveles.map((n) => (
              <figure key={n.numero} style={{ margin: 0, maxWidth: 330, justifySelf: "center", width: "100%" }}>
                <Planta alt={alt} nivel={n} escala={22} ajustar />
                <figcaption style={{ textAlign: "center", fontSize: 12, color: "var(--texto-2)" }}>{n.nombre}, cota +{fmt(n.cota_m)} m</figcaption>
              </figure>
            ))}
          </div>
        </section>

        <section>
          <h2>Cuadro de áreas</h2>
          <table className="tabla">
            <thead><tr><th>Ambiente</th><th>Nivel</th><th>Área objetivo</th><th>Área generada</th></tr></thead>
            <tbody>
              {alt.niveles.flatMap((n) => n.espacios.filter((e) => !["escalera", "patio"].includes(e.funcion)).map((e) => (
                <tr key={e.id}>
                  <td>{e.nombre}</td><td className="num">{n.numero}</td>
                  <td className="num">{e.area_objetivo_m2 ? `${fmt(e.area_objetivo_m2)} m²` : "—"}</td>
                  <td className="num">{fmt(e.area_m2)} m²</td>
                </tr>
              )))}
            </tbody>
          </table>
        </section>

        {res && (
          <section>
            <h2>Materiales y estimación de costos</h2>
            <table className="tabla">
              <thead><tr><th>Partida</th><th>Material (categoría oficial)</th><th>S/ por m²</th><th>Monto</th></tr></thead>
              <tbody>
                {res.por_partida.map((p) => {
                  const desc = s.vuoe?.partidas.find((x) => x.id === p.partida)?.categorias.find((c) => c.categoria === p.categoria)?.descripcion;
                  return (
                    <tr key={p.partida} style={p.reemplazada ? { color: "var(--texto-2)", textDecoration: "line-through" } : undefined}>
                      <td>{p.nombre}</td><td style={{ textAlign: "left" }}>{p.categoria}{desc ? `: ${desc}` : ""}</td><td className="num">{fmt(p.valor_m2)}</td><td className="num">{soles(p.monto)}</td>
                    </tr>
                  );
                })}
                {res.cotizacion.filter((i) => i.incluir).map((i) => (
                  <tr key={i.id}><td>Cotización</td><td style={{ textAlign: "left" }}>{i.descripcion} ({fmt(i.cantidad)} {i.unidad})</td><td className="num">{fmt(i.precio_unitario)}</td><td className="num">{soles(i.subtotal)}</td></tr>
                ))}
                <tr><td><b>Construcción</b></td><td /><td className="num">{fmt(res.totales.construccion_m2)}</td><td className="num"><b>{soles(res.totales.construccion)}</b></td></tr>
                {res.totales.terreno !== null && <tr><td>Terreno</td><td style={{ textAlign: "left" }}>{res.terreno.fuente}</td><td className="num">{fmt(res.terreno.valor_m2)}</td><td className="num">{soles(res.totales.terreno)}</td></tr>}
                {res.totales.terreno !== null && <tr><td><b>Total</b></td><td /><td /><td className="num"><b>{soles(res.totales.total)}</b></td></tr>}
              </tbody>
            </table>
            <p style={{ margin: "8px 0 0", fontSize: 11.5, color: "var(--texto-2)", lineHeight: 1.5 }}>
              Fuente: {res.fuente.nombre}, {res.fuente.vigencia.toLowerCase()} ({res.fuente.base_legal}). {res.fuente.naturaleza}.
            </p>
          </section>
        )}

        <section className="dos">
          <div>
            <h2>Verificaciones y puntos pendientes</h2>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>{pendientes.map((v) => <EstadoFila key={v.id} v={v} />)}</div>
          </div>
          <div>
            <h2>Supuestos</h2>
            <ul className="lista" style={{ fontSize: 13 }}>
              {alt.supuestos.map((x) => <li key={x}>{x}</li>)}
              {supuestosBrief > 0 && <li>{supuestosBrief} datos del brief son supuestos o están por confirmar; se marcan en el resumen.</li>}
            </ul>
          </div>
        </section>

        <section>
          <h2>Limitaciones</h2>
          <p style={{ margin: 0, lineHeight: 1.6, fontSize: 13 }} contentEditable suppressContentEditableWarning className="editable">
            Propuesta preliminar generada por un motor paramétrico para apoyar la decisión comercial. No constituye diseño arquitectónico,
            estructural ni de instalaciones aprobado, y no certifica cumplimiento normativo. Requiere revisión y firma de profesionales
            competentes, estudio de mecánica de suelos y certificado de parámetros urbanísticos antes de su desarrollo.
          </p>
        </section>

        <section>
          <h2>Registro de decisiones</h2>
          {s.decisiones.length === 0 ? <p style={{ margin: 0, color: "var(--texto-2)" }}>Sin decisiones registradas.</p> : (
            <table className="tabla">
              <tbody>{s.decisiones.map((d, i) => <tr key={i}><td className="num" style={{ width: 170 }}>{d.fecha}</td><td style={{ textAlign: "left" }}>{d.texto}</td></tr>)}</tbody>
            </table>
          )}
        </section>

        <footer style={{ fontSize: 11.5, color: "var(--texto-2)", lineHeight: 1.6, borderTop: "1px solid var(--borde)", paddingTop: 12 }}>
          Datos calculados por el motor paramétrico ARQIA {alt.motor_version}. Las explicaciones del asistente pasan por un verificador de cifras.
          El mismo brief produce siempre el mismo diseño (huella {alt.huella}).
        </footer>
      </article>
    </div>
  );
}

import { useRef, useState } from "react";
import { api } from "./api";
import { fmt, soles, useArqia } from "./store";
import type { ItemCotizacion, Partida } from "./tipos";

const PARTIDAS_AMBIENTE: Partida[] = ["pisos", "revestimientos"];
const NOMBRE_CANT: Record<string, string> = {
  area_techada_m2: "Área techada", piso_m2: "Pisos", muro_m2: "Muros (neto de vanos)", muro_ext_m2: "Muros exteriores",
  muro_int_m2: "Muros interiores", losa_m2: "Losas (piso y techo)", losa_m3: "Concreto en losas", puertas_und: "Puertas",
  ventanas_und: "Ventanas", ventanas_m2: "Superficie de ventanas", banos_und: "Servicios higiénicos",
};
const UNIDAD_CANT: Record<string, string> = { losa_m3: "m³", puertas_und: "und", ventanas_und: "und", banos_und: "und" };

function aBase64(f: File): Promise<string> {
  return new Promise((ok, mal) => {
    const r = new FileReader();
    r.onload = () => ok(String(r.result).split(",")[1] ?? "");
    r.onerror = () => mal(r.error);
    r.readAsDataURL(f);
  });
}

export default function Costos() {
  const s = useArqia();
  const alt = s.alternativas.find((a) => a.id === s.activa) ?? s.alternativas[0];
  const res = alt ? s.costos[alt.id] : undefined;
  const t = s.vuoe;
  const e = s.costosEntrada;
  const [importando, setImportando] = useState(false);
  const [mensaje, setMensaje] = useState<string | null>(null);
  const archivo = useRef<HTMLInputElement>(null);
  if (!alt) return null;
  const spec = { ...(t?.especificacion_por_defecto ?? {}), ...e.especificacion } as Record<Partida, string>;
  const setEntrada = (p: Partial<typeof e>) => s.set({ costosEntrada: { ...e, ...p } });
  const setItem = (id: string, p: Partial<ItemCotizacion>) => setEntrada({ cotizacion: e.cotizacion.map((i) => (i.id === id ? { ...i, ...p } : i)) });

  async function importar(f: File) {
    setImportando(true);
    setMensaje(null);
    try {
      const r = await api.importarCotizacion(f.name, await aBase64(f));
      setEntrada({ cotizacion: [...e.cotizacion, ...r.items] });
      setMensaje(`${r.items.length} partidas importadas de ${r.archivo} (${r.metodo}).${r.avisos.length ? " " + r.avisos.join(" ") : ""}`);
      s.decidir(`Se importó la cotización ${r.archivo} con ${r.items.length} partidas.`);
    } catch (err) {
      setMensaje(`No se pudo importar: ${(err as Error).message}`);
    } finally {
      setImportando(false);
      if (archivo.current) archivo.current.value = "";
    }
  }

  return (
    <div className="comparador">
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: 16, justifyContent: "space-between" }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 22 }}>Materiales y costos</h1>
          <p style={{ margin: "4px 0 0", color: "var(--texto-2)" }}>
            Estimación referencial con valores oficiales por m² de área techada. Cambia un material y todo se recalcula.
          </p>
        </div>
        <div role="group" aria-label="Alternativa" className="segmentado">
          {s.alternativas.map((a) => (
            <button key={a.id} className={a.id === alt.id ? "activo" : ""} onClick={() => s.set({ activa: a.id })}>{a.nombre}</button>
          ))}
        </div>
      </div>

      {res && (
        <div className="mini" style={{ gridTemplateColumns: "repeat(4, minmax(0,1fr))" }}>
          <Total k="Construcción" v={soles(res.totales.construccion)} d={`${soles(res.totales.construccion_m2, 2)} por m² techado`} fuerte />
          <Total k="Valores oficiales incluidos" v={soles(res.totales.vuoe_incluido)} d={`de ${soles(res.totales.vuoe)} sin reemplazos`} />
          <Total k="Cotizaciones" v={soles(res.totales.cotizacion)} d={`${res.cotizacion.filter((i) => i.incluir).length} partidas incluidas`} />
          <Total k="Total con terreno" v={soles(res.totales.total)} d={res.totales.terreno !== null ? `Terreno ${soles(res.totales.terreno)}` : "Terreno no incluido"} />
        </div>
      )}

      <div className="dos" style={{ alignItems: "start" }}>
        <div className="tarjeta">
          <div className="tarjeta-cab"><h2 className="etiqueta">Especificación de materiales</h2><span style={{ fontSize: 12, color: "var(--texto-2)" }}>Categoría oficial por partida</span></div>
          <div className="tarjeta-cuerpo" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {t?.partidas.map((p) => {
              const tieneCot = e.cotizacion.some((i) => i.partida === p.id);
              return (
                <div key={p.id} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <label htmlFor={`sp-${p.id}`} style={{ fontSize: 13, fontWeight: 600 }}>{p.nombre}</label>
                  <select id={`sp-${p.id}`} className="campo" style={{ minHeight: 36 }} value={spec[p.id]}
                    onChange={(ev) => { setEntrada({ especificacion: { ...e.especificacion, [p.id]: ev.target.value } }); s.decidir(`${p.nombre}: categoría ${ev.target.value}.`); }}>
                    {p.categorias.map((c) => (
                      <option key={c.categoria} value={c.categoria}>{c.categoria} — {c.descripcion || "sin descripción"} ({soles(c.valor_m2, 2)} por m²)</option>
                    ))}
                  </select>
                  {tieneCot && (
                    <label style={{ fontSize: 12.5, color: "var(--texto-3)", display: "flex", gap: 6, alignItems: "center" }}>
                      <input type="checkbox" checked={e.reemplazos.includes(p.id)}
                        onChange={(ev) => setEntrada({ reemplazos: ev.target.checked ? [...e.reemplazos, p.id] : e.reemplazos.filter((x) => x !== p.id) })} />
                      Reemplazar el valor oficial de esta partida por la cotización importada
                    </label>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        <div className="tarjeta">
          <div className="tarjeta-cab"><h2 className="etiqueta">Desglose por partida</h2><span className="num" style={{ fontSize: 12, color: "var(--texto-2)" }}>{alt.nombre}</span></div>
          {res && (
            <table className="tabla" style={{ border: 0 }}>
              <thead><tr><th>Partida</th><th>Cat.</th><th>S/ por m²</th><th>Monto</th></tr></thead>
              <tbody>
                {res.por_partida.map((p) => (
                  <tr key={p.partida} style={p.reemplazada ? { color: "var(--texto-2)", textDecoration: "line-through" } : undefined}>
                    <td>{p.nombre}</td><td className="num">{p.categoria}</td><td className="num">{fmt(p.valor_m2)}</td><td className="num">{soles(p.monto)}</td>
                  </tr>
                ))}
                {res.por_nivel.map((n) => (
                  <tr key={n.nivel}><td style={{ color: "var(--texto-2)" }}>Nivel {n.nivel}</td><td /><td /><td className="num" style={{ color: "var(--texto-2)" }}>{soles(n.monto)}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className="tarjeta">
        <div className="tarjeta-cab"><h2 className="etiqueta">Materiales por ambiente</h2><span style={{ fontSize: 12, color: "var(--texto-2)" }}>Pisos y revestimientos se pueden elegir por ambiente; aplica a las tres alternativas</span></div>
        {res && t && (
          <div style={{ overflowX: "auto" }}>
            <table className="tabla" style={{ border: 0 }}>
              <thead><tr><th>Ambiente</th><th>Nivel</th><th>Área</th><th>Pisos</th><th>Revestimientos</th><th>S/ por m²</th><th>Costo</th></tr></thead>
              <tbody>
                {res.espacios.map((x) => {
                  const clave = `${x.nivel}:${x.nombre}`;
                  return (
                    <tr key={x.id}>
                      <td>{x.nombre}</td><td className="num">{x.nivel}</td><td className="num">{fmt(x.area_m2)} m²</td>
                      {PARTIDAS_AMBIENTE.map((p) => (
                        <td key={p}>
                          <select aria-label={`${p} de ${x.nombre}`} className="campo" style={{ minHeight: 30, padding: "2px 6px", width: 64 }} value={x.categorias[p]}
                            onChange={(ev) => setEntrada({ por_ambiente: { ...e.por_ambiente, [clave]: { ...(e.por_ambiente[clave] ?? {}), [p]: ev.target.value } } })}>
                            {t.partidas.find((q) => q.id === p)!.categorias.map((c) => <option key={c.categoria} value={c.categoria} title={c.descripcion}>{c.categoria}</option>)}
                          </select>
                        </td>
                      ))}
                      <td className="num">{fmt(x.valor_m2)}</td><td className="num">{soles(x.costo)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="tarjeta">
        <div className="tarjeta-cab">
          <h2 className="etiqueta">Cotizaciones</h2>
          <div style={{ display: "flex", gap: 8 }}>
            <input ref={archivo} type="file" accept=".csv,.xlsx,.pdf,.png,.jpg,.jpeg,.webp" style={{ display: "none" }} onChange={(ev) => ev.target.files?.[0] && importar(ev.target.files[0])} />
            <button className="btn chico" onClick={() => setEntrada({ cotizacion: [...e.cotizacion, { id: Math.random().toString(16).slice(2, 10), descripcion: "Nueva partida", partida: "otros", unidad: "glb", cantidad: 1, cantidad_origen: "usuario", precio_unitario: 0, moneda: "PEN", incluir: true, fuente: "Ingresada por el usuario", verificado: null }] })}>Agregar partida</button>
            <button className="btn chico primario" disabled={importando} onClick={() => archivo.current?.click()}>{importando ? "Leyendo archivo…" : "Importar cotización"}</button>
          </div>
        </div>
        <div className="tarjeta-cuerpo" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <p style={{ margin: 0, fontSize: 12.5, color: "var(--texto-2)" }}>
            CSV y Excel se leen directamente. PDF e imágenes los interpreta el asistente; cada precio de un PDF se contrasta con el texto del documento.
            La cantidad se toma del modelo cuando la unidad coincide (m² de muro, piso o losa; unidades de puertas, ventanas o baños).
          </p>
          {mensaje && <p style={{ margin: 0, fontSize: 13 }}>{mensaje}</p>}
          {res && res.cotizacion.length > 0 && (
            <div style={{ overflowX: "auto" }}>
              <table className="tabla" style={{ border: 0 }}>
                <thead><tr><th>Incluir</th><th>Descripción</th><th>Partida</th><th>Unidad</th><th>Cantidad</th><th>Precio unit.</th><th>Subtotal</th><th>Origen</th><th /></tr></thead>
                <tbody>
                  {res.cotizacion.map((i) => (
                    <tr key={i.id}>
                      <td><input type="checkbox" aria-label="Incluir" checked={i.incluir} onChange={(ev) => setItem(i.id, { incluir: ev.target.checked })} /></td>
                      <td style={{ textAlign: "left" }}><input aria-label="Descripción" className="campo" style={{ minHeight: 30, padding: "2px 6px", width: 220 }} value={i.descripcion} onChange={(ev) => setItem(i.id, { descripcion: ev.target.value })} /></td>
                      <td>
                        <select aria-label="Partida" className="campo" style={{ minHeight: 30, padding: "2px 6px" }} value={i.partida} onChange={(ev) => setItem(i.id, { partida: ev.target.value as ItemCotizacion["partida"] })}>
                          {t?.partidas.map((p) => <option key={p.id} value={p.id}>{p.nombre}</option>)}
                          <option value="otros">Otros</option>
                        </select>
                      </td>
                      <td><input aria-label="Unidad" className="campo" style={{ minHeight: 30, padding: "2px 6px", width: 60 }} value={i.unidad} onChange={(ev) => setItem(i.id, { unidad: ev.target.value })} /></td>
                      <td style={{ whiteSpace: "nowrap" }}>
                        <input aria-label="Cantidad" className="campo num" style={{ minHeight: 30, padding: "2px 6px", width: 84 }} type="number" step="0.01" value={i.cantidad}
                          onChange={(ev) => setItem(i.id, { cantidad: Number(ev.target.value), cantidad_origen: "usuario" })} />
                        {i.cantidad_modelo !== null && i.cantidad_origen === "usuario" && (
                          <button className="enlace" style={{ marginLeft: 6 }} onClick={() => setItem(i.id, { cantidad_origen: "modelo" })}>usar modelo</button>
                        )}
                        {i.cantidad_origen === "modelo" && i.cantidad_modelo !== null && <span className="origen">del modelo</span>}
                      </td>
                      <td><input aria-label="Precio unitario" className="campo num" style={{ minHeight: 30, padding: "2px 6px", width: 92 }} type="number" step="0.01" value={i.precio_unitario} onChange={(ev) => setItem(i.id, { precio_unitario: Number(ev.target.value) })} /></td>
                      <td className="num">{soles(i.subtotal, 2)}</td>
                      <td style={{ fontSize: 12, textAlign: "left" }}>
                        <span title={i.fuente}>{i.fuente.length > 22 ? i.fuente.slice(0, 22) + "…" : i.fuente}</span>
                        {i.verificado === true && <span className="e-cumple" style={{ display: "block" }}>Precio verificado</span>}
                        {i.verificado === false && <span className="e-pendiente" style={{ display: "block" }}>Revisar precio</span>}
                      </td>
                      <td><button className="enlace" aria-label={`Quitar ${i.descripcion}`} onClick={() => setEntrada({ cotizacion: e.cotizacion.filter((x) => x.id !== i.id) })}>✕</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      <div className="dos" style={{ alignItems: "start" }}>
        <div className="tarjeta">
          <div className="tarjeta-cab"><h2 className="etiqueta">Terreno (opcional)</h2></div>
          <div className="tarjeta-cuerpo" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div className="dl">
              <label htmlFor="t-val">Valor por m²</label>
              <input id="t-val" className="campo num" type="number" step="0.01" placeholder="S/ por m²" value={e.terreno_valor_m2 ?? ""}
                onChange={(ev) => setEntrada({ terreno_valor_m2: ev.target.value ? Number(ev.target.value) : null, terreno_fuente: e.terreno_fuente ?? "Valores arancelarios de terrenos (MEF)" })} />
              <label htmlFor="t-fue">Fuente</label>
              <input id="t-fue" className="campo" value={e.terreno_fuente ?? ""} placeholder="Valores arancelarios de terrenos (MEF)" onChange={(ev) => setEntrada({ terreno_fuente: ev.target.value })} />
            </div>
            <p style={{ margin: 0, fontSize: 12.5, color: "var(--texto-2)", lineHeight: 1.5 }}>
              El valor arancelario oficial por calle está en los planos del MEF (
              <a href="https://www.mef.gob.pe/es/valores-arancelarios-de-terrenos" target="_blank" rel="noreferrer">valores arancelarios de terrenos</a>
              ). Es un valor fiscal, no un precio de mercado. Área del terreno: <span className="num">{fmt(res?.terreno.area_m2)} m²</span>.
            </p>
          </div>
        </div>
        <div className="tarjeta">
          <div className="tarjeta-cab"><h2 className="etiqueta">Cantidades del modelo</h2><span style={{ fontSize: 12, color: "var(--texto-2)" }}>Calculadas por el motor</span></div>
          {res && (
            <table className="tabla" style={{ border: 0 }}>
              <tbody>
                {Object.entries(res.cantidades).map(([k, v]) => (
                  <tr key={k}><td>{NOMBRE_CANT[k] ?? k}</td><td className="num">{fmt(v, Number.isInteger(v) ? 0 : 2)} {UNIDAD_CANT[k] ?? "m²"}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {t && (
        <p style={{ margin: 0, fontSize: 12, color: "var(--texto-2)", lineHeight: 1.6 }}>
          Fuente: <a href={t.fuente.url} target="_blank" rel="noreferrer">{t.fuente.nombre}</a>, {t.fuente.vigencia.toLowerCase()}, publicado por el {t.fuente.publicado_por}.
          {" "}{t.fuente.base_legal}. Ámbito: {t.fuente.ambito.toLowerCase()}. {t.fuente.naturaleza}.
        </p>
      )}
    </div>
  );
}

function Total({ k, v, d, fuerte }: { k: string; v: string; d: string; fuerte?: boolean }) {
  return (
    <div className="tarjeta" style={{ padding: 16, borderColor: fuerte ? "var(--acento)" : undefined }}>
      <div style={{ fontSize: 12, color: "var(--texto-2)" }}>{k}</div>
      <div className="num" style={{ fontSize: 22, marginTop: 4, color: fuerte ? "var(--acento)" : undefined }}>{v}</div>
      <div style={{ fontSize: 12, color: "var(--texto-2)", marginTop: 2 }}>{d}</div>
    </div>
  );
}

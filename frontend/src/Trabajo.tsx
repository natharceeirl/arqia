import { lazy, Suspense, useEffect, useState } from "react";
import Planta from "./Planta";
import { coloresBase, fmt, soles, useArqia } from "./store";
import type { Colores } from "./tipos";
import type { Alternativa, Estado, Verificacion } from "./tipos";

const Vista3D = lazy(() => import("./Vista3D"));

export const ETIQUETA_ESTADO: Record<Estado, string> = {
  cumple: "Cumple", no_cumple: "No cumple", pendiente: "Pendiente", revision_profesional: "Revisión profesional",
};

export function EstadoFila({ v }: { v: Verificacion }) {
  return (
    <div className="estado" title={[v.detalle, ...v.evidencia].join("\n")}>
      <span aria-hidden="true" className={`punto p-${v.estado}`} />
      <span className="txt">{v.titulo}</span>
      <span className={`e-${v.estado}`} style={{ fontWeight: 500, whiteSpace: "nowrap" }}>{ETIQUETA_ESTADO[v.estado]}</span>
    </div>
  );
}

export default function Trabajo({ onIfc }: { onIfc: () => void }) {
  const s = useArqia();
  const alt = s.alternativas.find((a) => a.id === s.activa) ?? s.alternativas[0];
  useEffect(() => {
    const tecla = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement).tagName.match(/INPUT|TEXTAREA|SELECT/)) return;
      if (["1", "2", "3"].includes(e.key) && alt && Number(e.key) <= alt.niveles.length) s.set({ nivel: Number(e.key) });
      if (["a", "b", "c"].includes(e.key.toLowerCase())) s.set({ activa: e.key.toUpperCase(), seleccion: null });
    };
    window.addEventListener("keydown", tecla);
    return () => window.removeEventListener("keydown", tecla);
  });
  const [panelColores, setPanelColores] = useState(false);
  if (!alt) return null;
  const nivel = alt.niveles.find((n) => n.numero === s.nivel) ?? alt.niveles[0];
  const ind = alt.indicadores as Record<string, number>;
  const res = s.costos[alt.id];
  const costoPorEspacio = s.etiquetas && res ? Object.fromEntries(res.espacios.map((x) => [x.id, x.costo])) : undefined;

  return (
    <div className="trabajo">
      <aside className="lateral izq">
        <section>
          <h2 className="etiqueta">Brief del proyecto</h2>
          <dl className="dl" style={{ gridTemplateColumns: "120px minmax(0,1fr)" }}>
            <dt>Tipo</dt><dd>{s.brief.tipo_proyecto}</dd>
            <dt>Ubicación</dt><dd>{[s.brief.ubicacion.distrito, s.brief.ubicacion.ciudad].filter(Boolean).join(", ")}</dd>
            <dt>Terreno</dt><dd className="num">{fmt(s.brief.terreno.frente_m)} × {fmt(s.brief.terreno.fondo_m)} m</dd>
            <dt>Área</dt><dd className="num">{fmt(ind.area_terreno_m2)} m²</dd>
            <dt>Niveles</dt><dd className="num">{s.brief.niveles}</dd>
            {s.brief.presupuesto.monto ? (<><dt>Presupuesto</dt><dd className="num">S/ {s.brief.presupuesto.monto.toLocaleString("es-PE")}</dd></>) : null}
            <dt>Estudio de suelos</dt><dd style={{ color: s.brief.terreno.estudio_suelos === "si" ? "var(--ok)" : "var(--pendiente)" }}>{s.brief.terreno.estudio_suelos === "si" ? "Disponible" : "Pendiente"}</dd>
          </dl>
          <button className="enlace" style={{ alignSelf: "flex-start" }} onClick={() => s.set({ pantalla: "entrevista" })}>Editar requerimientos</button>
        </section>
        <section>
          <h2 className="etiqueta">{alt.nombre}</h2>
          <p style={{ margin: 0, fontWeight: 600 }}>{alt.estrategia}</p>
          <p style={{ margin: 0, lineHeight: 1.5, color: "var(--texto-3)" }}>{alt.descripcion}</p>
        </section>
        <section>
          <h2 className="etiqueta">Supuestos del motor</h2>
          <ul className="lista" style={{ fontSize: 12.5, color: "var(--texto-3)" }}>
            {alt.supuestos.map((x) => <li key={x}>{x}</li>)}
          </ul>
        </section>
      </aside>

      <main className="centro">
        <div className="herramientas">
          <div role="group" aria-label="Vista" className="segmentado">
            <button className={s.vista === "3d" ? "activo" : ""} onClick={() => s.set({ vista: "3d" })}>3D</button>
            <button className={s.vista === "planta" ? "activo" : ""} onClick={() => s.set({ vista: "planta" })}>Planta</button>
          </div>
          <div role="group" aria-label="Nivel" className="segmentado">
            {alt.niveles.map((n) => (
              <button key={n.numero} className={s.nivel === n.numero ? "activo" : ""} onClick={() => s.set({ nivel: n.numero })}>{n.nombre}</button>
            ))}
          </div>
          <span style={{ color: "var(--texto-2)", fontSize: 13, flexGrow: 1 }}>
            {alt.estrategia}
          </span>
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 13 }}>
            <input type="checkbox" checked={s.etiquetas} onChange={(e) => s.set({ etiquetas: e.target.checked })} /> Etiquetas de área y costo
          </label>
          {s.vista === "3d" && (
            <div style={{ position: "relative" }}>
              <button className="btn chico" aria-expanded={panelColores} onClick={() => setPanelColores(!panelColores)}>Colores</button>
              {panelColores && <PanelColores c={s.colores} onCambio={(c) => s.set({ colores: c })} onCerrar={() => setPanelColores(false)} />}
            </div>
          )}
        </div>
        <div className="lienzo" style={s.vista === "3d" ? { background: "#f6f4ef" } : undefined}>
          {s.vista === "planta" ? (
            <div style={{ width: "100%", height: "100%", maxWidth: 520, padding: 20, position: "absolute", inset: 0, margin: "0 auto" }}>
              <Planta alt={alt} nivel={nivel} seleccion={s.seleccion} onSeleccion={(id) => s.set({ seleccion: id })} costos={costoPorEspacio} />
            </div>
          ) : (
            <Suspense fallback={<p className="pensando">Cargando vista 3D…</p>}>
              <Vista3D alt={alt} nivelVisible={s.nivel} seleccion={s.seleccion} onSeleccion={(id) => s.set({ seleccion: id })}
                colores={s.colores} etiquetas={s.etiquetas} costos={res} />
            </Suspense>
          )}
        </div>
        <div className="pie">
          <div className="grupo"><span>Cotas en metros</span><span>Áreas en m²</span><span>Áreas a ejes</span></div>
          <div className="grupo num"><span>Motor paramétrico {alt.motor_version}</span><span>Generado en {fmt(alt.tiempo_ms, 1)} ms</span><span>Huella {alt.huella}</span></div>
        </div>
      </main>

      <aside className="lateral der">
        <Inspector alt={alt} />
        <section>
          <h2 className="etiqueta">Indicadores calculados</h2>
          <div className="indicadores">
            <Ind k="Área techada" v={`${fmt(ind.area_techada_m2)} m²`} />
            <Ind k="Área útil" v={`${fmt(ind.area_util_m2)} m²`} />
            <Ind k="Uso público" v={`${fmt(ind.area_comercial_m2)} m²`} />
            <Ind k="Circulación" v={`${fmt(ind.circulacion_pct, 1)} %`} />
            <Ind k="Ambientes con luz" v={`${fmt(ind.ambientes_con_luz_pct, 0)} %`} />
            <Ind k="Ventanas" v={`${fmt(ind.area_ventanas_m2)} m²`} />
          </div>
          <p style={{ margin: 0, fontSize: 12, color: "var(--texto-2)" }}>
            Acceso independiente a niveles superiores: {alt.indicadores.acceso_independiente_superior ? "sí" : "no"}
          </p>
        </section>
        {res && (
          <section>
            <h2 className="etiqueta">Estimación de costos</h2>
            <div className="indicadores">
              <Ind k="Construcción" v={soles(res.totales.construccion)} />
              <Ind k="Por m² techado" v={soles(res.totales.construccion_m2)} />
            </div>
            <p style={{ margin: 0, fontSize: 12, color: "var(--texto-2)", lineHeight: 1.5 }}>Valores oficiales de edificación ({res.fuente.vigencia.toLowerCase()}){res.totales.cotizacion ? " y cotizaciones importadas" : ""}. Referencial, no es presupuesto de obra.</p>
            <button className="enlace" style={{ alignSelf: "flex-start" }} onClick={() => s.set({ pantalla: "costos" })}>Ver desglose y cambiar materiales</button>
          </section>
        )}
        <section>
          <h2 className="etiqueta">Verificaciones preliminares</h2>
          {alt.verificaciones.map((v) => <EstadoFila key={v.id} v={v} />)}
          <p style={{ margin: 0, fontSize: 12, color: "var(--texto-2)" }}>Pasa el cursor sobre una verificación para ver su detalle y evidencia.</p>
        </section>
        <section>
          <button className="btn primario" onClick={onIfc}>Exportar IFC de esta alternativa</button>
        </section>
      </aside>
    </div>
  );
}

const CAMPOS_COLOR: [keyof Colores, string][] = [
  ["muroExt", "Muros exteriores"], ["muroInt", "Muros interiores"], ["losa", "Losas"], ["vidrio", "Vidrios"], ["escalera", "Escalera"],
  ["pisoPublico", "Pisos de uso público"], ["pisoPrivado", "Pisos de uso privado"], ["pisoServicio", "Pisos de servicio"], ["pisoCirculacion", "Pisos de circulación"],
];

function PanelColores({ c, onCambio, onCerrar }: { c: Colores; onCambio: (c: Colores) => void; onCerrar: () => void }) {
  return (
    <div role="dialog" aria-label="Colores del modelo 3D" className="tarjeta" style={{ position: "absolute", top: 38, right: 0, zIndex: 10, width: 280, padding: 14, display: "flex", flexDirection: "column", gap: 8, boxShadow: "0 6px 24px rgba(31,35,40,0.12)" }}>
      <label style={{ fontSize: 12.5, display: "flex", gap: 6, alignItems: "center" }}>
        <input type="checkbox" checked={c.modo === "material"} onChange={(e) => onCambio({ ...c, modo: e.target.checked ? "material" : "personalizado" })} />
        Color de pisos según el material elegido
      </label>
      {CAMPOS_COLOR.filter(([k]) => !(c.modo === "material" && String(k).startsWith("piso"))).map(([k, nombre]) => (
        <label key={k} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: 13 }}>
          {nombre}
          <input type="color" value={c[k] as string} onChange={(e) => onCambio({ ...c, [k]: e.target.value })} style={{ width: 40, height: 26, border: "1px solid var(--borde-fuerte)", padding: 0, background: "none" }} />
        </label>
      ))}
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <button className="enlace" onClick={() => onCambio(coloresBase())}>Restablecer</button>
        <button className="enlace" onClick={onCerrar}>Cerrar</button>
      </div>
    </div>
  );
}

function Ind({ k, v }: { k: string; v: string }) {
  return <div><div className="k">{k}</div><div className="v">{v}</div></div>;
}

function Inspector({ alt }: { alt: Alternativa }) {
  const sel = useArqia((s) => s.seleccion);
  const res = useArqia((s) => s.costos[alt.id]);
  let cuerpo: React.ReactNode = <p style={{ margin: 0, color: "var(--texto-2)", fontSize: 13 }}>Selecciona un ambiente, muro, puerta o ventana en la planta o en el 3D.</p>;
  let titulo = "Ningún elemento";
  for (const n of alt.niveles) {
    const e = n.espacios.find((x) => x.id === sel);
    if (e) {
      titulo = e.nombre;
      cuerpo = (
        <dl className="dl" style={{ gridTemplateColumns: "120px minmax(0,1fr)" }}>
          <dt>Clase IFC</dt><dd className="num">IfcSpace</dd>
          <dt>Identificador</dt><dd className="num">{e.id}</dd>
          <dt>Nivel</dt><dd style={{ whiteSpace: "nowrap" }}>{n.nombre} <span className="num" style={{ color: "var(--texto-2)" }}>(+{fmt(n.cota_m)})</span></dd>
          <dt>Función</dt><dd>{e.funcion}</dd>
          <dt>Área</dt><dd className="num">{fmt(e.area_m2)} m²</dd>
          {(() => { const c = res?.espacios.find((x) => x.id === e.id); return c ? (<><dt>Pisos y acabados</dt><dd>Pisos {c.categorias.pisos}, revestimientos {c.categorias.revestimientos}</dd><dt>Costo estimado</dt><dd className="num">{soles(c.costo)} <span style={{ color: "var(--texto-2)" }}>({fmt(c.valor_m2)} por m²)</span></dd></>) : null; })()}
          {e.area_objetivo_m2 ? (<><dt>Área objetivo</dt><dd className="num">{fmt(e.area_objetivo_m2)} m²</dd></>) : null}
          <dt>Ancho mínimo</dt><dd className="num">{fmt(e.ancho_m)} m</dd>
          <dt>Altura libre</dt><dd className="num">{fmt(n.altura_m - 0.2)} m</dd>
          <dt>Luz natural</dt><dd>{e.luz_natural ? "Sí" : "No"}</dd>
          {e.acceso_desde ? (<><dt>Acceso</dt><dd>{e.acceso_directo ? "Directo desde " : "A través de "}{e.acceso_desde}</dd></>) : null}
        </dl>
      );
    }
    const m = n.muros.find((x) => x.id === sel);
    if (m) {
      const L = Math.hypot(m.b[0] - m.a[0], m.b[1] - m.a[1]);
      titulo = `Muro ${m.exterior ? "exterior" : "interior"}`;
      cuerpo = (
        <dl className="dl" style={{ gridTemplateColumns: "120px minmax(0,1fr)" }}>
          <dt>Clase IFC</dt><dd className="num">IfcWall</dd>
          <dt>Identificador</dt><dd className="num">{m.id}</dd>
          <dt>Nivel</dt><dd>{n.nombre}</dd>
          <dt>Longitud</dt><dd className="num">{fmt(L)} m</dd>
          <dt>Espesor</dt><dd className="num">{fmt(m.espesor_m)} m</dd>
          <dt>Altura</dt><dd className="num">{fmt(m.altura_m)} m</dd>
          <dt>Material</dt><dd>{m.material}</dd>
          <dt>Vanos</dt><dd className="num">{n.vanos.filter((v) => v.muro_id === m.id).length}</dd>
        </dl>
      );
    }
    const v = n.vanos.find((x) => x.id === sel);
    if (v) {
      titulo = v.nombre;
      cuerpo = (
        <dl className="dl" style={{ gridTemplateColumns: "120px minmax(0,1fr)" }}>
          <dt>Clase IFC</dt><dd className="num">{v.tipo === "puerta" ? "IfcDoor" : "IfcWindow"}</dd>
          <dt>Identificador</dt><dd className="num">{v.id}</dd>
          <dt>Muro anfitrión</dt><dd className="num">{v.muro_id}</dd>
          <dt>Ancho</dt><dd className="num">{fmt(v.ancho_m)} m</dd>
          <dt>Alto</dt><dd className="num">{fmt(v.alto_m)} m</dd>
          <dt>Alféizar</dt><dd className="num">{fmt(v.alfeizar_m)} m</dd>
        </dl>
      );
    }
    const es = n.escaleras.find((x) => x.id === sel);
    if (es) {
      titulo = "Escalera";
      cuerpo = (
        <dl className="dl" style={{ gridTemplateColumns: "120px minmax(0,1fr)" }}>
          <dt>Clase IFC</dt><dd className="num">IfcStair</dd>
          <dt>Identificador</dt><dd className="num">{es.id}</dd>
          <dt>Contrapasos</dt><dd className="num">{es.numero_contrapasos} de {fmt(es.contrapaso_m, 3)} m</dd>
          <dt>Paso</dt><dd className="num">{fmt(es.paso_m)} m</dd>
        </dl>
      );
    }
  }
  return (
    <section>
      <h2 className="etiqueta">Elemento seleccionado</h2>
      <p style={{ margin: 0, fontSize: 17, fontWeight: 600 }}>{titulo}</p>
      {cuerpo}
    </section>
  );
}

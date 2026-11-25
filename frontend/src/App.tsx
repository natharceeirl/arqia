import { useEffect, useState } from "react";
import { api } from "./api";
import Comparador from "./Comparador";
import Costos from "./Costos";
import { useCostos } from "./useCostos";
import { useRef } from "react";
import Entrevista from "./Entrevista";
import Ficha from "./Ficha";
import { fmt, useArqia } from "./store";
import type { VerificacionIFC } from "./tipos";
import Trabajo from "./Trabajo";

function Marca({ onClick }: { onClick: () => void }) {
  return (
    <button className="marca" onClick={onClick} aria-label="Ir al inicio">
      <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true"><rect x="1" y="1" width="20" height="20" fill="none" stroke="#1F2328" strokeWidth="2" /><path d="M1 11H11V21" fill="none" stroke="#1F2328" strokeWidth="2" /></svg>
      <span>ARQIA</span>
    </button>
  );
}

export default function App() {
  const s = useArqia();
  useCostos();
  const archivoPaquete = useRef<HTMLInputElement>(null);
  const [aviso, setAviso] = useState<string | null>(null);

  function descargar(nombre: string, b64: string, tipo: string) {
    const bin = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const url = URL.createObjectURL(new Blob([bin], { type: tipo }));
    const a = document.createElement("a");
    a.href = url; a.download = nombre; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  async function exportarPaquete() {
    const elegida = s.elegida ?? s.activa;
    try {
      const r = await api.exportarPaquete({ brief: s.brief, alternativas: s.alternativas, elegida, costos: s.costosEntrada,
        decisiones: s.decisiones, notas_cliente: s.notasCliente, colores: s.colores });
      descargar(r.nombre, r.archivo_base64, "application/zip");
      s.decidir(`Se exportó el paquete ${r.nombre} con la alternativa ${elegida}.`);
    } catch (e) { setAviso(`No se pudo exportar el paquete: ${(e as Error).message}`); }
  }

  async function importarPaquete(f: File) {
    try {
      const b64: string = await new Promise((ok, mal) => { const r = new FileReader(); r.onload = () => ok(String(r.result).split(",")[1] ?? ""); r.onerror = () => mal(r.error); r.readAsDataURL(f); });
      const d = await api.importarPaquete(f.name, b64);
      const entrada = d.costos?.entrada ?? null;
      s.set({
        pantalla: "trabajo", brief: d.brief, alternativas: d.alternativas, activa: d.alternativa_elegida, elegida: d.alternativa_elegida,
        decisiones: [...(d.decisiones ?? []), { fecha: new Date().toLocaleString("es-PE"), texto: `Se importó el paquete ${f.name}${d.reproducible ? "; el diseño se reprodujo idéntico" : ""}.` }],
        notasCliente: d.notas_cliente ?? "", colores: { ...s.colores, ...(d.colores ?? {}) }, esDemo: false, explicacion: null, seleccion: null, nivel: 1,
        ...(entrada ? { costosEntrada: { ...s.costosEntrada, ...entrada } } : {}),
      });
      setAviso(d.reproducible ? "Paquete importado. ARQIA regeneró el diseño y coincide exactamente con el archivo." : "Paquete importado. Aviso: el diseño regenerado no coincide con el guardado.");
    } catch (e) { setAviso(`No se pudo importar: ${(e as Error).message}`); }
    finally { if (archivoPaquete.current) archivoPaquete.current.value = ""; }
  }
  const [ifc, setIfc] = useState<null | { cargando: boolean; nombre?: string; verif?: VerificacionIFC; url?: string; error?: string }>(null);
  const [asistente, setAsistente] = useState<boolean | null>(null);
  useEffect(() => { api.salud().then((r) => setAsistente(r.asistente)).catch(() => setAsistente(false)); }, []);

  async function abrirDemo() {
    const d = await api.demo();
    s.set({
      pantalla: "trabajo", brief: d.brief, alternativas: d.alternativas, avisos: d.avisos, historial: d.conversacion,
      avisosMostrados: d.avisos.map((a) => a.id), activa: "A", nivel: 1, vista: "planta", seleccion: null, explicacion: null,
      elegida: null, decisiones: [{ fecha: new Date().toLocaleString("es-PE"), texto: "Se abrió el caso de demostración: local comercial en Sachaca." }],
      esDemo: true, entrevista: null, pendiente: null,
    });
  }

  async function exportarIfc() {
    const alt = s.alternativas.find((a) => a.id === (s.pantalla === "ficha" ? s.elegida ?? s.activa : s.activa));
    if (!alt) return;
    setIfc({ cargando: true });
    try {
      const r = await api.ifc(s.brief, alt, s.costosEntrada);
      const bin = Uint8Array.from(atob(r.archivo_base64), (c) => c.charCodeAt(0));
      const url = URL.createObjectURL(new Blob([bin], { type: "application/x-step" }));
      setIfc({ cargando: false, nombre: r.nombre, verif: r.verificacion, url });
      s.decidir(`Se exportó el IFC de la ${alt.nombre} (${r.verificacion.valido ? "archivo válido" : "con observaciones"}).`);
    } catch (e) {
      setIfc({ cargando: false, error: (e as Error).message });
    }
  }

  const hayAlts = s.alternativas.length > 0;
  return (
    <div className="app">
      <header className="encabezado">
        <Marca onClick={() => s.set({ pantalla: "inicio" })} />
        {s.pantalla !== "inicio" && (
          <div className="proyecto" title={s.esDemo ? "Caso de demostración" : "Guardado en este navegador"}>
            <span style={{ fontWeight: 500 }}>{s.brief.nombre_proyecto !== "Proyecto sin nombre" ? s.brief.nombre_proyecto : s.brief.tipo_proyecto ?? "Nuevo proyecto"}</span>
            {s.esDemo && <small>Demostración</small>}
          </div>
        )}
        {s.pantalla === "entrevista" ? (
          <ol className="etapas" aria-label="Etapas">
            <li className="activa"><b>1</b>Requerimientos</li><li>2 Alternativas</li><li>3 Comparación</li><li>4 Ficha comercial</li>
          </ol>
        ) : s.pantalla !== "inicio" ? (
          <nav className="pestanas" aria-label="Alternativas">
            <button onClick={() => s.set({ pantalla: "entrevista" })}>Requerimientos</button>
            {s.alternativas.map((a) => (
              <button key={a.id} className={s.pantalla === "trabajo" && s.activa === a.id ? "activa" : ""} onClick={() => s.set({ pantalla: "trabajo", activa: a.id, seleccion: null })}>
                {a.nombre}
              </button>
            ))}
            <button className={s.pantalla === "costos" ? "activa" : ""} disabled={!hayAlts} onClick={() => s.set({ pantalla: "costos" })}>Costos</button>
            <button className={s.pantalla === "comparador" ? "activa" : ""} disabled={!hayAlts} onClick={() => s.set({ pantalla: "comparador" })}>Comparador</button>
            <button className={s.pantalla === "ficha" ? "activa" : ""} disabled={!hayAlts} onClick={() => s.set({ pantalla: "ficha" })}>Ficha comercial</button>
          </nav>
        ) : <div style={{ flexGrow: 1 }} />}
        {s.pantalla !== "inicio" && hayAlts && (
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn" onClick={exportarPaquete} title="Guarda el modelo IFC y los datos del proyecto en un archivo .arqia">Guardar</button>
            <button className="btn primario" onClick={exportarIfc}>Exportar IFC</button>
          </div>
        )}
      </header>

      {s.pantalla === "inicio" && (
        <div className="inicio">
          <div className="caja">
            <p className="etiqueta">Hackathon BIM + IA UNSA 2026, Reto 1</p>
            <h1>Del brief del cliente a propuestas arquitectónicas comparables, con información BIM verificable.</h1>
            <p>ARQIA entrevista al cliente, genera tres alternativas con un motor paramétrico determinista, las compara con indicadores calculados y exporta el modelo en IFC.</p>
            <div className="pasos">
              <div><b>1. Entrevista</b>Preguntas guiadas y resumen editable, con avisos del lugar.</div>
              <div><b>2. Alternativas</b>Tres estrategias en planta y 3D, en menos de un segundo.</div>
              <div><b>3. Comparación</b>Indicadores calculados y verificaciones con su estado.</div>
              <div><b>4. Ficha e IFC</b>Ficha comercial imprimible y modelo IFC4 verificado.</div>
            </div>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <button className="btn primario" style={{ minHeight: 44 }} onClick={() => (s.historial.length && !s.esDemo ? s.set({ pantalla: hayAlts ? "trabajo" : "entrevista" }) : s.reiniciar())}>
                {s.historial.length && !s.esDemo ? "Continuar proyecto" : "Nuevo proyecto"}
              </button>
              {s.historial.length > 0 && !s.esDemo && <button className="btn" style={{ minHeight: 44 }} onClick={() => s.reiniciar()}>Empezar de nuevo</button>}
              <button className="btn" style={{ minHeight: 44 }} onClick={abrirDemo}>Abrir caso de demostración</button>
              <button className="btn" style={{ minHeight: 44 }} onClick={() => archivoPaquete.current?.click()}>Abrir proyecto .arqia</button>
            </div>
            <p style={{ fontSize: 12, color: "var(--texto-2)" }}>
              {asistente === null ? "Comprobando el asistente…" : asistente ? "Asistente con IA disponible." : "Asistente con IA no disponible: la entrevista funcionará como formulario guiado."}
            </p>
          </div>
        </div>
      )}
      {s.pantalla === "entrevista" && <Entrevista />}
      {s.pantalla === "trabajo" && hayAlts && <Trabajo onIfc={exportarIfc} />}
      {s.pantalla === "costos" && hayAlts && <Costos />}
      {s.pantalla === "comparador" && <Comparador />}
      <input ref={archivoPaquete} type="file" accept=".arqia,.zip" style={{ display: "none" }} onChange={(e) => e.target.files?.[0] && importarPaquete(e.target.files[0])} />
      {aviso && (
        <div role="status" className="tarjeta" style={{ position: "fixed", bottom: 20, left: "50%", transform: "translateX(-50%)", padding: "12px 16px", zIndex: 30, display: "flex", gap: 14, alignItems: "center", boxShadow: "0 6px 24px rgba(31,35,40,0.12)" }}>
          <span style={{ fontSize: 13 }}>{aviso}</span><button className="enlace" onClick={() => setAviso(null)}>Cerrar</button>
        </div>
      )}
      {s.pantalla === "ficha" && <Ficha onIfc={exportarIfc} />}

      {ifc && (
        <div className="modal-fondo" role="dialog" aria-modal="true" aria-label="Exportación IFC" onClick={() => setIfc(null)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2 style={{ margin: 0, fontSize: 18 }}>Exportación IFC</h2>
            {ifc.cargando && <p className="pensando">Generando y verificando el archivo…</p>}
            {ifc.error && <p className="error">{ifc.error}</p>}
            {ifc.verif && (
              <>
                <div className="estado">
                  <span className={`punto p-${ifc.verif.valido ? "cumple" : "no_cumple"}`} aria-hidden="true" />
                  <span className="txt">Validación contra el esquema {ifc.verif.esquema}</span>
                  <span className={ifc.verif.valido ? "e-cumple" : "e-no_cumple"}>{ifc.verif.valido ? "Válido" : "Con errores"}</span>
                </div>
                <div className="estado">
                  <span className={`punto p-${ifc.verif.coincide_con_modelo ? "cumple" : "no_cumple"}`} aria-hidden="true" />
                  <span className="txt">Elementos y áreas coinciden con el modelo de ARQIA</span>
                  <span className={ifc.verif.coincide_con_modelo ? "e-cumple" : "e-no_cumple"}>{ifc.verif.coincide_con_modelo ? "Coinciden" : "Difieren"}</span>
                </div>
                <table className="tabla">
                  <thead><tr><th>Clase IFC</th><th>En el archivo</th><th>En el modelo</th></tr></thead>
                  <tbody>
                    {Object.entries(ifc.verif.elementos).map(([k, v]) => (
                      <tr key={k}><td className="num">{k}</td><td className="num">{v}</td><td className="num">{ifc.verif!.esperado[k] ?? "—"}</td></tr>
                    ))}
                    <tr><td>Área de IfcSpace</td><td className="num">{fmt(ifc.verif.area_espacios_ifc_m2)} m²</td><td className="num">{fmt(ifc.verif.area_espacios_modelo_m2)} m²</td></tr>
                  </tbody>
                </table>
                <p style={{ margin: 0, fontSize: 12.5, color: "var(--texto-2)", lineHeight: 1.5 }}>
                  El archivo se abre en visores IFC y en programas BIM como Revit, Archicad, BIMvision o Bonsai. Incluye niveles, espacios,
                  muros con vanos, puertas, ventanas, losas, escalera, propiedades de ARQIA (identificador, huella y fuente del dato) y la
                  estimación de costos como IfcCostSchedule.
                </p>
                <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                  <button className="btn" onClick={() => setIfc(null)}>Cerrar</button>
                  <a className="btn primario" href={ifc.url} download={ifc.nombre}>Descargar archivo IFC ({fmt(ifc.verif.tamano_kb, 0)} KB)</a>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

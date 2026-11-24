import type { Alternativa, Aviso, Brief, EstadoEntrevista, Explicacion, Mensaje, VerificacionIFC } from "./tipos";

// En producción la API vive en la misma URL. Si la interfaz se publica aparte (por ejemplo en Vercel),
// VITE_API_URL apunta al servidor de Render.
const BASE = (import.meta as any).env?.VITE_API_URL?.replace(/\/$/, "") ?? "";

async function post<T>(ruta: string, cuerpo: unknown): Promise<T> {
  const r = await fetch(`${BASE}${ruta}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cuerpo) });
  if (!r.ok) {
    let detalle = "";
    try { detalle = JSON.stringify((await r.json()).detail); } catch { /* sin cuerpo */ }
    throw new Error(`Error ${r.status} ${detalle}`);
  }
  return r.json();
}

export interface RespuestaTurno {
  modo: "asistente" | "formulario";
  comentario: string | null; pregunta: string | null; contexto: string | null; opciones: string[];
  campo: string | null; tipo_entrada: string | null; avisos_nuevos: string[];
  brief: Brief; errores: string[]; estado: EstadoEntrevista; avisos: Aviso[];
}

export const api = {
  salud: () => fetch(`${BASE}/api/salud`).then((r) => r.json()) as Promise<{ ok: boolean; asistente: boolean; motor: string }>,
  turno: (brief: Brief, historial: Mensaje[], mensaje: string | null, avisos_mostrados: string[]) =>
    post<RespuestaTurno>("/api/entrevista/turno", { brief, historial, mensaje, avisos_mostrados }),
  aplicar: (brief: Brief, cambios: Record<string, unknown>) =>
    post<{ brief: Brief; errores: string[]; estado: EstadoEntrevista; avisos: Aviso[] }>("/api/brief/aplicar", { brief, cambios }),
  alternativas: (brief: Brief) => post<{ brief: Brief; alternativas: Alternativa[]; avisos: Aviso[] }>("/api/alternativas", { brief }),
  explicar: (brief: Brief, alternativas: Alternativa[]) => post<Explicacion>("/api/comparacion/explicar", { brief, alternativas }),
  ifc: (brief: Brief, alternativa: Alternativa) =>
    post<{ nombre: string; verificacion: VerificacionIFC; archivo_base64: string }>("/api/ifc", { brief, alternativa }),
  demo: () =>
    fetch(`${BASE}/api/demo`).then((r) => r.json()) as Promise<{ brief: Brief; alternativas: Alternativa[]; avisos: Aviso[]; conversacion: Mensaje[] }>,
};

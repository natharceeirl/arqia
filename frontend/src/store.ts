import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Alternativa, Aviso, Brief, Colores, Decision, EntradaCostos, EstadoEntrevista, Explicacion, Mensaje, ResultadoCostos, TablaVuoe } from "./tipos";

export type Pantalla = "inicio" | "entrevista" | "trabajo" | "costos" | "comparador" | "ficha";

export const entradaVacia = (): EntradaCostos => ({ especificacion: {}, por_ambiente: {}, cotizacion: [], reemplazos: [], terreno_valor_m2: null, terreno_fuente: null });

export const coloresBase = (): Colores => ({
  modo: "material", muroExt: "#e9e4da", muroInt: "#f4f1ea", losa: "#d8d3c9", vidrio: "#9fb9c4", escalera: "#c9c3b7",
  pisoPublico: "#ead7cc", pisoPrivado: "#d9e2e5", pisoServicio: "#e3dfd6", pisoCirculacion: "#f2efe8",
});

/** Color de referencia del piso según la categoría oficial elegida (para el modo "según material"). */
export const COLOR_PISO: Record<string, string> = {
  A: "#ebe8e2", B: "#c9a27c", C: "#b48a63", D: "#d9cfc1", E: "#a98c6b", F: "#cfc8bc", G: "#bcc5c3", H: "#b8b4ad", I: "#9c8b74",
};

export const briefVacio = (): Brief => ({
  nombre_proyecto: "Proyecto sin nombre",
  tipo_proyecto: null,
  ubicacion: { distrito: null, ciudad: "Arequipa", pais: "Perú", contexto: [] },
  terreno: { frente_m: null, fondo_m: null, retiro_frontal_m: null, estudio_suelos: null },
  niveles: null,
  altura_piso_m: 3,
  ambientes: [],
  presupuesto: { moneda: "PEN", monto: null, referencial: true },
  preferencias: { luz_natural: null, estilo: null, acceso_independiente_n2: null, notas: null },
  origen: {},
});

interface Estado {
  pantalla: Pantalla;
  brief: Brief;
  historial: Mensaje[];
  avisos: Aviso[];
  avisosMostrados: string[];
  entrevista: EstadoEntrevista | null;
  pendiente: { pregunta: string | null; opciones: string[]; campo: string | null; tipo_entrada: string | null } | null;
  modo: "asistente" | "formulario" | null;
  alternativas: Alternativa[];
  activa: string;
  nivel: number;
  vista: "planta" | "3d";
  seleccion: string | null;
  explicacion: Explicacion | null;
  elegida: string | null;
  decisiones: Decision[];
  notasCliente: string;
  esDemo: boolean;
  costosEntrada: EntradaCostos;
  costos: Record<string, ResultadoCostos>;
  vuoe: TablaVuoe | null;
  colores: Colores;
  etiquetas: boolean;
  set: (p: Partial<Estado>) => void;
  decidir: (texto: string) => void;
  reiniciar: () => void;
}

export const useArqia = create<Estado>()(
  persist(
    (set) => ({
      pantalla: "inicio",
      brief: briefVacio(),
      historial: [],
      avisos: [],
      avisosMostrados: [],
      entrevista: null,
      pendiente: null,
      modo: null,
      alternativas: [],
      activa: "A",
      nivel: 1,
      vista: "planta",
      seleccion: null,
      explicacion: null,
      elegida: null,
      decisiones: [],
      notasCliente: "",
      esDemo: false,
      costosEntrada: entradaVacia(),
      costos: {},
      vuoe: null,
      colores: coloresBase(),
      etiquetas: true,
      set: (p) => set(p),
      decidir: (texto) =>
        set((s) => ({ decisiones: [...s.decisiones, { fecha: new Date().toLocaleString("es-PE"), texto }] })),
      reiniciar: () =>
        set({
          pantalla: "entrevista", brief: briefVacio(), historial: [], avisos: [], avisosMostrados: [], entrevista: null,
          pendiente: null, modo: null, alternativas: [], activa: "A", nivel: 1, vista: "planta", seleccion: null,
          explicacion: null, elegida: null, decisiones: [], notasCliente: "", esDemo: false,
          costosEntrada: entradaVacia(), costos: {}, colores: coloresBase(),
        }),
    }),
    {
      name: "arqia-proyecto",
      partialize: (s) => {
        const { set: _s, decidir: _d, reiniciar: _r, vuoe: _v, ...resto } = s;
        return resto;
      },
    },
  ),
);

export const fmt = (v: number | null | undefined, d = 2) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : v.toLocaleString("es-PE", { minimumFractionDigits: d, maximumFractionDigits: d });

export const soles = (v: number | null | undefined, d = 0) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : `S/ ${v.toLocaleString("es-PE", { minimumFractionDigits: d, maximumFractionDigits: d })}`;

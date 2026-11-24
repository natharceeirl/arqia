import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Alternativa, Aviso, Brief, Decision, EstadoEntrevista, Explicacion, Mensaje } from "./tipos";

export type Pantalla = "inicio" | "entrevista" | "trabajo" | "comparador" | "ficha";

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
      set: (p) => set(p),
      decidir: (texto) =>
        set((s) => ({ decisiones: [...s.decisiones, { fecha: new Date().toLocaleString("es-PE"), texto }] })),
      reiniciar: () =>
        set({
          pantalla: "entrevista", brief: briefVacio(), historial: [], avisos: [], avisosMostrados: [], entrevista: null,
          pendiente: null, modo: null, alternativas: [], activa: "A", nivel: 1, vista: "planta", seleccion: null,
          explicacion: null, elegida: null, decisiones: [], notasCliente: "", esDemo: false,
        }),
    }),
    {
      name: "arqia-proyecto",
      partialize: (s) => {
        const { set: _s, decidir: _d, reiniciar: _r, ...resto } = s;
        return resto;
      },
    },
  ),
);

export const fmt = (v: number | null | undefined, d = 2) =>
  v === null || v === undefined || Number.isNaN(v) ? "—" : v.toLocaleString("es-PE", { minimumFractionDigits: d, maximumFractionDigits: d });

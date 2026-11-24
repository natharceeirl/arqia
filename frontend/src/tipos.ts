export type Punto = [number, number];
export type TipoAmbiente = "publico" | "privado" | "servicio";
export type Funcion = TipoAmbiente | "circulacion" | "escalera" | "patio";
export type Estado = "cumple" | "no_cumple" | "pendiente" | "revision_profesional";

export interface Ambiente {
  nombre: string;
  nivel: number;
  tipo: TipoAmbiente;
  area_objetivo_m2: number | null;
}

export interface Brief {
  nombre_proyecto: string;
  tipo_proyecto: string | null;
  ubicacion: { distrito: string | null; ciudad: string | null; pais: string; contexto: string[] };
  terreno: { frente_m: number | null; fondo_m: number | null; retiro_frontal_m: number | null; estudio_suelos: "si" | "no" | "desconoce" | null };
  niveles: number | null;
  altura_piso_m: number;
  ambientes: Ambiente[];
  presupuesto: { moneda: string; monto: number | null; referencial: boolean };
  preferencias: { luz_natural: "baja" | "media" | "alta" | null; estilo: string | null; acceso_independiente_n2: boolean | null; notas: string | null };
  origen: Record<string, string>;
}

export interface Espacio {
  id: string; nombre: string; funcion: Funcion; poligono: Punto[]; area_m2: number; ancho_m: number; largo_m: number;
  area_objetivo_m2: number | null; luz_natural: boolean; acceso_directo: boolean; acceso_desde: string | null;
}
export interface Muro {
  id: string; a: Punto; b: Punto; espesor_m: number; altura_m: number; exterior: boolean; material: string;
  espacios: string[]; piezas: [number, number, number, number][];
}
export interface Vano {
  id: string; tipo: "puerta" | "ventana"; nombre: string; muro_id: string; centro: Punto; ancho_m: number; alto_m: number; alfeizar_m: number; entre: string[];
}
export interface Losa { id: string; nombre: string; poligono: Punto[]; vacios: Punto[][]; espesor_m: number; cota_m: number; area_m2: number }
export interface Peldano { x0: number; y0: number; x1: number; y1: number; z0: number; z1: number }
export interface Escalera { id: string; nivel_desde: number; nivel_hasta: number; huella: Punto[]; peldanos: Peldano[]; contrapaso_m: number; paso_m: number; numero_contrapasos: number }
export interface Nivel { numero: number; nombre: string; cota_m: number; altura_m: number; espacios: Espacio[]; muros: Muro[]; vanos: Vano[]; losas: Losa[]; escaleras: Escalera[] }
export interface Verificacion { id: string; titulo: string; estado: Estado; detalle: string; evidencia: string[]; fuente: string | null }
export interface Alternativa {
  id: string; nombre: string; estrategia: string; descripcion: string; huella: string; motor_version: string; tiempo_ms: number;
  terreno: Punto[]; niveles: Nivel[]; indicadores: Record<string, number | boolean | string>; verificaciones: Verificacion[]; supuestos: string[];
}
export interface Aviso { id: string; titulo: string; texto: string; referencia: string; url: string | null; revisado_por: string; tema: string }

export interface Mensaje { rol: "usuario" | "asistente"; texto: string; opciones?: string[]; avisos?: string[]; contexto?: string | null }

export interface EstadoEntrevista {
  temas: { id: string; nombre: string; completo: boolean; faltan: string[] }[];
  tema_actual: string | null; faltan_obligatorios: string[]; listo_para_generar: boolean; completos: number; total: number;
}

export interface Explicacion {
  resumen: string;
  por_alternativa: { id: string; ventajas: string[]; desventajas: string[] }[];
  recomendacion: { id: string; motivo: string };
  fuente: "reglas" | "asistente";
  descartes_verificador?: string[];
}

export interface VerificacionIFC {
  esquema: string; valido: boolean; errores: string[]; elementos: Record<string, number>; esperado: Record<string, number>;
  area_espacios_ifc_m2: number; area_espacios_modelo_m2: number; coincide_con_modelo: boolean; tamano_kb: number;
}

export interface Decision { fecha: string; texto: string }

import { useEffect, useRef } from "react";
import { api } from "./api";
import { useArqia } from "./store";

/** Recalcula los costos de todas las alternativas en el servidor cuando cambian los materiales o el diseño. */
export function useCostos() {
  const alternativas = useArqia((s) => s.alternativas);
  const entrada = useArqia((s) => s.costosEntrada);
  const vuoe = useArqia((s) => s.vuoe);
  const set = useArqia((s) => s.set);
  const turno = useRef(0);
  useEffect(() => {
    if (!vuoe) api.vuoe().then((t) => set({ vuoe: t })).catch(() => undefined);
  }, [vuoe, set]);
  useEffect(() => {
    if (!alternativas.length) return;
    const n = ++turno.current;
    const t = setTimeout(async () => {
      try {
        const res = await Promise.all(alternativas.map((a) => api.costos(a, entrada)));
        if (n === turno.current) set({ costos: Object.fromEntries(res.map((r, i) => [alternativas[i].id, r])) });
      } catch { /* se mantiene el último cálculo válido */ }
    }, 150);
    return () => clearTimeout(t);
  }, [alternativas, entrada, set]);
}

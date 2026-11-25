import type { Alternativa, Funcion, Nivel } from "./tipos";

const RELLENO: Record<Funcion, string> = {
  publico: "#f3e3da",
  privado: "#e6ecee",
  servicio: "#ece9e2",
  circulacion: "#fbfaf7",
  escalera: "#e2ded6",
  patio: "#dfe9dc",
};

interface Props {
  alt: Alternativa;
  nivel: Nivel;
  seleccion?: string | null;
  onSeleccion?: (id: string) => void;
  escala?: number;
  etiquetas?: boolean;
  cotas?: boolean;
  ajustar?: boolean; // true: alto automático según el ancho
  costos?: Record<string, number>; // costo por id de espacio, para la etiqueta
}

/** Planta 2D en SVG generada desde el mismo modelo que el 3D y el IFC. Unidades: metros. */
export default function Planta({ alt, nivel, seleccion, onSeleccion, escala = 30, etiquetas = true, cotas = true, ajustar = false, costos }: Props) {
  const xs = alt.terreno.map((p) => p[0]);
  const ys = alt.terreno.map((p) => p[1]);
  const W = Math.max(...xs), D = Math.max(...ys);
  const m = cotas ? 1.6 : 0.4;
  const s = escala;
  const X = (x: number) => (x + m) * s;
  const Y = (y: number) => (y + m) * s;
  const ancho = (W + 2 * m) * s, alto = (D + 2 * m) * s;
  const centro = (pts: [number, number][]) => {
    // centro del rectángulo mayor contenido aproximado: promedio ponderado simple
    const cx = pts.reduce((a, p) => a + p[0], 0) / pts.length;
    const cy = pts.reduce((a, p) => a + p[1], 0) / pts.length;
    return [cx, cy];
  };
  const etiquetaEn = (e: Nivel["espacios"][number]) => {
    if (e.poligono.length === 4) return centro(e.poligono);
    // forma en L: usar la parte rectangular mayor
    const bx = Math.min(...e.poligono.map((p) => p[0])), bX = Math.max(...e.poligono.map((p) => p[0]));
    const by = Math.min(...e.poligono.map((p) => p[1])), bY = Math.max(...e.poligono.map((p) => p[1]));
    const cand: [number, number][] = [];
    for (let i = 1; i < 10; i++) for (let j = 1; j < 10; j++) cand.push([bx + ((bX - bx) * i) / 10, by + ((bY - by) * j) / 10]);
    const dentro = cand.filter((c) => puntoEnPoligono(c, e.poligono));
    const lejos = dentro.sort((a, b) => distBorde(b, e.poligono) - distBorde(a, e.poligono))[0];
    return lejos ?? centro(e.poligono);
  };

  return (
    <svg viewBox={`0 0 ${ancho} ${alto}`} style={ajustar ? { width: "100%", height: "auto", display: "block" } : { width: "100%", height: "100%" }} role="img" aria-label={`Planta del ${nivel.nombre}, ${alt.nombre}`}>
      {nivel.espacios.map((e) => {
        const sel = seleccion === e.id;
        return (
          <g key={e.id} className="espacio" onClick={() => onSeleccion?.(e.id)}>
            <polygon
              points={e.poligono.map((p) => `${X(p[0])},${Y(p[1])}`).join(" ")}
              fill={sel ? "var(--acento)" : RELLENO[e.funcion]}
              fillOpacity={sel ? 0.14 : 1}
              stroke={sel ? "var(--acento)" : "none"}
              strokeWidth={sel ? 2 : 0}
            />
          </g>
        );
      })}
      {nivel.escaleras.map((es) => (
        <g key={es.id} stroke="#8a8d93" strokeWidth={0.8}>
          {es.peldanos.map((p, i) => (
            <rect key={i} x={X(p.x0)} y={Y(p.y0)} width={(p.x1 - p.x0) * s} height={(p.y1 - p.y0) * s} fill="none" />
          ))}
        </g>
      ))}
      {nivel.numero > 1 &&
        nivel.espacios.filter((e) => e.funcion === "escalera").map((e) => (
          <text key={e.id + "l"} x={X(centro(e.poligono)[0])} y={Y(e.poligono[2][1]) - 8} fontSize={10} textAnchor="middle" fill="#5e6168">llegada</text>
        ))}
      {nivel.espacios.filter((e) => e.funcion === "patio").map((e) => (
        <line key={e.id + "x"} x1={X(e.poligono[0][0])} y1={Y(e.poligono[0][1])} x2={X(e.poligono[2][0])} y2={Y(e.poligono[2][1])} stroke="#9fb59a" strokeWidth={1} />
      ))}
      {/* muros: solo tramos de altura completa; los vanos quedan como aberturas */}
      {nivel.muros.map((mu) => {
        const [ax, ay] = mu.a, [bx, by] = mu.b;
        const L = Math.hypot(bx - ax, by - ay);
        const ux = (bx - ax) / L, uy = (by - ay) / L;
        return (
          <g key={mu.id} onClick={() => onSeleccion?.(mu.id)} style={{ cursor: "pointer" }}>
            {mu.piezas.filter((p) => p[2] === 0 && p[3] >= mu.altura_m - 1e-3).map((p, i) => (
              <line key={i} x1={X(ax + ux * p[0])} y1={Y(ay + uy * p[0])} x2={X(ax + ux * p[1])} y2={Y(ay + uy * p[1])}
                stroke={seleccion === mu.id ? "var(--acento)" : "#1f2328"} strokeWidth={mu.espesor_m * s} strokeLinecap="butt" />
            ))}
          </g>
        );
      })}
      {nivel.vanos.map((v) => {
        const mu = nivel.muros.find((m) => m.id === v.muro_id);
        if (!mu) return null;
        const [ax, ay] = mu.a, [bx, by] = mu.b;
        const L = Math.hypot(bx - ax, by - ay);
        const ux = (bx - ax) / L, uy = (by - ay) / L;
        const x0 = v.centro[0] - (ux * v.ancho_m) / 2, y0 = v.centro[1] - (uy * v.ancho_m) / 2;
        const x1 = v.centro[0] + (ux * v.ancho_m) / 2, y1 = v.centro[1] + (uy * v.ancho_m) / 2;
        const sel = seleccion === v.id;
        if (v.tipo === "ventana") {
          const nx = -uy * (mu.espesor_m / 2), ny = ux * (mu.espesor_m / 2);
          return (
            <g key={v.id} onClick={() => onSeleccion?.(v.id)} style={{ cursor: "pointer" }} stroke={sel ? "var(--acento)" : "#1f2328"} strokeWidth={1}>
              <line x1={X(x0 + nx)} y1={Y(y0 + ny)} x2={X(x1 + nx)} y2={Y(y1 + ny)} />
              <line x1={X(x0 - nx)} y1={Y(y0 - ny)} x2={X(x1 - nx)} y2={Y(y1 - ny)} />
              <line x1={X(x0)} y1={Y(y0)} x2={X(x1)} y2={Y(y1)} strokeWidth={0.6} />
            </g>
          );
        }
        // puerta: hoja y arco de giro
        const nx = -uy, ny = ux;
        const r = v.ancho_m;
        const hx = x0 + nx * r, hy = y0 + ny * r;
        return (
          <g key={v.id} onClick={() => onSeleccion?.(v.id)} style={{ cursor: "pointer" }} stroke={sel ? "var(--acento)" : "#5e6168"} fill="none" strokeWidth={0.9}>
            <line x1={X(x0)} y1={Y(y0)} x2={X(hx)} y2={Y(hy)} />
            <path d={`M ${X(hx)} ${Y(hy)} A ${r * s} ${r * s} 0 0 ${ux * ny - uy * nx > 0 ? 1 : 0} ${X(x1)} ${Y(y1)}`} strokeDasharray="3 2" />
          </g>
        );
      })}
      {etiquetas &&
        nivel.espacios.map((e) => {
          const [cx, cy] = etiquetaEn(e);
          const bxs = e.poligono.map((p) => p[0]), bys = e.poligono.map((p) => p[1]);
          const bw = Math.max(...bxs) - Math.min(...bxs), bh = Math.max(...bys) - Math.min(...bys);
          const chico = bw < 2.2 && bh > bw;
          if (e.funcion === "escalera") return null;
          return (
            <g key={e.id + "t"} pointerEvents="none" transform={chico ? `rotate(-90 ${X(cx)} ${Y(cy)})` : undefined}>
              <text x={X(cx)} y={Y(cy) - 2} fontSize={11.5} fontWeight={600} textAnchor="middle" fill="#1f2328">{e.nombre}</text>
              <text x={X(cx)} y={Y(cy) + 13} fontSize={10.5} textAnchor="middle" fill="#5e6168" style={{ fontFamily: "var(--mono)" }}>{e.area_m2.toFixed(2)} m²</text>
              {costos?.[e.id] !== undefined && !chico && (
                <text x={X(cx)} y={Y(cy) + 26} fontSize={10.5} textAnchor="middle" fill="#a64b2a" style={{ fontFamily: "var(--mono)" }}>S/ {Math.round(costos[e.id]).toLocaleString("es-PE")}</text>
              )}
            </g>
          );
        })}
      {cotas && (
        <g fontSize={10.5} fill="#5e6168" stroke="#8a8d93" strokeWidth={0.8} textAnchor="middle" style={{ fontFamily: "var(--mono)" }}>
          <line x1={X(0)} y1={Y(-0.9)} x2={X(W)} y2={Y(-0.9)} />
          <line x1={X(0)} y1={Y(-1.1)} x2={X(0)} y2={Y(-0.7)} />
          <line x1={X(W)} y1={Y(-1.1)} x2={X(W)} y2={Y(-0.7)} />
          <text x={X(W / 2)} y={Y(-1.15)} stroke="none">{W.toFixed(2)}</text>
          <line x1={X(W + 0.9)} y1={Y(0)} x2={X(W + 0.9)} y2={Y(D)} />
          <line x1={X(W + 0.7)} y1={Y(0)} x2={X(W + 1.1)} y2={Y(0)} />
          <line x1={X(W + 0.7)} y1={Y(D)} x2={X(W + 1.1)} y2={Y(D)} />
          <text x={X(W + 1.25)} y={Y(D / 2)} stroke="none" transform={`rotate(90 ${X(W + 1.25)} ${Y(D / 2)})`}>{D.toFixed(2)}</text>
          <text x={X(W / 2)} y={Y(D + 1.2)} stroke="none" fill="#8a8d93">fachada posterior</text>
          <text x={X(W / 2)} y={Y(-0.35)} stroke="none" fill="#8a8d93" fontSize={9.5}>fachada principal</text>
        </g>
      )}
    </svg>
  );
}

function puntoEnPoligono([x, y]: [number, number], pol: [number, number][]) {
  let dentro = false;
  for (let i = 0, j = pol.length - 1; i < pol.length; j = i++) {
    const [xi, yi] = pol[i], [xj, yj] = pol[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) dentro = !dentro;
  }
  return dentro;
}

function distBorde([x, y]: [number, number], pol: [number, number][]) {
  let d = Infinity;
  for (let i = 0, j = pol.length - 1; i < pol.length; j = i++) {
    const [x1, y1] = pol[j], [x2, y2] = pol[i];
    const L2 = (x2 - x1) ** 2 + (y2 - y1) ** 2;
    const t = Math.max(0, Math.min(1, ((x - x1) * (x2 - x1) + (y - y1) * (y2 - y1)) / (L2 || 1)));
    d = Math.min(d, Math.hypot(x - (x1 + t * (x2 - x1)), y - (y1 + t * (y2 - y1))));
  }
  return d;
}

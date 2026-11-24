import { Canvas } from "@react-three/fiber";
import { Edges, OrbitControls } from "@react-three/drei";
import { useMemo } from "react";
import * as THREE from "three";
import type { Alternativa, Nivel } from "./tipos";

interface Props {
  alt: Alternativa;
  nivelVisible: number; // muestra hasta este nivel
  seleccion: string | null;
  onSeleccion: (id: string) => void;
}

const COLOR = { muroExt: "#e9e4da", muroInt: "#f4f1ea", losa: "#d8d3c9", vidrio: "#9fb9c4", escalera: "#c9c3b7", piso: {
  publico: "#ead7cc", privado: "#d9e2e5", servicio: "#e3dfd6", circulacion: "#f2efe8", escalera: "#d6d1c6", patio: "#cfdcca",
} as Record<string, string> };

/** Modelo 3D construido con los mismos datos que la planta: x = frente, z = fondo, y = altura. */
export default function Vista3D({ alt, nivelVisible, seleccion, onSeleccion }: Props) {
  const W = Math.max(...alt.terreno.map((p) => p[0]));
  const D = Math.max(...alt.terreno.map((p) => p[1]));
  const centro = new THREE.Vector3(W / 2, 2, D / 2);
  const niveles = alt.niveles.filter((n) => n.numero <= nivelVisible);
  return (
    <Canvas shadows camera={{ position: [W * 2.4 + 8, D * 1.15 + 6, -D * 0.75], fov: 38 }} style={{ position: "absolute", inset: 0 }}>
      <color attach="background" args={["#f6f4ef"]} />
      <hemisphereLight args={["#ffffff", "#d9d4ca", 0.9]} />
      <directionalLight position={[-12, 26, -16]} intensity={1.3} castShadow shadow-mapSize={[2048, 2048]} shadow-camera-left={-20} shadow-camera-right={30} shadow-camera-top={30} shadow-camera-bottom={-20} />
      <mesh rotation-x={-Math.PI / 2} position={[W / 2, -0.21, D / 2]} receiveShadow>
        <planeGeometry args={[W + 30, D + 30]} />
        <meshStandardMaterial color="#ebe7df" />
      </mesh>
      {niveles.map((n) => (
        <NivelMallas key={n.numero} n={n} superior={n.numero === nivelVisible} seleccion={seleccion} onSeleccion={onSeleccion} />
      ))}
      <OrbitControls target={centro} maxPolarAngle={Math.PI / 2.05} enableDamping />
    </Canvas>
  );
}

function NivelMallas({ n, superior, seleccion, onSeleccion }: { n: Nivel; superior: boolean; seleccion: string | null; onSeleccion: (id: string) => void }) {
  const muros = useMemo(() => {
    const out: { id: string; pos: [number, number, number]; size: [number, number, number]; rot: number; ext: boolean }[] = [];
    n.muros.forEach((m) => {
      const [ax, ay] = m.a, [bx, by] = m.b;
      const L = Math.hypot(bx - ax, by - ay);
      const ux = (bx - ax) / L, uy = (by - ay) / L;
      const rot = -Math.atan2(uy, ux);
      m.piezas.forEach(([s0, s1, z0, z1]) => {
        const c = (s0 + s1) / 2;
        out.push({ id: m.id, pos: [ax + ux * c, n.cota_m + (z0 + z1) / 2, ay + uy * c], size: [s1 - s0, z1 - z0, m.espesor_m], rot, ext: m.exterior });
      });
    });
    return out;
  }, [n]);
  const vidrios = useMemo(() => n.vanos.filter((v) => v.tipo === "ventana").map((v) => {
    const m = n.muros.find((x) => x.id === v.muro_id)!;
    const [ax, ay] = m.a, [bx, by] = m.b;
    const rot = -Math.atan2(by - ay, bx - ax);
    return { id: v.id, pos: [v.centro[0], n.cota_m + v.alfeizar_m + v.alto_m / 2, v.centro[1]] as [number, number, number], size: [v.ancho_m, v.alto_m, 0.04] as [number, number, number], rot };
  }), [n]);
  const losas = useMemo(() => n.losas.map((l) => {
    const forma = new THREE.Shape(l.poligono.map(([x, y]) => new THREE.Vector2(x, -y)));
    l.vacios.forEach((v) => forma.holes.push(new THREE.Path(v.map(([x, y]) => new THREE.Vector2(x, -y)))));
    const geo = new THREE.ExtrudeGeometry(forma, { depth: l.espesor_m, bevelEnabled: false });
    geo.rotateX(-Math.PI / 2);
    return { id: l.id, geo, y: l.cota_m - l.espesor_m, techo: l.nombre.toLowerCase().includes("techo") };
  }), [n]);
  const pisos = useMemo(() => n.espacios.map((e) => {
    const forma = new THREE.Shape(e.poligono.map(([x, y]) => new THREE.Vector2(x, -y)));
    const geo = new THREE.ShapeGeometry(forma);
    geo.rotateX(-Math.PI / 2);
    return { id: e.id, geo, funcion: e.funcion };
  }), [n]);

  return (
    <group>
      {losas.filter((l) => !(l.techo && superior)).map((l) => (
        <mesh key={l.id} geometry={l.geo} position={[0, l.y, 0]} castShadow receiveShadow>
          <meshStandardMaterial color={COLOR.losa} />
        </mesh>
      ))}
      {pisos.map((p) => (
        <mesh key={p.id} geometry={p.geo} position={[0, n.cota_m + 0.005, 0]} onClick={(ev) => { ev.stopPropagation(); onSeleccion(p.id); }} receiveShadow>
          <meshStandardMaterial color={seleccion === p.id ? "#d9a58e" : COLOR.piso[p.funcion]} />
        </mesh>
      ))}
      {muros.map((m, i) => (
        <mesh key={m.id + i} position={m.pos} rotation-y={m.rot} castShadow receiveShadow onClick={(ev) => { ev.stopPropagation(); onSeleccion(m.id); }}>
          <boxGeometry args={m.size} />
          <meshStandardMaterial color={seleccion === m.id ? "#c97d5f" : m.ext ? COLOR.muroExt : COLOR.muroInt} />
          <Edges color="#b9b2a5" threshold={20} />
        </mesh>
      ))}
      {vidrios.map((v) => (
        <mesh key={v.id} position={v.pos} rotation-y={v.rot} onClick={(ev) => { ev.stopPropagation(); onSeleccion(v.id); }}>
          <boxGeometry args={v.size} />
          <meshStandardMaterial color={seleccion === v.id ? "#c97d5f" : COLOR.vidrio} transparent opacity={0.45} />
        </mesh>
      ))}
      {n.escaleras.map((es) => es.peldanos.map((p, i) => (
        <mesh key={es.id + i} position={[(p.x0 + p.x1) / 2, (p.z0 + p.z1) / 2, (p.y0 + p.y1) / 2]} castShadow receiveShadow
          onClick={(ev) => { ev.stopPropagation(); onSeleccion(es.id); }}>
          <boxGeometry args={[p.x1 - p.x0, Math.max(0.02, p.z1 - p.z0), p.y1 - p.y0]} />
          <meshStandardMaterial color={seleccion === es.id ? "#c97d5f" : COLOR.escalera} />
        </mesh>
      )))}
    </group>
  );
}

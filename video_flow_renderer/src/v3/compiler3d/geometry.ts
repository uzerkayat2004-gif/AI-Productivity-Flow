/**
 * Procedural 3D Geometry Compilers for Video Flow V3.
 * Generates Three.js geometries for Assemblies, Components, Exploded Views, and FlowPaths.
 */

import { ExecutableNode3D } from "../contracts/video-program";

export interface Compiled3DObject {
  node_id: string;
  type: string;
  position: [number, number, number];
  rotation: [number, number, number];
  scale: [number, number, number];
  color: string;
  roughness: number;
  metalness: number;
}

export class GeometryCompiler3D {
  public compileNode(node: ExecutableNode3D, timeSec: number): Compiled3DObject {
    const t = node.transform || { position: [0, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1] };
    const pos: [number, number, number] = [...t.position];

    // Exploded Assembly procedural animation offset
    if (node.procedural_type === "ExplodedAssembly") {
      const offset = Math.sin(timeSec * 1.2) * 1.8;
      pos[0] += offset;
    }

    return {
      node_id: node.node_id,
      type: node.procedural_type || "Component",
      position: pos,
      rotation: t.rotation,
      scale: t.scale,
      color: node.material_spec.color || "#ff6b00",
      roughness: node.material_spec.roughness ?? 0.3,
      metalness: node.material_spec.metalness ?? 0.4,
    };
  }
}

export const geometryCompiler3D = new GeometryCompiler3D();

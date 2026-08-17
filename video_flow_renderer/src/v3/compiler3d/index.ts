/**
 * 3D Procedural Visual Compiler for Video Flow V3.
 * Procedural Three.js geometry compilation for Assemblies, Components, Cutaways, FlowPaths.
 * Enforces absolute-time property evaluation: state = Scene(t).
 */

import { ExecutableNode3D, ExecutableSceneProgram } from "../contracts/video-program";

export interface EvaluatedNode3D {
  node_id: string;
  procedural_type: string;
  position: [number, number, number];
  rotation: [number, number, number];
  scale: [number, number, number];
  material: Record<string, any>;
}

export class VisualCompiler3D {
  /**
   * Deterministically evaluate 3D procedural nodes at absolute time t (seconds).
   */
  public evaluateAt(scene: ExecutableSceneProgram, tSec: number): EvaluatedNode3D[] {
    const progress = Math.max(0, Math.min(1, tSec / (scene.duration_sec || 1.0)));

    return scene.nodes_3d.map((node) => {
      const transform = node.transform || { position: [0, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1] };
      const pos: [number, number, number] = [...transform.position];

      // Exploded assembly / flow animation curves
      if (node.procedural_type === "ExplodedAssembly" && progress > 0.3) {
        const explodeFactor = Math.sin((progress - 0.3) * Math.PI);
        pos[0] += explodeFactor * 1.5;
      }

      return {
        node_id: node.node_id,
        procedural_type: node.procedural_type,
        position: pos,
        rotation: transform.rotation,
        scale: transform.scale,
        material: node.material_spec || {},
      };
    });
  }
}

export const compiler3D = new VisualCompiler3D();

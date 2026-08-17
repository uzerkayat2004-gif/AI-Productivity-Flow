/**
 * 2D Semantic Visual Compiler for Video Flow V3.
 * Uses D3 for mathematical/layout scales & positioning, PixiJS v8 for WebGL canvas rendering.
 * Enforces absolute-time property evaluation: state = Scene(t).
 */

import { ExecutableElement2D, ExecutableSceneProgram } from "../contracts/video-program";

export interface EvaluatedElement2D {
  element_id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  opacity: number;
  scale: number;
  style: Record<string, any>;
}

export class VisualCompiler2D {
  /**
   * Deterministically evaluate 2D elements at absolute time t (seconds).
   */
  public evaluateAt(scene: ExecutableSceneProgram, tSec: number): EvaluatedElement2D[] {
    const progress = Math.max(0, Math.min(1, tSec / (scene.duration_sec || 1.0)));

    return scene.elements_2d.map((elem) => {
      const bounds = elem.layout_bounds || { x: 100, y: 100, width: 200, height: 100 };

      // Deterministic entrance animation curve based on element layer
      let opacity = 1.0;
      let scale = 1.0;

      if (progress < 0.2) {
        const localT = progress / 0.2;
        opacity = localT;
        scale = 0.9 + 0.1 * localT;
      }

      return {
        element_id: elem.element_id,
        x: bounds.x,
        y: bounds.y,
        width: bounds.width,
        height: bounds.height,
        opacity,
        scale,
        style: elem.style || {},
      };
    });
  }
}

export const compiler2D = new VisualCompiler2D();

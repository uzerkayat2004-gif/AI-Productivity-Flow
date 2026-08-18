/**
 * 2D Semantic Visual Compiler for Video Flow V3.
 *
 * Combines D3 mathematical layout engines with PixiJS v8 canvas rendering.
 * Provides deterministic absolute-time scene compilation and evaluation: state = Scene(t).
 */

import { Container } from "pixi.js";
import {
  ArtDirectionGenome,
  DEFAULT_ART_GENOME,
  ExecutableSceneProgram,
  SemanticRepresentationType,
} from "../contracts/video-program";
import {
  CompositorContext,
  EvaluatedElement2D,
  ICompositor2D,
  RenderableNode2D,
  VisualCompilerOutput2D,
} from "./types";
import {
  compositorRegistry,
  createSceneContainer,
  updateSceneAt,
  CompositorRegistry,
  CompositorLibrary2D,
  compositorLibrary2D,
} from "./composers";

export * from "./types";
export * from "./helpers";
export {
  CompositorLibrary2D,
  compositorLibrary2D,
  CompositorRegistry,
  compositorRegistry,
  createSceneContainer,
  updateSceneAt,
  extractDynamicLabels,
} from "./composers";

export class VisualCompiler2D {
  private registry: CompositorRegistry;

  constructor() {
    this.registry = compositorRegistry;
  }

  /**
   * Deterministically creates the PixiJS v8 display hierarchy for an ExecutableSceneProgram.
   */
  public createContainer(
    scene: ExecutableSceneProgram,
    genome: Partial<ArtDirectionGenome> = DEFAULT_ART_GENOME,
    width: number = 1920,
    height: number = 1080
  ): Container {
    return createSceneContainer(scene, genome, width, height);
  }

  /**
   * Deterministically updates a PixiJS v8 display hierarchy at absolute time t (tSec).
   */
  public updateAt(
    container: Container,
    scene: ExecutableSceneProgram,
    tSec: number,
    width: number = 1920,
    height: number = 1080,
    genome: Partial<ArtDirectionGenome> = DEFAULT_ART_GENOME
  ): void {
    updateSceneAt(container, scene, tSec, width, height, genome);
  }

  /**
   * Evaluates 2D elements at absolute time t (seconds) for contract parity and queries.
   */
  public evaluateAt(scene: ExecutableSceneProgram, tSec: number): EvaluatedElement2D[] {
    const duration = Math.max(0.1, scene.duration_sec || 5.0);
    const progress = Math.max(0, Math.min(1, tSec / duration));
    const repType = scene.representation_type || scene.elements_2d?.[0]?.compositor || SemanticRepresentationType.PROCESS;

    // Evaluate elements with deterministic entrance curves
    return (scene.elements_2d || []).map((elem, idx) => {
      const bounds = elem.layout_bounds || { x: 100 + idx * 220, y: 200, width: 200, height: 120 };

      let opacity = 1.0;
      let scale = 1.0;

      const staggerStart = idx * 0.1;
      const localElapsed = progress * duration - staggerStart;

      if (localElapsed <= 0) {
        opacity = 0;
        scale = 0.85;
      } else if (localElapsed < 0.4) {
        const localT = localElapsed / 0.4;
        opacity = localT;
        scale = 0.85 + 0.15 * localT;
      }

      return {
        element_id: elem.element_id,
        compositor: elem.compositor || repType,
        x: bounds.x,
        y: bounds.y,
        width: bounds.width,
        height: bounds.height,
        opacity,
        scale,
        style: elem.style || {},
        data: elem.data,
      };
    });
  }

  /**
   * Compiles and evaluates the entire 2D visual scene at absolute time tSec.
   */
  public compileScene(
    scene: ExecutableSceneProgram,
    tSec: number,
    width: number = 1920,
    height: number = 1080,
    genome: Partial<ArtDirectionGenome> = DEFAULT_ART_GENOME
  ): VisualCompilerOutput2D {
    const container = this.createContainer(scene, genome, width, height);
    this.updateAt(container, scene, tSec, width, height, genome);
    const evaluated_elements = this.evaluateAt(scene, tSec);

    return {
      scene_id: scene.scene_id,
      time_sec: tSec,
      duration_sec: scene.duration_sec || 5.0,
      representation_type: scene.representation_type || SemanticRepresentationType.PROCESS,
      container,
      evaluated_elements,
    };
  }
}

export const compiler2D = new VisualCompiler2D();

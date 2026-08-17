/**
 * Type definitions for the 2D Semantic Visual Compiler and Compositor Library.
 */

import { Container } from "pixi.js";
import {
  ArtDirectionGenome,
  ExecutableElement2D,
  ExecutableSceneProgram,
  SemanticRepresentationType,
} from "../contracts/video-program";

export interface CompositorContext {
  containerWidth: number;
  containerHeight: number;
  genome: ArtDirectionGenome;
  durationSec: number;
}

export interface RenderableNode2D {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  label: string;
  role: string;
  fillColor: string;
  strokeColor: string;
  opacity: number;
  scale: number;
  data?: Record<string, any>;
}

export interface EvaluatedElement2D {
  element_id: string;
  compositor: string;
  x: number;
  y: number;
  width: number;
  height: number;
  opacity: number;
  scale: number;
  style: Record<string, any>;
  data?: Record<string, any>;
}

export interface VisualCompilerOutput2D {
  scene_id: string;
  time_sec: number;
  duration_sec: number;
  representation_type: SemanticRepresentationType | string;
  container: Container;
  evaluated_elements: EvaluatedElement2D[];
}

export interface ICompositor2D {
  readonly type: SemanticRepresentationType | string;
  readonly name: string;
  readonly description: string;

  /**
   * Constructs the PixiJS v8 DisplayObject hierarchy for this scene representation.
   */
  createScene(scene: ExecutableSceneProgram, context: CompositorContext): Container;

  /**
   * Deterministically updates display objects (transforms, opacities, graphics, meters, connectors)
   * at absolute time t (tSec). Pure function of Scene(t).
   */
  updateAt(root: Container, scene: ExecutableSceneProgram, tSec: number, context: CompositorContext): void;
}

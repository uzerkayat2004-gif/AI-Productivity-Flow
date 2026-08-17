/**
 * Canonical Video Flow V3 TypeScript Contracts.
 * Synchronized 1:1 with src/voice_flow/video_flow_v3/contracts.py
 */

export const V3_CONTRACT_VERSION = "v3.0.0";

export enum GenerationStateV3 {
  CREATED = "created",
  QUEUED = "queued",
  NORMALIZING_SOURCE = "normalizing_source",
  UNDERSTANDING = "understanding",
  DIRECTING = "directing",
  COMPILING_INITIAL = "compiling_initial",
  BUFFERING = "buffering",
  READY = "ready",
  GENERATING_AHEAD = "generating_ahead",
  COMPLETE = "complete",
  FAILED = "failed",
  CANCELLED = "cancelled",
}

export enum ExportStateV3 {
  NOT_REQUESTED = "not_requested",
  REQUESTED = "requested",
  EXPORTING = "exporting",
  EXPORTED = "exported",
  FAILED = "failed",
}

export enum FidelityClass3D {
  F1_PHYSICAL = "F1",
  F2_SCHEMATIC = "F2",
  F3_CONCEPTUAL = "F3",
  F4_INSUFFICIENT = "F4",
}

export interface ExecutableElement2D {
  element_id: string;
  layer: "background" | "node" | "text" | "callout" | "overlay";
  compositor: string;
  layout_bounds: { x: number; y: number; width: number; height: number };
  style: Record<string, any>;
  animation_keyframes: Array<Record<string, any>>;
}

export interface ExecutableNode3D {
  node_id: string;
  procedural_type: string;
  transform: { position: [number, number, number]; rotation: [number, number, number]; scale: [number, number, number] };
  material_spec: Record<string, any>;
  camera_target?: Record<string, any>;
  animation_keyframes: Array<Record<string, any>>;
}

export interface ExecutableSceneProgram {
  contract_version: string;
  scene_id: string;
  sequence: number;
  duration_sec: number;
  elements_2d: ExecutableElement2D[];
  nodes_3d: ExecutableNode3D[];
  camera_path: Array<Record<string, any>>;
  audio_segment_url: string;
  word_timestamps: Array<Record<string, any>>;
}

export interface VideoProgramV3 {
  contract_version: string;
  project_id: string;
  mode: "summary" | "full" | "spatial_3d";
  title: string;
  source_hash: string;
  art_genome: Record<string, any>;
  chapters: Array<Record<string, any>>;
  scenes: Array<Record<string, any>>;
  coverage_summary: Record<string, any>;
  total_estimated_duration_sec: number;
}

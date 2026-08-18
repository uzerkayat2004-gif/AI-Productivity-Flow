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

export enum PerformanceProfile {
  QUALITY = "QUALITY",
  STANDARD = "STANDARD",
  COMPATIBILITY = "COMPATIBILITY",
}

/**
 * Canonical 3D Representation Types for procedural spatial graphics.
 * 9 Canonical 3D representations.
 */
export enum Semantic3DRepresentationType {
  ASSEMBLY_3D = "ASSEMBLY_3D",
  ASSEMBLY = "ASSEMBLY",
  EXPLODED_3D = "EXPLODED_3D",
  EXPLODED_ASSEMBLY = "EXPLODED_ASSEMBLY",
  CUTAWAY_3D = "CUTAWAY_3D",
  CUTAWAY = "CUTAWAY",
  HOUSING_3D = "HOUSING_3D",
  COMPONENT = "COMPONENT",
  FLOW_PATH_3D = "FLOW_PATH_3D",
  FLOW_PATH = "FLOW_PATH",
  LAYER_STACK_3D = "LAYER_STACK_3D",
  CROSS_SECTION_3D = "CROSS_SECTION_3D",
  TERRAIN_SURFACE_3D = "TERRAIN_SURFACE_3D",
  ORBIT_INSPECT_3D = "ORBIT_INSPECT_3D",
  TRAJECTORY = "TRAJECTORY",
  MECHANISM = "MECHANISM",
  SPATIAL_SYSTEM = "SPATIAL_SYSTEM",
}

export const Canonical3DRepresentationType = Semantic3DRepresentationType;
export type Canonical3DRepresentationType = Semantic3DRepresentationType;

/**
 * Canonical 2D Semantic Representation Types.
 * All 20 canonical 2D compositors + aliases for deterministic compositing.
 */
export enum SemanticRepresentationType {
  // 20 Canonical 2D Representation Types
  PROCESS = "PROCESS",
  CAUSE_EFFECT = "CAUSE_EFFECT",
  COMPARISON = "COMPARISON",
  TIMELINE = "TIMELINE",
  TRANSFORMATION = "TRANSFORMATION",
  HIERARCHY = "HIERARCHY",
  NETWORK = "NETWORK",
  QUANTITATIVE_RELATIONSHIP = "QUANTITATIVE_RELATIONSHIP",
  CHART = "CHART",
  LAYER_STACK = "LAYER_STACK",
  SYSTEM_ARCHITECTURE = "SYSTEM_ARCHITECTURE",
  DOCUMENT_SOURCE = "DOCUMENT_SOURCE",
  CODE_EXPLANATION = "CODE_EXPLANATION",
  EQUATION_EXPLANATION = "EQUATION_EXPLANATION",
  MAP_GEOGRAPHY = "MAP_GEOGRAPHY",
  SEQUENCE = "SEQUENCE",
  OBJECT_FOCUS = "OBJECT_FOCUS",
  BEFORE_AFTER = "BEFORE_AFTER",
  FLOW = "FLOW",
  CONCEPTUAL_METAPHOR = "CONCEPTUAL_METAPHOR",
  SUMMARY_RECAP = "SUMMARY_RECAP",

  // 3D Canonical Types (Unified in enum for cross-language compatibility)
  ASSEMBLY_3D = "ASSEMBLY_3D",
  EXPLODED_ASSEMBLY_3D = "EXPLODED_ASSEMBLY_3D",
  EXPLODED_3D = "EXPLODED_3D",
  CUTAWAY_3D = "CUTAWAY_3D",
  COMPONENT_3D = "COMPONENT_3D",
  HOUSING_3D = "HOUSING_3D",
  FLOW_PATH_3D = "FLOW_PATH_3D",
  TRAJECTORY_3D = "TRAJECTORY_3D",
  MECHANISM_3D = "MECHANISM_3D",
  SPATIAL_SYSTEM_3D = "SPATIAL_SYSTEM_3D",
  CROSS_SECTION_3D = "CROSS_SECTION_3D",
  TERRAIN_SURFACE_3D = "TERRAIN_SURFACE_3D",
  ORBIT_INSPECT_3D = "ORBIT_INSPECT_3D",

  // Aliases & Extended Visual Styles
  QUANTITATIVE = "QUANTITATIVE",
  LIST_BREAKDOWN = "LIST_BREAKDOWN",
  STAT_GRID = "STAT_GRID",
  QUOTE_CALLOUT = "QUOTE_CALLOUT",
}

/**
 * Semantic Transition Types between scenes and beats.
 */
export enum SemanticTransitionType {
  MATCH_TRANSITION = "MATCH_TRANSITION",
  CARRY = "CARRY",
  TRAVERSE = "TRAVERSE",
  EXPAND = "EXPAND",
  COLLAPSE = "COLLAPSE",
  DISSOLVE = "DISSOLVE",
  CUT = "CUT",
  FADE = "FADE",
  CROSS_FADE = "CROSS_FADE",
  SLIDE = "SLIDE",
  WIPE = "WIPE",
  ZOOM = "ZOOM",
  MORPH = "MORPH",
  PUSH = "PUSH",
  MATCH_CUT = "MATCH_CUT",
  NONE = "NONE",
}

/**
 * Semantic Motion Types (motion verbs) governing beat-level animation.
 */
export enum SemanticMotionType {
  GROW = "GROW",
  SHRINK = "SHRINK",
  FLOW = "FLOW",
  CONNECT = "CONNECT",
  MORPH = "MORPH",
  ISOLATE = "ISOLATE",
  PROGRESS = "PROGRESS",
  REVEAL_LEVELS = "REVEAL_LEVELS",
  MERGE = "MERGE",
  SPLIT = "SPLIT",
  EXPLODE = "EXPLODE",
  REVEAL = "REVEAL",
  FOCUS = "FOCUS",
  PULSE = "PULSE",
  TRANSFORM = "TRANSFORM",
  SWEEP = "SWEEP",
}

/**
 * Disposition types for SourceUnits.
 */
export enum UnitDispositionType {
  COVERED_NARRATION = "covered_narration",
  COVERED_VISUAL = "covered_visual",
  COVERED_BOTH = "covered_both",
  MERGED = "merged",
  DISPOSED = "disposed",
  INCLUDED = "included",
  COMPRESSED = "compressed",
  SUPPORTING_ONLY = "supporting_only",
  UNRESOLVED = "unresolved",
}

/**
 * Internal Scene Beat for deterministic temporal pacing and semantic motion verbs.
 */
export interface SceneBeat {
  beat_id: string;
  start_sec?: number;
  end_sec?: number;
  duration_sec?: number;
  time_offset_sec?: number;
  action?: string;
  motion_type?: SemanticMotionType | string;
  transition_type?: SemanticTransitionType | string;
  target_ids?: string[];
  target_elements?: string[];
  target_element_ids?: string[];
  narration_cue?: string;
  narration_subphrase?: string;
  visual_action?: string;
  description?: string;
  label?: string;
  emphasis?: number;
  parameters?: Record<string, any>;
  properties?: DictAny;
  data?: DictAny;
}

type DictAny = Record<string, any>;

export interface ArtDirectionPalette {
  background: string;
  surface: string;
  surfaceSubtle?: string;
  surfaceElevated?: string;
  primary: string;
  secondary: string;
  accent: string;
  accentAlt?: string;
  text: string;
  textSecondary: string;
  textMuted?: string;
  border: string;
  borderSubtle?: string;
  glow?: string;
  grid?: string;
  success?: string;
  warning?: string;
  error?: string;
  info?: string;
  primary_info?: string;
  secondary_info?: string;
  structural_neutral?: string;
  highlight?: string;
  environment?: string;
  [key: string]: string | undefined;
}

export interface ArtDirectionTypography {
  headingFont: string;
  bodyFont: string;
  codeFont: string;
  monoFont?: string;
  editorialFont?: string;
  [key: string]: string | undefined;
}

export interface ArtDirectionDensityRules {
  maxNodesPerScene?: number;
  padding?: number;
  nodeSpacing?: number;
  cardRadius?: number;
  borderWidth?: number;
  glowRadius?: number;
  [key: string]: any;
}

export interface ArtDirectionGenome {
  family: string;
  palette: ArtDirectionPalette;
  typography: ArtDirectionTypography;
  materials?: Record<string, any>;
  lighting_rig?: string | Record<string, any>;
  camera_grammar?: string;
  motion_grammar?: string;
  density_rules: ArtDirectionDensityRules;
  visual_intensity_budget?: number;
}

export const TECHNICAL_SYSTEMS_GENOME: ArtDirectionGenome = {
  family: "Technical Systems",
  palette: {
    background: "#080d1a",
    surface: "#0f172a",
    surfaceSubtle: "#131e35",
    surfaceElevated: "#1e293b",
    primary: "#38bdf8",
    secondary: "#818cf8",
    accent: "#00e5ff",
    accentAlt: "#f59e0b",
    text: "#f8fafc",
    textSecondary: "#94a3b8",
    textMuted: "#64748b",
    border: "#1e293b",
    borderSubtle: "#334155",
    glow: "rgba(0, 229, 255, 0.4)",
    grid: "rgba(56, 189, 248, 0.08)",
    success: "#10b981",
    warning: "#f59e0b",
    error: "#ef4444",
    info: "#0284c7",
    primary_info: "#38bdf8",
    secondary_info: "#818cf8",
    structural_neutral: "#0f172a",
    highlight: "#00e5ff",
    environment: "#080d1a",
  },
  typography: {
    headingFont: "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    bodyFont: "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    codeFont: "'JetBrains Mono', 'Fira Code', Consolas, Monaco, monospace",
    monoFont: "'JetBrains Mono', Consolas, monospace",
    editorialFont: "Georgia, Cambria, 'Times New Roman', serif",
  },
  lighting_rig: "Technical High Key",
  camera_grammar: "HeroFocus",
  motion_grammar: "ControlledDeceleration",
  density_rules: {
    maxNodesPerScene: 8,
    padding: 48,
    nodeSpacing: 24,
    cardRadius: 10,
    borderWidth: 1.5,
    glowRadius: 12,
  },
  visual_intensity_budget: 100,
};

export const CYBER_GRID_GENOME: ArtDirectionGenome = {
  family: "Cyber Grid",
  palette: {
    background: "#050811",
    surface: "#0c1322",
    surfaceSubtle: "#111b30",
    surfaceElevated: "#182744",
    primary: "#00ffd5",
    secondary: "#a855f7",
    accent: "#06b6d4",
    accentAlt: "#f43f5e",
    text: "#ffffff",
    textSecondary: "#a5f3fc",
    textMuted: "#475569",
    border: "#164e63",
    borderSubtle: "#0e7490",
    glow: "rgba(0, 255, 213, 0.45)",
    grid: "rgba(0, 255, 213, 0.12)",
    success: "#22c55e",
    warning: "#eab308",
    error: "#f43f5e",
    info: "#06b6d4",
  },
  typography: {
    headingFont: "'Space Grotesk', Inter, sans-serif",
    bodyFont: "Inter, sans-serif",
    codeFont: "'Fira Code', 'JetBrains Mono', monospace",
  },
  lighting_rig: "Neon Cyber Rim",
  camera_grammar: "KineticOrbit",
  motion_grammar: "SnappySpring",
  density_rules: {
    maxNodesPerScene: 10,
    padding: 40,
    nodeSpacing: 20,
    cardRadius: 6,
    borderWidth: 2,
    glowRadius: 16,
  },
  visual_intensity_budget: 120,
};

export const EDITORIAL_ELEGANCE_GENOME: ArtDirectionGenome = {
  family: "Editorial Elegance",
  palette: {
    background: "#121316",
    surface: "#1a1c21",
    surfaceSubtle: "#24272e",
    surfaceElevated: "#2d313b",
    primary: "#f3e8d2",
    secondary: "#d97706",
    accent: "#e5a93b",
    accentAlt: "#ea580c",
    text: "#fcfaf7",
    textSecondary: "#cbd5e1",
    textMuted: "#64748b",
    border: "#334155",
    borderSubtle: "#475569",
    glow: "rgba(229, 169, 59, 0.3)",
    grid: "rgba(243, 232, 210, 0.05)",
    success: "#059669",
    warning: "#d97706",
    error: "#dc2626",
    info: "#2563eb",
  },
  typography: {
    headingFont: "Georgia, 'Playfair Display', serif",
    bodyFont: "Inter, -apple-system, sans-serif",
    codeFont: "'JetBrains Mono', monospace",
    editorialFont: "Georgia, 'Playfair Display', serif",
  },
  lighting_rig: "Studio Warm Rim",
  camera_grammar: "SlowEditorialGlide",
  motion_grammar: "SmoothEaseInOut",
  density_rules: {
    maxNodesPerScene: 6,
    padding: 60,
    nodeSpacing: 32,
    cardRadius: 12,
    borderWidth: 1,
    glowRadius: 8,
  },
  visual_intensity_budget: 80,
};

export const DEFAULT_ART_GENOME = TECHNICAL_SYSTEMS_GENOME;

export interface ExecutableElement2D {
  element_id: string;
  layer: "background" | "diagram" | "node" | "text" | "callout" | "overlay" | string;
  compositor: SemanticRepresentationType | string;
  layout_bounds: { x: number; y: number; width: number; height: number };
  style: Record<string, any>;
  animation_keyframes?: Array<Record<string, any>>;
  data?: Record<string, any>;
  continuity_key?: string;
  carry_over?: boolean;
}

export interface ExecutableNode3D {
  node_id: string;
  procedural_type: string;
  transform: {
    position: [number, number, number];
    rotation: [number, number, number];
    scale: [number, number, number];
  };
  material_spec: Record<string, any>;
  camera_target?: Record<string, any>;
  animation_keyframes: Array<Record<string, any>>;
  continuity_key?: string;
  carry_over?: boolean;
}

export interface ExecutableSceneProgram {
  contract_version: string;
  scene_id: string;
  chapter_id?: string;
  sequence: number;
  duration_sec: number;
  suggested_duration_sec?: number;
  representation_type?: SemanticRepresentationType | Semantic3DRepresentationType | string;
  title?: string;
  narration_text?: string;
  teaching_goal?: string;
  viewer_question?: string;
  intended_understanding?: string;
  motion_purpose?: string;
  shot_grammar?: string;
  use_3d?: boolean;
  fidelity_3d?: FidelityClass3D | string;
  evidence_refs?: string[];
  semantic_objects?: Array<Record<string, any>>;
  semantic_relationships?: Array<Record<string, any>>;
  beats?: SceneBeat[];
  scene_beats?: Array<SceneBeat | Record<string, any>>;
  transition_type?: SemanticTransitionType | string;
  transition_in?: string;
  transition_out?: string;
  source_unit_dispositions?: Record<string, string>;
  elements_2d: ExecutableElement2D[];
  nodes_3d: ExecutableNode3D[];
  camera_path: Array<Record<string, any>>;
  audio_segment_url?: string;
  word_timestamps?: Array<Record<string, any>>;
  art_genome?: Partial<ArtDirectionGenome>;
  metadata?: Record<string, any>;
}

export interface VideoProgramV3 {
  contract_version: string;
  project_id: string;
  mode: "summary" | "full" | "spatial_3d" | string;
  title: string;
  source_hash: string;
  art_genome: ArtDirectionGenome;
  chapters: Array<Record<string, any>>;
  scenes: Array<ExecutableSceneProgram | Record<string, any>>;
  coverage_summary: Record<string, any>;
  total_estimated_duration_sec: number;
}

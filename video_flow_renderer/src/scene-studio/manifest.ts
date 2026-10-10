import type {SceneNode, SceneProgram} from "./schema";

export type SceneRenderWindow = {
  startFrame: number;
  endFrame: number;
  mode?: "full" | "motion-island" | "static";
  sceneFrameStart?: number;
  sceneFrameEnd?: number;
};

export type SceneTransition = {
  type?: "cut" | "fade" | "wipe" | "slide" | "match" | string;
  durationInFrames?: number;
  direction?: "left" | "right" | "up" | "down";
  color?: string;
};

export type SceneMotionPlan = {
  renderWindows?: SceneRenderWindow[];
  transition?: SceneTransition;
  [key: string]: unknown;
};

export type SceneWordTiming = {
  text: string;
  offsetSeconds: number;
  durationSeconds?: number;
  startFrame?: number;
  endFrame?: number;
  anchorId?: string;
};

export type AgenticSceneManifest = SceneProgram & {
  durationSeconds?: number;
  narration?: string;
  audioFile?: string | null;
  wordTimings?: SceneWordTiming[];
  transition?: SceneTransition;
  motionPlan?: SceneMotionPlan;
  sceneProgram?: SceneProgram | null;
};

export type AgenticVideoFlowManifest = {
  engineVersion?: "agentic-visual.v1" | string;
  title?: string;
  fps?: number;
  width?: number;
  height?: number;
  scenes: AgenticSceneManifest[];
  metadata?: Record<string, unknown>;
};

const numberOr = (value: unknown, fallback: number) => typeof value === "number" && Number.isFinite(value) ? value : fallback;
const isRecord = (value: unknown): value is Record<string, unknown> => Boolean(value && typeof value === "object" && !Array.isArray(value));

const stableSceneKey = (scene: Partial<AgenticSceneManifest>) => {
  const source = `${scene.title ?? "scene"}|${scene.narration ?? ""}|${scene.durationSeconds ?? scene.durationInFrames ?? 0}`;
  let hash = 2166136261;
  for (let index = 0; index < source.length; index += 1) {
    hash ^= source.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36);
};

const fallbackRoot = (scene: Partial<AgenticSceneManifest>): SceneNode => ({
  id: `${typeof scene.id === "string" && scene.id ? scene.id : "scene"}-root`,
  type: "group",
  layout: {mode: "absolute", width: numberOr(scene.width, 1920), height: numberOr(scene.height, 1080)},
  children: isRecord(scene) && Array.isArray((scene as {nodes?: unknown}).nodes)
    ? ((scene as {nodes: unknown[]}).nodes.filter((node): node is SceneNode => isRecord(node)) as SceneNode[])
    : [],
});

/** Normalize orchestrator output while keeping narration and render-window metadata intact. */
export const normalizeSceneProgram = (
  input: AgenticSceneManifest | null | undefined | unknown,
  defaults: Pick<AgenticVideoFlowManifest, "fps" | "width" | "height"> = {},
): AgenticSceneManifest => {
  const raw = isRecord(input) ? input as AgenticSceneManifest : {} as AgenticSceneManifest;
  const nested = isRecord(raw.sceneProgram) ? raw.sceneProgram as SceneProgram : undefined;
  const scene = (nested ? {...raw, ...nested} : {...raw}) as AgenticSceneManifest;
  const fps = numberOr(scene.fps, numberOr(defaults.fps, 24));
  const width = numberOr(scene.width, numberOr(defaults.width, 1920));
  const height = numberOr(scene.height, numberOr(defaults.height, 1080));
  const durationSeconds = numberOr(scene.durationSeconds, numberOr(scene.durationInFrames, fps) / Math.max(1, fps));
  const durationInFrames = Math.max(1, Math.ceil(numberOr(scene.durationInFrames, durationSeconds * fps)));
  const root = isRecord(scene.root) ? scene.root as SceneNode : fallbackRoot({...scene, width, height});
  return {
    ...scene,
    id: typeof scene.id === "string" && scene.id ? scene.id : `scene-${stableSceneKey(scene)}`,
    fps,
    width,
    height,
    durationSeconds,
    durationInFrames,
    renderClass: typeof scene.renderClass === "string" && scene.renderClass ? scene.renderClass as SceneProgram["renderClass"] : "static",
    root,
  };
};

export const normalizeManifest = (manifest: AgenticVideoFlowManifest | null | undefined | unknown): AgenticVideoFlowManifest => {
  const raw: Partial<AgenticVideoFlowManifest> = isRecord(manifest) ? manifest as AgenticVideoFlowManifest : {};
  const scenes = Array.isArray(raw.scenes) ? raw.scenes : [];
  return {
    ...raw,
    engineVersion: typeof raw.engineVersion === "string" && raw.engineVersion ? raw.engineVersion : "agentic-visual.v1",
    scenes: scenes.map((scene) => normalizeSceneProgram(scene, raw)),
  };
};

/** Convert narration timings into semantic anchors without changing authored anchors. */
export const wordTimingsToAnchors = (scene: AgenticSceneManifest): NonNullable<SceneProgram["anchors"]> => {
  const timings = Array.isArray(scene.wordTimings) ? scene.wordTimings : [];
  return timings.map((timing, index) => {
    const offsetSeconds = numberOr(timing?.offsetSeconds, 0);
    const start = numberOr(timing?.startFrame, Math.max(0, Math.round(offsetSeconds * Math.max(1, scene.fps))));
    const end = numberOr(timing?.endFrame, start + Math.max(1, Math.round(numberOr(timing?.durationSeconds, 0.25) * Math.max(1, scene.fps))));
    return {id: typeof timing?.anchorId === "string" && timing.anchorId ? timing.anchorId : `word-${index}`, start, end, tags: ["narration", typeof timing?.text === "string" ? timing.text : ""]};
  });
};


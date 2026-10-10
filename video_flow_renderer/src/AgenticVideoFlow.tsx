import React from "react";
import {AbsoluteFill, Composition, Sequence, staticFile} from "remotion";
import {Audio} from "@remotion/media";
import {SceneRuntime} from "./scene-studio/renderer";
import type {SceneNode, SceneProgram} from "./scene-studio/schema";
import {normalizeSceneProgram, wordTimingsToAnchors, type AgenticSceneManifest} from "./scene-studio/manifest";
import {assertSceneProgram, preflightScene} from "./scene-studio/validate";

export type AgenticVideoFlowProps = {
  /** One program is the smallest useful manifest. */
  program?: AgenticSceneManifest;
  /** Multiple independently authored programs are rendered as a timeline. */
  scenes?: AgenticSceneManifest[];
  engineVersion?: string;
  title?: string;
  fps?: number;
  width?: number;
  height?: number;
  metadata?: Record<string, unknown>;
};

const sampleNode = (id: string, type: SceneNode["type"], layout: SceneNode["layout"], extra: Partial<SceneNode> = {}): SceneNode => ({id, type, layout, ...extra});

/** A small, intentionally open-ended example rather than a completed template. */
export const defaultAgenticProgram: SceneProgram = {
  version: "scene-program/1",
  id: "agentic-welcome",
  title: "Scene Studio",
  fps: 24,
  width: 1920,
  height: 1080,
  durationInFrames: 192,
  renderClass: "continuous-2d",
  background: "#f5f0e8",
  anchors: [
    {id: "intro", start: 0, end: 48, tags: ["scene:intro"]},
    {id: "network-reveal", start: 42, end: 144, tags: ["relationship"]},
    {id: "closing", start: 150, end: 192, tags: ["scene:closing"]},
  ],
  root: sampleNode("canvas", "group", {mode: "absolute", width: 1920, height: 1080}, {
    style: {fontFamily: "Arial, sans-serif", color: "#171717"},
    children: [
      sampleNode("eyebrow", "text", {x: 120, y: 104, width: 700, height: 44}, {
        text: {text: "SCENE STUDIO / AGENTIC VISUAL COMPILER", role: "label"},
        style: {fontSize: 22, fontWeight: 700, letterSpacing: 3, color: "#6b665e"},
        anchors: ["intro"],
        motion: {enter: {start: 0, end: 24, easing: "easeOut"}},
      }),
      sampleNode("headline", "text", {x: 120, y: 160, width: 1080, height: 136}, {
        text: {text: "Author the visual idea.\nLet the runtime keep it honest.", role: "display", fit: "wrap"},
        style: {fontSize: 66, fontWeight: 800, lineHeight: 1.02, color: "#171717"},
        anchors: ["intro"],
        motion: {enter: {start: 12, end: 48, easing: "easeOut"}},
      }),
      sampleNode("signal", "path", {x: 120, y: 340, width: 980, height: 360}, {
        path: {d: "M 20 286 C 190 250 225 54 430 126 S 730 366 956 74", progress: {op: "interpolate", input: "frame", inputRange: [32, 112], outputRange: [0, 1]}},
        style: {stroke: {color: "#ee7b35", width: 8, cap: "round"}},
        anchors: ["network-reveal"],
      }),
      sampleNode("network", "network", {x: 1060, y: 340, width: 690, height: 430}, {
        network: {
          nodes: [
            {id: "evidence", label: "evidence", x: 90, y: 190, radius: 36, color: "#a7d6a2"},
            {id: "meaning", label: "meaning", x: 340, y: 76, radius: 38, color: "#8bd7e6"},
            {id: "scene", label: "scene", x: 560, y: 190, radius: 42, color: "#ffd65a"},
            {id: "motion", label: "motion", x: 340, y: 330, radius: 34, color: "#ef9caa"},
          ],
          edges: [
            {from: "evidence", to: "meaning", directed: true, progress: {op: "interpolate", input: "frame", inputRange: [44, 88], outputRange: [0, 1]}},
            {from: "meaning", to: "scene", directed: true, progress: {op: "interpolate", input: "frame", inputRange: [64, 110], outputRange: [0, 1]}},
            {from: "scene", to: "motion", directed: true, progress: {op: "interpolate", input: "frame", inputRange: [86, 132], outputRange: [0, 1]}},
          ],
        },
        anchors: ["network-reveal"],
      }),
      sampleNode("footnote", "text", {x: 120, y: 900, width: 1200, height: 42}, {
        text: {text: "Every node is inspectable; every motion is a function of the current frame.", role: "caption"},
        style: {fontSize: 24, color: "#6b665e"},
        anchors: ["closing"],
      }),
    ],
  }),
  metadata: {renderClass: "continuous-2d", generatedBy: "SceneStudio"},
};

const toMediaSrc = (src: unknown) => {
  if (typeof src !== "string" || !src.trim()) return "";
  return /^(?:https?:|data:|blob:)/.test(src) ? src : staticFile(src);
};

const getPrograms = (props: AgenticVideoFlowProps | Record<string, unknown>) => {
  const raw = props as AgenticVideoFlowProps;
  const scenes = Array.isArray(raw.scenes) ? raw.scenes.filter(Boolean) : [];
  const input: unknown[] = scenes.length ? scenes : [raw.program ?? defaultAgenticProgram];
  return input.map((scene) => {
    const normalized = normalizeSceneProgram(scene, raw);
    const narrationAnchors = wordTimingsToAnchors(normalized);
    const anchors = [...(Array.isArray(normalized.anchors) ? normalized.anchors : [])];
    for (const anchor of narrationAnchors) if (!anchors.some((item) => item.id === anchor.id)) anchors.push(anchor);
    return {...normalized, anchors};
  });
};

const totalDuration = (programs: SceneProgram[]) => programs.reduce((sum, program) => sum + Math.max(1, program.durationInFrames), 0);

const AgenticVideoFlowComposition: React.FC<AgenticVideoFlowProps> = (props) => {
  let from = 0;
  const programs = getPrograms(props);
  return <AbsoluteFill style={{background: "#f5f0e8"}}>{programs.map((program) => {
    const durationInFrames = Math.max(1, program.durationInFrames);
    const sceneFrom = from;
    from += durationInFrames;
    return <Sequence key={program.id} from={sceneFrom} durationInFrames={durationInFrames} premountFor={program.fps} name={`Agentic Scene · ${program.title ?? program.id}`}><SceneRuntime program={program}/>{toMediaSrc((program as AgenticSceneManifest).audioFile) ? <Audio src={toMediaSrc((program as AgenticSceneManifest).audioFile)} /> : null}</Sequence>;
  })}</AbsoluteFill>;
};

export const AgenticVideoFlowRoot: React.FC = () => <Composition
  id="AgenticVideoFlow"
  component={AgenticVideoFlowComposition}
  defaultProps={{program: defaultAgenticProgram, engineVersion: "agentic-visual.v1", title: "Agentic Video Flow"}}
  durationInFrames={defaultAgenticProgram.durationInFrames}
  fps={defaultAgenticProgram.fps}
  width={defaultAgenticProgram.width}
  height={defaultAgenticProgram.height}
  calculateMetadata={({props}) => {
    const rawProps = props as unknown as AgenticVideoFlowProps;
    const programs = getPrograms(rawProps);
    programs.forEach((program) => assertSceneProgram(program));
    const fps = typeof rawProps.fps === "number" && Number.isFinite(rawProps.fps) && rawProps.fps > 0 ? rawProps.fps : programs[0]?.fps || 24;
    const width = typeof rawProps.width === "number" && Number.isFinite(rawProps.width) && rawProps.width > 0 ? rawProps.width : programs[0]?.width || 1920;
    const height = typeof rawProps.height === "number" && Number.isFinite(rawProps.height) && rawProps.height > 0 ? rawProps.height : programs[0]?.height || 1080;
    const renderClasses = programs.map((program) => preflightScene(program).renderClass);
    const metadata = rawProps.metadata && typeof rawProps.metadata === "object" ? rawProps.metadata : {};
    return {
      durationInFrames: totalDuration(programs),
      fps,
      width,
      height,
      defaultOutName: `${rawProps.title || "agentic-video-flow"}.mp4`,
      props: {...rawProps, engineVersion: rawProps.engineVersion || "agentic-visual.v1", metadata: {...metadata, renderClasses}},
    };
  }}
/>;

export {AgenticVideoFlowComposition};


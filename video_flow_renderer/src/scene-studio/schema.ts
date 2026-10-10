import type React from "react";

/**
 * The Scene Studio contract is deliberately low level.  It describes the
 * things the renderer knows how to draw, but it does not prescribe a
 * completed layout (a scene author is free to compose and nest these nodes in
 * any way).
 */

export type RenderClass =
  | "static"
  | "motion-island"
  | "continuous-2d"
  | "webgl-3d"
  | "media";

export type NodeType =
  | "group"
  | "rect"
  | "roundRect"
  | "ellipse"
  | "circle"
  | "line"
  | "path"
  | "text"
  | "image"
  | "chart"
  | "network"
  | "timeline"
  | "media"
  | "three"
  | "custom";

/** A serialisable frame expression. Strings are parsed by expression.ts. */
export type FrameExpression =
  | number
  | string
  | {value: FrameExpression}
  | {op: "add" | "sub" | "mul" | "div" | "mod" | "pow"; left: FrameExpression; right: FrameExpression}
  | {op: "min" | "max"; values: FrameExpression[]}
  | {op: "clamp"; value: FrameExpression; min: FrameExpression; max: FrameExpression}
  | {op: "lerp"; from: FrameExpression; to: FrameExpression; progress: FrameExpression}
  | {op: "sin" | "cos" | "tan" | "abs" | "sqrt" | "floor" | "ceil" | "round"; value: FrameExpression}
  | {op: "smoothstep"; value: FrameExpression}
  | {op: "interpolate"; input: FrameExpression; inputRange: number[]; outputRange: number[]}
  | {op: "spring"; frame?: FrameExpression; from?: number; to?: number; duration?: number; damping?: number; stiffness?: number}
  | {op: "anchor"; id: string; field?: "start" | "end" | "center" | "progress"};

export type Scalar = number | string | FrameExpression;

export type Point = {x: Scalar; y: Scalar; z?: Scalar};

export type Color = string | FrameExpression;

export type LayoutSpec = {
  /** `absolute` places children at coordinates; `flow` uses flex layout. */
  mode?: "absolute" | "flow";
  position?: "absolute" | "relative";
  x?: Scalar;
  y?: Scalar;
  z?: Scalar;
  width?: Scalar;
  height?: Scalar;
  minWidth?: Scalar;
  minHeight?: Scalar;
  maxWidth?: Scalar;
  maxHeight?: Scalar;
  direction?: "row" | "column" | "row-reverse" | "column-reverse";
  gap?: Scalar;
  padding?: Scalar | [Scalar, Scalar] | [Scalar, Scalar, Scalar, Scalar];
  align?: "start" | "center" | "end" | "stretch";
  justify?: "start" | "center" | "end" | "space-between" | "space-around" | "space-evenly";
  wrap?: boolean;
  overflow?: "visible" | "hidden";
};

export type TransformSpec = {
  x?: Scalar;
  y?: Scalar;
  z?: Scalar;
  scale?: Scalar;
  scaleX?: Scalar;
  scaleY?: Scalar;
  scaleZ?: Scalar;
  rotate?: Scalar;
  rotateX?: Scalar;
  rotateY?: Scalar;
  rotateZ?: Scalar;
  skewX?: Scalar;
  skewY?: Scalar;
  origin?: string;
  perspective?: Scalar;
};

export type StrokeSpec = {
  color?: Color;
  width?: Scalar;
  opacity?: Scalar;
  dash?: Scalar[];
  cap?: "butt" | "round" | "square";
  join?: "miter" | "round" | "bevel";
};

export type ShadowSpec = {color: Color; blur: Scalar; x?: Scalar; y?: Scalar; spread?: Scalar};

export type NodeStyle = {
  fill?: Color;
  background?: Color;
  stroke?: StrokeSpec;
  opacity?: Scalar;
  visible?: Scalar;
  borderRadius?: Scalar;
  borderWidth?: Scalar;
  borderColor?: Color;
  shadow?: ShadowSpec;
  blendMode?: React.CSSProperties["mixBlendMode"];
  clipPath?: string;
  objectFit?: "contain" | "cover" | "fill" | "none";
  objectPosition?: string;
  fontFamily?: string;
  fontSize?: Scalar;
  fontWeight?: Scalar;
  lineHeight?: Scalar;
  letterSpacing?: Scalar;
  color?: Color;
  textAlign?: "left" | "center" | "right" | "justify";
  textTransform?: "none" | "uppercase" | "lowercase" | "capitalize";
  whiteSpace?: "normal" | "nowrap" | "pre" | "pre-line" | "pre-wrap";
  italic?: boolean;
  textDecoration?: string;
  filter?: string;
};

export type MotionSpec = {
  /** A convenience entrance/exit window, expressed in scene-local frames. */
  enter?: {from?: FrameExpression; to?: FrameExpression; start?: FrameExpression; end?: FrameExpression; easing?: "linear" | "easeIn" | "easeOut" | "easeInOut"};
  exit?: {from?: FrameExpression; to?: FrameExpression; start?: FrameExpression; end?: FrameExpression; easing?: "linear" | "easeIn" | "easeOut" | "easeInOut"};
  /** Property-level keyframes; the property is resolved each frame. */
  keyframes?: Record<string, {at: FrameExpression; value: FrameExpression}[]>;
  /** A frame offset allows an agent to phase a node without changing layout. */
  offset?: FrameExpression;
};

export type TextSpec = {
  text: string | FrameExpression;
  /** Optional hierarchy role used by preflight and default typography. */
  role?: "display" | "title" | "heading" | "body" | "label" | "caption" | "code";
  maxLines?: number;
  fit?: "shrink" | "clip" | "wrap";
};

export type PathSpec = {
  d: string;
  /** Draw progress (0..1) is applied using a deterministic dash offset. */
  progress?: FrameExpression;
  markerStart?: "none" | "dot" | "arrow";
  markerEnd?: "none" | "dot" | "arrow";
};

export type ChartSpec = {
  kind: "bar" | "line" | "area" | "pie" | "donut";
  data: Array<{label?: string; value: number; color?: string}>;
  max?: number;
  axis?: boolean;
  grid?: boolean;
  animate?: FrameExpression;
  valueFormat?: "number" | "percent" | "compact";
};

export type NetworkNode = {id: string; label?: string; x?: Scalar; y?: Scalar; radius?: Scalar; color?: Color; group?: string};
export type NetworkEdge = {from: string; to: string; label?: string; color?: Color; width?: Scalar; progress?: FrameExpression; directed?: boolean};
export type NetworkSpec = {nodes: NetworkNode[]; edges: NetworkEdge[]; directed?: boolean; curved?: boolean; nodeLabels?: boolean};

export type TimelineItem = {id: string; label: string; start: Scalar; end?: Scalar; color?: Color; lane?: number; detail?: string};
export type TimelineSpec = {items: TimelineItem[]; min?: number; max?: number; axis?: boolean; lanes?: number; now?: FrameExpression};

export type MediaSpec = {src: string; kind: "video" | "audio"; volume?: Scalar; playbackRate?: Scalar; muted?: boolean; loop?: boolean; startFrom?: number};

export type ThreeFlowPath = {
  from: [Scalar, Scalar, Scalar];
  to: [Scalar, Scalar, Scalar];
  color?: Color;
  width?: Scalar;
  progress?: FrameExpression;
};

export type ThreeSpec = {
  primitive?: "box" | "sphere" | "cylinder" | "torus" | "plane";
  dimensions?: [Scalar, Scalar, Scalar];
  color?: Color;
  roughness?: Scalar;
  metalness?: Scalar;
  rotation?: [Scalar, Scalar, Scalar];
  position?: [Scalar, Scalar, Scalar];
  /** Optional frame-driven connectors for assemblies and cutaways. */
  flowPaths?: ThreeFlowPath[];
  /** A scene author may provide an adapter key for a vetted glTF asset. */
  assetKey?: string;
  illustrative?: boolean;
};

export type SemanticAnchor = {
  id: string;
  /** Absolute scene-local frame; expressions are allowed for generated programs. */
  start: FrameExpression;
  end?: FrameExpression;
  /** Optional semantic labels (e.g. `claim:launch`, `word:42`). */
  tags?: string[];
};

export type CameraSpec = {
  x?: Scalar;
  y?: Scalar;
  z?: Scalar;
  zoom?: Scalar;
  rotate?: Scalar;
  perspective?: Scalar;
  target?: Point;
};

export type AssetManifestItem = {
  id: string;
  src: string;
  kind: "image" | "video" | "audio" | "font" | "gltf" | "svg" | "other";
  provenance?: string;
  license?: string;
  width?: number;
  height?: number;
};

export type SceneNode = {
  id: string;
  type: NodeType;
  layout?: LayoutSpec;
  transform?: TransformSpec;
  style?: NodeStyle;
  motion?: MotionSpec;
  /** Semantic anchors on a node make narration alignment inspectable. */
  anchors?: string[];
  children?: SceneNode[];
  zIndex?: Scalar;
  /** Node-specific payload. Keeping this open makes the graph forward-compatible. */
  text?: TextSpec;
  path?: PathSpec;
  points?: Point[];
  chart?: ChartSpec;
  network?: NetworkSpec;
  timeline?: TimelineSpec;
  media?: MediaSpec;
  three?: ThreeSpec;
  src?: string;
  alt?: string;
  radius?: Scalar;
  shape?: "rect" | "roundRect" | "ellipse" | "circle" | "triangle" | "diamond" | "star" | "polygon";
  data?: unknown;
  [key: string]: unknown;
};

export type SceneProgram = {
  version?: string;
  id: string;
  title?: string;
  fps: number;
  width: number;
  height: number;
  durationInFrames: number;
  renderClass: RenderClass;
  estimatedCost?: {cpuMs?: number; memoryMb?: number; gpu?: boolean; elementCount?: number};
  background?: Color;
  root: SceneNode;
  anchors?: SemanticAnchor[];
  assets?: AssetManifestItem[];
  camera?: CameraSpec;
  metadata?: Record<string, unknown>;
};

export type ScenePreflightIssue = {
  level: "error" | "warning";
  code: string;
  message: string;
  nodeId?: string;
  path?: string;
};

export type ScenePreflightReport = {
  ok: boolean;
  issues: ScenePreflightIssue[];
  renderClass: RenderClass;
  estimatedElementCount: number;
  maxDepth: number;
  anchors: string[];
};


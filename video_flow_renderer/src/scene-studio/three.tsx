import React from "react";
import {ThreeCanvas} from "@remotion/three";
import type {CameraSpec, SceneNode, ThreeFlowPath} from "./schema";
import {clamp, ease, resolveScalar, toNumber, type FrameRuntime} from "./expression";

/**
 * Optional bridge for @remotion/three + three.
 *
 * The core runtime never imports WebGL eagerly. A host that has installed the
 * optional packages can register an adapter on globalThis (or pass one to
 * createThreeAdapter) and receive the same frame runtime as the 2D path.
 * Every value below is resolved from the current frame; there is no
 * React Three Fiber useFrame() loop.
 */
export type ThreeCamera = {
  fov?: number;
  near?: number;
  far?: number;
  position?: [number, number, number];
  zoom?: number;
};

export type ThreeAdapter = {
  ThreeCanvas: React.ComponentType<{
    width: number;
    height: number;
    orthographic?: boolean;
    camera?: ThreeCamera;
    children?: React.ReactNode;
  }>;
  renderNode: (args: {
    node: SceneNode;
    runtime: FrameRuntime;
    width: number;
    height: number;
    camera?: CameraSpec;
    /** Lighting is explicit so a host adapter can map it to Three.js lights. */
    lights: {ambient: number; key: number; fill: number};
  }) => React.ReactNode;
};

const globalKey = "__SCENE_STUDIO_THREE__";

export const createThreeAdapter = (adapter: ThreeAdapter) => adapter;

export const registerThreeAdapter = (adapter: ThreeAdapter) => {
  (globalThis as Record<string, unknown>)[globalKey] = adapter;
  return adapter;
};

const scalar = (value: unknown, runtime: FrameRuntime, fallback = 0) =>
  toNumber(resolveScalar(value as never, runtime, fallback), fallback);

const finite = (value: number, fallback = 0) => Number.isFinite(value) ? value : fallback;
const rad = (degrees: number) => degrees * Math.PI / 180;

const DefaultCanvas: ThreeAdapter["ThreeCanvas"] = ({width = 640, height = 360, camera, children}) =>
  <ThreeCanvas
    width={Math.max(1, Math.round(width))}
    height={Math.max(1, Math.round(height))}
    orthographic={false}
    camera={camera ?? {fov: 42, near: 0.1, far: 1000, position: [0, 0, 7]}}
  >
    {children}
  </ThreeCanvas>;

const collectThreeNodes = (root: SceneNode) => {
  const result: SceneNode[] = [];
  const visit = (candidate: unknown) => {
    if (!candidate || typeof candidate !== "object") return;
    const node = candidate as SceneNode;
    if (node.type === "three") {
      result.push(node);
      for (const child of Array.isArray(node.children) ? node.children : []) visit(child);
      return;
    }
    for (const child of Array.isArray(node.children) ? node.children : []) visit(child);
  };
  // A group can be promoted to an assembly by the renderer. In that case only
  // its children are geometry; a normal three node is geometry itself.
  if (root.type === "three" && root.three) result.push(root);
  for (const child of Array.isArray(root.children) ? root.children : []) visit(child);
  return result;
};

const frameReveal = (node: SceneNode, runtime: FrameRuntime) => {
  const motion = node.motion;
  let opacity = scalar(node.style?.opacity, runtime, 1);
  if (motion?.enter) {
    const start = scalar(motion.enter.start, runtime, 0);
    const end = scalar(motion.enter.end, runtime, Math.min(runtime.durationInFrames, start + Math.round(runtime.fps * 0.5)));
    opacity *= ease(end === start ? (runtime.frame >= start ? 1 : 0) : (runtime.frame - start) / Math.max(1, end - start), motion.enter.easing);
  }
  if (motion?.exit) {
    const start = scalar(motion.exit.start, runtime, Math.max(0, runtime.durationInFrames - Math.round(runtime.fps * 0.5)));
    const end = scalar(motion.exit.end, runtime, runtime.durationInFrames);
    opacity *= 1 - ease(end === start ? (runtime.frame >= end ? 1 : 0) : (runtime.frame - start) / Math.max(1, end - start), motion.exit.easing);
  }
  return clamp(opacity, 0, 1);
};

const dimensionsFor = (node: SceneNode, runtime: FrameRuntime): [number, number, number] => {
  const dimensions = Array.isArray(node.three?.dimensions) ? node.three.dimensions : [1.8, 1.8, 1.8];
  return [0, 1, 2].map((index) => Math.max(0.02, finite(scalar(dimensions[index], runtime, 1.8), 1.8))) as [number, number, number];
};

const layoutPositionFor = (node: SceneNode, runtime: FrameRuntime, width: number, height: number, root: boolean): [number, number, number] => {
  const spec = node.three;
  const explicit = Array.isArray(spec?.position) ? spec.position : undefined;
  const position = explicit
    ? [0, 1, 2].map((index) => scalar(explicit[index], runtime, 0)) as [number, number, number]
    : [0, 0, 0] as [number, number, number];
  if (!explicit && !root && (node.layout?.x !== undefined || node.layout?.y !== undefined)) {
    const x = scalar(node.layout?.x, runtime, 0) + scalar(node.layout?.width, runtime, 0) / 2;
    const y = scalar(node.layout?.y, runtime, 0) + scalar(node.layout?.height, runtime, 0) / 2;
    // Keep layout-authored assemblies readable while retaining normal Three.js
    // units for explicit positions.
    position[0] += (x / Math.max(1, width) - 0.5) * 8;
    position[1] += (0.5 - y / Math.max(1, height)) * 4.5;
  }
  position[0] += scalar(node.transform?.x, runtime) / Math.max(1, width) * 8;
  position[1] -= scalar(node.transform?.y, runtime) / Math.max(1, height) * 4.5;
  position[2] += scalar(node.transform?.z, runtime);
  position[0] += scalar(node.motion?.offset, runtime);
  return position;
};

const rotationFor = (node: SceneNode, runtime: FrameRuntime): [number, number, number] => {
  const rotation = Array.isArray(node.three?.rotation) ? node.three.rotation : [0, 0, 0];
  return [
    scalar(rotation[0], runtime) + rad(scalar(node.transform?.rotateX, runtime)),
    scalar(rotation[1], runtime) + rad(scalar(node.transform?.rotateY, runtime)),
    scalar(rotation[2], runtime) + rad(scalar(node.transform?.rotateZ, runtime)),
  ];
};

const colorFor = (node: SceneNode, runtime: FrameRuntime) =>
  String(resolveScalar(node.three?.color ?? node.style?.fill ?? "#8bd7e6", runtime, 0));

const primitiveFor = (node: SceneNode) => {
  const primitive = String(node.three?.primitive ?? "box");
  return ["box", "sphere", "cylinder", "torus", "plane"].includes(primitive) ? primitive : "box";
};

const geometryFor = (node: SceneNode, runtime: FrameRuntime) => {
  const [sx, sy, sz] = dimensionsFor(node, runtime);
  const primitive = primitiveFor(node);
  const geometryArgs: Record<string, number[]> = {
    box: [sx, sy, sz],
    sphere: [sx / 2, 48, 32],
    cylinder: [sx / 2, sy / 2, sz, 48],
    torus: [sx / 2, Math.max(0.04, sy / 6), 24, 64],
    plane: [sx, sy, 1, 1],
  };
  return {primitive, args: geometryArgs[primitive] ?? geometryArgs.box};
};

const pointFor = (point: [unknown, unknown, unknown], runtime: FrameRuntime): [number, number, number] =>
  [0, 1, 2].map((index) => scalar(point?.[index], runtime, 0)) as [number, number, number];

const renderBeam = (path: ThreeFlowPath, runtime: FrameRuntime, index: number) => {
  if (!Array.isArray(path?.from) || !Array.isArray(path?.to)) return null;
  const from = pointFor(path.from, runtime);
  const target = pointFor(path.to, runtime);
  const progress = clamp(scalar(path.progress, runtime, 1));
  const to: [number, number, number] = [
    from[0] + (target[0] - from[0]) * progress,
    from[1] + (target[1] - from[1]) * progress,
    from[2] + (target[2] - from[2]) * progress,
  ];
  const delta: [number, number, number] = [to[0] - from[0], to[1] - from[1], to[2] - from[2]];
  const length = Math.max(0.01, Math.hypot(delta[0], delta[1], delta[2]));
  const width = Math.max(0.01, scalar(path.width, runtime, 0.055));
  const midpoint: [number, number, number] = [(from[0] + to[0]) / 2, (from[1] + to[1]) / 2, (from[2] + to[2]) / 2];
  const horizontal = Math.hypot(delta[0], delta[2]);
  const rotation: [number, number, number] = [
    Math.atan2(delta[1], Math.max(0.0001, horizontal)),
    Math.atan2(delta[0], Math.max(0.0001, delta[2])),
    0,
  ];
  return <mesh key={"flow-" + index} position={midpoint} rotation={rotation} castShadow>
    <boxGeometry args={[width, width, length]}/>
    <meshStandardMaterial color={String(resolveScalar(path.color ?? "#f5b942", runtime, 0))} roughness={0.45} metalness={0.12}/>
  </mesh>;
};

const renderPrimitive = (node: SceneNode, runtime: FrameRuntime, width: number, height: number, root: boolean) => {
  const {primitive, args} = geometryFor(node, runtime);
  const position = layoutPositionFor(node, runtime, width, height, root);
  const rotation = rotationFor(node, runtime);
  const opacity = frameReveal(node, runtime);
  const spec = node.three ?? {};
  return <group key={node.id} position={position} rotation={rotation}>
    <mesh castShadow receiveShadow scale={[1, 1, 1]} visible={opacity > 0} >
      {React.createElement(primitive + "Geometry", {args})}
      <meshStandardMaterial
        color={colorFor(node, runtime)}
        transparent={opacity < 1}
        opacity={opacity}
        roughness={clamp(scalar(spec.roughness, runtime, 0.62), 0, 1)}
        metalness={clamp(scalar(spec.metalness, runtime, 0.08), 0, 1)}
      />
    </mesh>
    {(Array.isArray(spec.flowPaths) ? spec.flowPaths : []).map((path, index) => renderBeam(path, runtime, index))}
  </group>;
};

const defaultRenderNode: ThreeAdapter["renderNode"] = ({node, runtime, width, height, lights, camera}) => {
  const geometryNodes = collectThreeNodes(node);
  const cameraX = scalar(camera?.x, runtime) / Math.max(1, width) * 8;
  const cameraY = -scalar(camera?.y, runtime) / Math.max(1, height) * 4.5;
  const cameraZ = scalar(camera?.z, runtime);
  const zoom = Math.max(0.1, scalar(camera?.zoom, runtime, 1));
  const cameraRotation = rad(scalar(camera?.rotate, runtime));
  const cameraGroupPosition: [number, number, number] = [cameraX, cameraY, cameraZ];
  return <>
    <ambientLight intensity={lights.ambient}/>
    <directionalLight position={[4, 6, 8]} intensity={lights.key}/>
    <directionalLight position={[-5, -2, 4]} intensity={lights.fill}/>
    <group position={cameraGroupPosition} scale={[zoom, zoom, zoom]} rotation={[0, 0, cameraRotation]}>
      {geometryNodes.map((child, index) => renderPrimitive(child, runtime, width, height, index === 0 && child === node))}
    </group>
  </>;
};

const defaultAdapter = createThreeAdapter({
  ThreeCanvas: DefaultCanvas,
  renderNode: defaultRenderNode,
});

export const getThreeAdapter = () =>
  ((globalThis as Record<string, unknown>)[globalKey] as ThreeAdapter | undefined) ?? defaultAdapter;

class ThreeBoundary extends React.Component<{fallback: React.ReactNode; children: React.ReactNode}, {failed: boolean}> {
  state = {failed: false};
  static getDerivedStateFromError() {
    return {failed: true};
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

export const ThreeNode: React.FC<{
  node: SceneNode;
  runtime: FrameRuntime;
  width: number;
  height: number;
  camera?: CameraSpec;
  fallback: React.ReactNode;
}> = ({node, runtime, width, height, camera, fallback}) => {
  const adapter = getThreeAdapter();
  const Canvas = adapter.ThreeCanvas;
  const canvasWidth = Math.max(1, Math.round(finite(width, 1)));
  const canvasHeight = Math.max(1, Math.round(finite(height, 1)));
  const cameraConfig: ThreeCamera = {
    fov: Math.max(10, scalar(camera?.perspective, runtime, 42)),
    near: 0.1,
    far: 1000,
    position: [scalar(camera?.x, runtime) / Math.max(1, canvasWidth) * 8, scalar(camera?.y, runtime) / Math.max(1, canvasHeight) * 4.5, Math.max(2, 7 + scalar(camera?.z, runtime))],
  };
  return <ThreeBoundary fallback={fallback}><Canvas width={canvasWidth} height={canvasHeight} orthographic={false} camera={cameraConfig}><>{adapter.renderNode({node, runtime, width: canvasWidth, height: canvasHeight, camera, lights: {ambient: 0.45, key: 1.1, fill: 0.35}})}</></Canvas></ThreeBoundary>;
};


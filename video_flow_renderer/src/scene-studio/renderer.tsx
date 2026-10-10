import React, {useMemo} from "react";
import {Audio, Video} from "@remotion/media";
import {AbsoluteFill, Img, Sequence, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from "remotion";
import type {CSSProperties, ReactNode} from "react";
import type {FrameExpression, LayoutSpec, NodeStyle, SceneNode, SceneProgram, Scalar, TransformSpec} from "./schema";
import {clamp, ease, resolveFrameExpression, resolveScalar, runtimeFor, toNumber, type FrameRuntime} from "./expression";
import {preflightScene} from "./validate";
import {ThreeNode} from "./three";

type Box = {x: number; y: number; width: number; height: number; z: number};

const asString = (value: unknown, fallback = "") => typeof value === "string" ? value : String(value ?? fallback);
const asColor = (value: unknown, fallback = "transparent") => typeof value === "string" ? value : fallback;
const resolveAssetSrc = (source: string | undefined, program: SceneProgram) => {
  const declared = Array.isArray(program.assets) ? program.assets.find((asset) => asset?.id === source) : undefined;
  const src = declared?.src ?? source ?? "";
  if (typeof src !== "string" || !src.trim()) return "";
  return /^(?:https?:|data:|blob:)/.test(src) ? src : staticFile(src);
};


const scalar = (value: Scalar | undefined, runtime: FrameRuntime, fallback = 0) => toNumber(resolveScalar(value, runtime, fallback), fallback);

const padding = (value: LayoutSpec["padding"], runtime: FrameRuntime): [number, number, number, number] => {
  if (value === undefined) return [0, 0, 0, 0];
  if (Array.isArray(value)) {
    if (value.length === 2) return [scalar(value[0], runtime), scalar(value[1], runtime), scalar(value[0], runtime), scalar(value[1], runtime)];
    return [scalar(value[0], runtime), scalar(value[1], runtime), scalar(value[2], runtime), scalar(value[3], runtime)];
  }
  const amount = scalar(value, runtime);
  return [amount, amount, amount, amount];
};

const resolveTransform = (transform: TransformSpec | undefined, runtime: FrameRuntime) => {
  if (!transform) return "";
  const tx = scalar(transform.x, runtime);
  const ty = scalar(transform.y, runtime);
  const tz = scalar(transform.z, runtime);
  const sx = transform.scaleX === undefined ? scalar(transform.scale, runtime, 1) : scalar(transform.scaleX, runtime, 1);
  const sy = transform.scaleY === undefined ? scalar(transform.scale, runtime, 1) : scalar(transform.scaleY, runtime, 1);
  const sz = transform.scaleZ === undefined ? scalar(transform.scale, runtime, 1) : scalar(transform.scaleZ, runtime, 1);
  const values = [
    `translate3d(${tx}px, ${ty}px, ${tz}px)`,
    `scale3d(${sx}, ${sy}, ${sz})`,
    `rotate(${scalar(transform.rotate, runtime)}deg)`,
    `rotateX(${scalar(transform.rotateX, runtime)}deg)`,
    `rotateY(${scalar(transform.rotateY, runtime)}deg)`,
    `rotateZ(${scalar(transform.rotateZ, runtime)}deg)`,
    `skew(${scalar(transform.skewX, runtime)}deg, ${scalar(transform.skewY, runtime)}deg)`,
  ];
  return values.join(" ");
};

const styleFor = (style: NodeStyle | undefined, runtime: FrameRuntime): CSSProperties => {
  if (!style) return {};
  const shadow = style.shadow ? `${scalar(style.shadow.x, runtime)}px ${scalar(style.shadow.y, runtime)}px ${scalar(style.shadow.blur, runtime)}px ${asColor(resolveScalar(style.shadow.color, runtime), "#0004")}` : undefined;
  return {
    background: asColor(resolveScalar(style.background ?? style.fill, runtime), "transparent"),
    color: asColor(resolveScalar(style.color, runtime), "inherit"),
    opacity: scalar(style.opacity, runtime, 1),
    borderRadius: scalar(style.borderRadius, runtime) || undefined,
    border: style.borderWidth !== undefined || style.borderColor !== undefined ? `${scalar(style.borderWidth, runtime, 1)}px solid ${asColor(resolveScalar(style.borderColor, runtime), "transparent")}` : undefined,
    boxShadow: shadow,
    mixBlendMode: style.blendMode,
    clipPath: style.clipPath,
    fontFamily: style.fontFamily,
    fontSize: style.fontSize === undefined ? undefined : scalar(style.fontSize, runtime),
    fontWeight: style.fontWeight === undefined ? undefined : scalar(style.fontWeight, runtime),
    lineHeight: style.lineHeight === undefined ? undefined : scalar(style.lineHeight, runtime),
    letterSpacing: style.letterSpacing === undefined ? undefined : scalar(style.letterSpacing, runtime),
    textAlign: style.textAlign,
    textTransform: style.textTransform,
    whiteSpace: style.whiteSpace,
    fontStyle: style.italic ? "italic" : undefined,
    textDecoration: style.textDecoration,
    filter: style.filter,
  };
};

const initialBox = (node: SceneNode, runtime: FrameRuntime, parent: Box): Box => ({
  x: parent.x + scalar(node.layout?.x, runtime),
  y: parent.y + scalar(node.layout?.y, runtime),
  width: Math.max(0, scalar(node.layout?.width, runtime, parent.width)),
  height: Math.max(0, scalar(node.layout?.height, runtime, parent.height)),
  z: scalar(node.layout?.z, runtime, 0) + scalar(node.zIndex, runtime, 0),
});

const layoutChildren = (node: SceneNode, runtime: FrameRuntime, box: Box) => {
  const children = (Array.isArray(node.children) ? node.children : []).filter((child): child is SceneNode => Boolean(child && typeof child === "object"));
  const mode = node.layout?.mode ?? "absolute";
  if (mode !== "flow") return children.map((child) => initialBox(child, runtime, box));
  const direction = node.layout?.direction ?? "row";
  const isRow = direction === "row" || direction === "row-reverse";
  const reverse = direction === "row-reverse" || direction === "column-reverse";
  const [top, right, bottom, left] = padding(node.layout?.padding, runtime);
  const gap = scalar(node.layout?.gap, runtime);
  const contentWidth = Math.max(0, box.width - left - right);
  const contentHeight = Math.max(0, box.height - top - bottom);
  const totalBasis = children.reduce((sum, child) => sum + scalar(isRow ? child.layout?.width : child.layout?.height, runtime, 0), 0);
  const free = (isRow ? contentWidth : contentHeight) - totalBasis - Math.max(0, children.length - 1) * gap;
  const justify = node.layout?.justify ?? "start";
  const extra = justify === "space-between" && children.length > 1 ? free / (children.length - 1) : justify === "space-around" && children.length > 0 ? free / children.length : justify === "space-evenly" && children.length > 0 ? free / (children.length + 1) : 0;
  let cursor = isRow ? left : top;
  if (justify === "center") cursor += free / 2;
  if (justify === "end") cursor += free;
  if (justify === "space-around") cursor += extra / 2;
  if (justify === "space-evenly") cursor += extra;
  const boxes = children.map((child) => {
    const width = scalar(child.layout?.width, runtime, isRow ? Math.max(0, free / Math.max(1, children.length)) : contentWidth);
    const height = scalar(child.layout?.height, runtime, isRow ? contentHeight : Math.max(0, free / Math.max(1, children.length)));
    const cross = isRow ? scalar(child.layout?.y, runtime, 0) : scalar(child.layout?.x, runtime, 0);
    const align = node.layout?.align ?? "start";
    const crossSize = isRow ? contentHeight : contentWidth;
    const childCross = isRow ? height : width;
    const alignOffset = align === "center" ? (crossSize - childCross) / 2 : align === "end" ? crossSize - childCross : 0;
    const result: Box = {x: box.x + (isRow ? cursor : left + cross + alignOffset), y: box.y + (isRow ? top + cross + alignOffset : cursor), width, height, z: box.z + scalar(child.zIndex, runtime)};
    cursor += (isRow ? width : height) + gap + extra;
    return result;
  });
  return reverse ? boxes.reverse() : boxes;
};

const revealOpacity = (node: SceneNode, runtime: FrameRuntime) => {
  const motion = node.motion;
  let opacity = scalar(node.style?.opacity, runtime, 1);
  if (motion?.enter) {
    const start = scalar(motion.enter.start, runtime, 0);
    const end = scalar(motion.enter.end, runtime, Math.min(runtime.durationInFrames, start + Math.round(runtime.fps * 0.5)));
    opacity *= ease(end === start ? (runtime.frame >= start ? 1 : 0) : (runtime.frame - start) / (end - start), motion.enter.easing);
  }
  if (motion?.exit) {
    const start = scalar(motion.exit.start, runtime, Math.max(0, runtime.durationInFrames - Math.round(runtime.fps * 0.5)));
    const end = scalar(motion.exit.end, runtime, runtime.durationInFrames);
    opacity *= 1 - ease(end === start ? (runtime.frame >= end ? 1 : 0) : (runtime.frame - start) / (end - start), motion.exit.easing);
  }
  return clamp(opacity, 0, 1);
};

const motionStyle = (node: SceneNode, runtime: FrameRuntime) => {
  const style: CSSProperties = {};
  for (const [property, keyframes] of Object.entries(node.motion?.keyframes ?? {})) {
    if (!keyframes.length) continue;
    const frames = keyframes.map((keyframe) => ({at: scalar(keyframe.at, runtime), value: resolveFrameExpression(keyframe.value, runtime)})).sort((a, b) => a.at - b.at);
    const before = frames[0];
    const after = frames[frames.length - 1];
    const left = frames.find((item) => item.at <= runtime.frame) ?? before;
    const right = frames.find((item) => item.at >= runtime.frame) ?? after;
    const progress = left === right ? 1 : clamp((runtime.frame - left.at) / Math.max(1, right.at - left.at));
    const value = typeof left.value === "number" && typeof right.value === "number" ? left.value + (right.value - left.value) * progress : (progress < 1 ? left.value : right.value);
    (style as Record<string, unknown>)[property] = value;
  }
  return style;
};

const NodeBox: React.FC<{node: SceneNode; box: Box; runtime: FrameRuntime; children?: ReactNode}> = ({node, box, runtime, children}) => {
  const transform = [resolveTransform(node.transform, runtime), node.motion?.offset ? `translateX(${scalar(node.motion.offset, runtime)}px)` : ""].filter(Boolean).join(" ");
  const style: CSSProperties = {
    position: "absolute",
    left: box.x,
    top: box.y,
    width: box.width,
    height: box.height,
    zIndex: box.z,
    transform: transform || undefined,
    transformOrigin: node.transform?.origin,
    perspective: node.transform?.perspective ? scalar(node.transform.perspective, runtime) : undefined,
    opacity: revealOpacity(node, runtime),
    overflow: node.layout?.overflow === "hidden" ? "hidden" : undefined,
    ...styleFor(node.style, runtime),
    ...motionStyle(node, runtime),
  };
  return <div data-scene-node={node.id} style={style}>{children}</div>;
};

const TextNode: React.FC<{node: SceneNode; runtime: FrameRuntime}> = ({node, runtime}) => {
  const text = node.text?.text;
  const value = typeof text === "string" ? asString(resolveFrameExpression(text, runtime), text) : asString(text, "");
  return <span style={{display: "block", width: "100%", height: "100%", overflow: node.text?.fit === "clip" ? "hidden" : undefined}}>{value}</span>;
};

const SvgShape: React.FC<{node: SceneNode; runtime: FrameRuntime; box: Box}> = ({node, runtime, box}) => {
  const fill = asColor(resolveScalar(node.style?.fill ?? node.style?.background, runtime), "transparent");
  const stroke = node.style?.stroke;
  const strokeColor = asColor(resolveScalar(stroke?.color, runtime), "transparent");
  const strokeWidth = scalar(stroke?.width, runtime);
  const common = {fill, stroke: strokeColor, strokeWidth, opacity: scalar(node.style?.opacity, runtime, 1)};
  const points = Array.isArray(node.points) ? node.points : [];
  if (node.type === "line" && points.length >= 2) {
    const [from, to] = points;
    return <svg width={box.width} height={box.height} viewBox={`0 0 ${box.width} ${box.height}`} style={{overflow: "visible"}}><line x1={scalar(from.x, runtime)} y1={scalar(from.y, runtime)} x2={scalar(to.x, runtime)} y2={scalar(to.y, runtime)} {...common} strokeLinecap={stroke?.cap}/></svg>;
  }
  if (node.type === "path") {
    const progress = clamp(scalar(node.path?.progress, runtime, 1));
    const length = Math.max(box.width + box.height, 1) * 4;
    return <svg width={box.width} height={box.height} viewBox={`0 0 ${box.width} ${box.height}`} style={{overflow: "visible"}}><path d={node.path?.d ?? ""} {...common} fill="none" strokeDasharray={length} strokeDashoffset={length * (1 - progress)} strokeLinecap={stroke?.cap} strokeLinejoin={stroke?.join}/></svg>;
  }
  if (node.type === "ellipse" || node.type === "circle") return <svg width={box.width} height={box.height} viewBox={`0 0 ${box.width} ${box.height}`}><ellipse cx={box.width / 2} cy={box.height / 2} rx={box.width / 2} ry={box.height / 2} {...common}/></svg>;
  const radius = node.type === "roundRect" ? scalar(node.style?.borderRadius, runtime, Math.min(box.width, box.height) * 0.12) : 0;
  return <svg width={box.width} height={box.height} viewBox={`0 0 ${box.width} ${box.height}`}><rect x={0} y={0} width={box.width} height={box.height} rx={radius} {...common}/></svg>;
};

const ChartNode: React.FC<{node: SceneNode; runtime: FrameRuntime; box: Box}> = ({node, runtime, box}) => {
  const chart = node.chart;
  if (!chart) return null;
  const data = chart.data ?? [];
  const max = chart.max ?? Math.max(1, ...data.map((item) => item.value));
  const progress = clamp(scalar(chart.animate, runtime, 1));
  const pad = Math.min(36, box.width * 0.08);
  const innerWidth = Math.max(1, box.width - pad * 2);
  const innerHeight = Math.max(1, box.height - pad * 2);
  if (chart.kind === "pie" || chart.kind === "donut") {
    const total = Math.max(1, data.reduce((sum, item) => sum + Math.max(0, item.value), 0));
    let cursor = -Math.PI / 2;
    const radius = Math.min(box.width, box.height) * 0.34;
    const center = {x: box.width / 2, y: box.height / 2};
    const segments = data.map((item, index) => {
      const angle = (item.value / total) * Math.PI * 2 * progress;
      const from = {x: center.x + Math.cos(cursor) * radius, y: center.y + Math.sin(cursor) * radius};
      cursor += angle;
      const to = {x: center.x + Math.cos(cursor) * radius, y: center.y + Math.sin(cursor) * radius};
      const large = angle > Math.PI ? 1 : 0;
      return <path key={item.label ?? index} d={`M ${center.x} ${center.y} L ${from.x} ${from.y} A ${radius} ${radius} 0 ${large} 1 ${to.x} ${to.y} Z`} fill={item.color ?? `hsl(${index * 53} 68% 56%)`} stroke="white" strokeWidth={2}/>;
    });
    return <svg width={box.width} height={box.height} viewBox={`0 0 ${box.width} ${box.height}`}>{segments}{chart.kind === "donut" && <circle cx={center.x} cy={center.y} r={radius * 0.52} fill="white"/>}</svg>;
  }
  const points = data.map((item, index) => ({x: pad + (index / Math.max(1, data.length - 1)) * innerWidth, y: pad + innerHeight - (item.value / max) * innerHeight * progress}));
  if (chart.kind === "line" || chart.kind === "area") {
    const path = points.map((point, index) => `${index ? "L" : "M"} ${point.x} ${point.y}`).join(" ");
    const area = `${path} L ${pad + innerWidth} ${pad + innerHeight} L ${pad} ${pad + innerHeight} Z`;
    return <svg width={box.width} height={box.height} viewBox={`0 0 ${box.width} ${box.height}`}>
      {chart.grid && <line x1={pad} y1={pad + innerHeight} x2={pad + innerWidth} y2={pad + innerHeight} stroke="#aaa"/>}
      {chart.kind === "area" && <path d={area} fill={asColor(resolveScalar(node.style?.fill, runtime), "#8bd7e6")} opacity={0.35}/>}<path d={path} fill="none" stroke={asColor(resolveScalar(node.style?.stroke?.color, runtime), "#ff8a1f")} strokeWidth={Math.max(2, scalar(node.style?.stroke?.width, runtime, 4))}/>{points.map((point, index) => <circle key={index} cx={point.x} cy={point.y} r={4} fill={data[index]?.color ?? "#ff8a1f"}/>)}</svg>;
  }
  const barWidth = innerWidth / Math.max(1, data.length) * 0.72;
  return <svg width={box.width} height={box.height} viewBox={`0 0 ${box.width} ${box.height}`}>{data.map((item, index) => {const height = (item.value / max) * innerHeight * progress; const x = pad + (index + 0.14) * (innerWidth / Math.max(1, data.length)); return <rect key={item.label ?? index} x={x} y={pad + innerHeight - height} width={barWidth} height={height} rx={3} fill={item.color ?? `hsl(${index * 53} 68% 56%)`}/>;})}</svg>;
};

const NetworkNode: React.FC<{node: SceneNode; runtime: FrameRuntime; box: Box}> = ({node, runtime, box}) => {
  const network = node.network;
  if (!network) return null;
  const nodes = new Map(network.nodes.map((item) => [item.id, item]));
  const pointFor = (id: string) => {const item = nodes.get(id); return {x: scalar(item?.x, runtime, box.width / 2), y: scalar(item?.y, runtime, box.height / 2)};};
  return <svg width={box.width} height={box.height} viewBox={`0 0 ${box.width} ${box.height}`} style={{overflow: "visible"}}>
    <defs><marker id={`arrow-${node.id}`} markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="#6b7280"/></marker></defs>
    {network.edges.map((edge, index) => {const from = pointFor(edge.from); const to = pointFor(edge.to); const progress = clamp(scalar(edge.progress, runtime, 1)); const x = from.x + (to.x - from.x) * progress; const y = from.y + (to.y - from.y) * progress; return <line key={`${edge.from}-${edge.to}-${index}`} x1={from.x} y1={from.y} x2={x} y2={y} stroke={asColor(resolveScalar(edge.color, runtime), "#6b7280")} strokeWidth={scalar(edge.width, runtime, 3)} markerEnd={(edge.directed ?? network.directed) ? `url(#arrow-${node.id})` : undefined}/>;})}
    {network.nodes.map((item, index) => {const point = pointFor(item.id); const radius = scalar(item.radius, runtime, 20); return <g key={item.id}><circle cx={point.x} cy={point.y} r={radius} fill={asColor(resolveScalar(item.color, runtime), `hsl(${index * 47} 68% 56%)`)} stroke="white" strokeWidth={2}/>{network.nodeLabels !== false && item.label ? <text x={point.x} y={point.y + radius + 18} textAnchor="middle" fontSize={14} fill="#171717">{item.label}</text> : null}</g>;})}
  </svg>;
};

const TimelineNode: React.FC<{node: SceneNode; runtime: FrameRuntime; box: Box}> = ({node, runtime, box}) => {
  const timeline = node.timeline;
  if (!timeline) return null;
  const min = timeline.min ?? Math.min(0, ...timeline.items.map((item) => toNumber(item.start)));
  const max = timeline.max ?? Math.max(1, ...timeline.items.map((item) => toNumber(item.end ?? item.start) + 1));
  const span = Math.max(1, max - min);
  const lanes = Math.max(1, timeline.lanes ?? (Math.max(0, ...timeline.items.map((item) => item.lane ?? 0)) + 1));
  const laneHeight = box.height / lanes;
  return <svg width={box.width} height={box.height} viewBox={`0 0 ${box.width} ${box.height}`}>
    {timeline.axis !== false && <line x1={20} y1={box.height - 24} x2={box.width - 20} y2={box.height - 24} stroke="#8b8b8b"/>}
    {timeline.items.map((item) => {const start = toNumber(resolveScalar(item.start, runtime), min); const end = toNumber(resolveScalar(item.end ?? item.start, runtime), start + span * 0.1); const x = ((start - min) / span) * (box.width - 40) + 20; const width = Math.max(8, ((end - start) / span) * (box.width - 40)); const y = (item.lane ?? 0) * laneHeight + 8; return <g key={item.id}><rect x={x} y={y} width={width} height={Math.max(18, laneHeight - 16)} rx={7} fill={asColor(resolveScalar(item.color, runtime), "#8bd7e6")}/><text x={x + width / 2} y={y + Math.min(laneHeight - 20, 18)} textAnchor="middle" fontSize={Math.min(16, laneHeight * 0.35)} fill="#171717">{item.label}</text></g>;})}
  </svg>;
};

const ThreeFallback: React.FC<{node: SceneNode; runtime: FrameRuntime; box: Box}> = ({node, runtime, box}) => {
  const nodes: SceneNode[] = [];
  const visit = (candidate: unknown) => {
    if (!candidate || typeof candidate !== "object") return;
    const item = candidate as SceneNode;
    if (item.type === "three") nodes.push(item);
    for (const child of Array.isArray(item.children) ? item.children : []) visit(child);
  };
  visit(node);
  if (node.type === "three" && node.three && !nodes.includes(node)) nodes.unshift(node);
  const perspective = scalar(node.transform?.perspective, runtime, 800);
  return <div style={{position: "absolute", inset: 0, display: "grid", placeItems: "center", perspective}}>
    {nodes.map((item, index) => {
      const color = asColor(resolveScalar(item.three?.color ?? item.style?.fill, runtime), "#8bd7e6");
      const rotation = scalar(item.three?.rotation?.[1], runtime) + scalar(item.transform?.rotateY, runtime, 24);
      const primitive = String(item.three?.primitive ?? "box");
      const radius = primitive === "sphere" ? "50%" : primitive === "cylinder" ? 18 : 10;
      const offset = (index - (nodes.length - 1) / 2) * Math.min(box.width, box.height) * 0.16;
      const scale = Math.max(0.26, 0.6 - index * 0.025);
      return <div key={item.id} style={{position: "absolute", width: box.width * scale, height: box.height * scale, background: color, border: "2px solid #171717", borderRadius: radius, transform: `rotateX(${scalar(item.transform?.rotateX, runtime, 18)}deg) rotateY(${rotation}deg) rotateZ(${scalar(item.transform?.rotateZ, runtime)}deg)`, boxShadow: "18px 24px 0 #0002", opacity: scalar(item.style?.opacity, runtime, 1)}} />;
    })}
  </div>;
};

const SceneNodeRenderer: React.FC<{node: SceneNode; box: Box; runtime: FrameRuntime; program: SceneProgram}> = ({node, box, runtime, program}) => {
  const children = (Array.isArray(node.children) ? node.children : []).filter((child): child is SceneNode => Boolean(child && typeof child === "object"));
  // A group made entirely of Three nodes is rendered in one canvas so the
  // assembly shares depth, lights, camera motion, and frame timing.
  const isThreeAssembly = node.type === "group" && children.length > 0 && children.every((child) => child.type === "three");
  const threeNode = isThreeAssembly ? {...node, type: "three" as const, children} : node;
  const content = (() => {
    if (isThreeAssembly) {
      return <ThreeNode node={threeNode} runtime={runtime} width={box.width} height={box.height} camera={program.camera} fallback={<ThreeFallback node={threeNode} runtime={runtime} box={box}/>}/>;
    }
    switch (node.type) {
      case "text": return <TextNode node={node} runtime={runtime}/>;
      case "rect": case "roundRect": case "ellipse": case "circle": case "line": case "path": return <SvgShape node={node} runtime={runtime} box={box}/>;
      case "chart": return <ChartNode node={node} runtime={runtime} box={box}/>;
      case "network": return <NetworkNode node={node} runtime={runtime} box={box}/>;
      case "timeline": return <TimelineNode node={node} runtime={runtime} box={box}/>;
      case "image": {
        const src = resolveAssetSrc(node.src, program);
        return src ? <Img src={src} alt={node.alt} style={{width: "100%", height: "100%", objectFit: node.style?.objectFit ?? "contain", objectPosition: node.style?.objectPosition}}/> : <div style={{display: "grid", placeItems: "center", width: "100%", height: "100%", color: "#777"}}>Image unavailable</div>;
      }
      case "media": {
        const src = resolveAssetSrc(node.media?.src, program);
        if (!src) return <div style={{display: "grid", placeItems: "center", width: "100%", height: "100%", color: "#777"}}>Media unavailable</div>;
        return node.media?.kind === "audio" ? <Audio src={src} volume={scalar(node.media.volume, runtime, 1)}/> : <Video src={src} muted={node.media?.muted} loop={node.media?.loop} playbackRate={scalar(node.media?.playbackRate, runtime, 1)} style={{width: "100%", height: "100%", objectFit: node.style?.objectFit ?? "contain"}}/>;
      }
      case "three": return <ThreeNode node={node} runtime={runtime} width={box.width} height={box.height} camera={program.camera} fallback={<ThreeFallback node={node} runtime={runtime} box={box}/>}/>;
      default: return null;
    }
  })();
  const renderChildren = isThreeAssembly || node.type === "three" ? [] : children;
  const childBoxes = layoutChildren(node, runtime, box);
  return <NodeBox node={node} box={box} runtime={runtime}>
    {content}
    {renderChildren.map((child, index) => <SceneNodeRenderer key={child.id} node={child} box={childBoxes[index] ?? box} runtime={runtime} program={program}/>)}
  </NodeBox>;
};

export type SceneRuntimeProps = {program: SceneProgram; frame?: number; showPreflight?: boolean};

export const SceneRuntime: React.FC<SceneRuntimeProps> = ({program, frame: frameOverride, showPreflight = true}) => {
  const remotionFrame = useCurrentFrame();
  const config = useVideoConfig();
  const frame = frameOverride ?? remotionFrame;
  const report = useMemo(() => preflightScene(program), [program]);
  const runtime = runtimeFor(frame, {fps: program.fps || config.fps, width: program.width || config.width, height: program.height || config.height, durationInFrames: program.durationInFrames || config.durationInFrames}, program.anchors);
  const rootBox: Box = {x: 0, y: 0, width: program.width, height: program.height, z: 0};
  const background = asColor(resolveScalar(program.background, runtime), "transparent");
  const cameraTransform = program.camera ? [`translate3d(${scalar(program.camera.x, runtime)}px, ${scalar(program.camera.y, runtime)}px, ${scalar(program.camera.z, runtime)}px)`, `scale(${scalar(program.camera.zoom, runtime, 1)})`, `rotate(${scalar(program.camera.rotate, runtime)}deg)`].join(" ") : undefined;
  if (!report.ok) return <AbsoluteFill style={{background: "#fff6f0", color: "#7c2d12", padding: 48, fontFamily: "Arial"}}><strong>Scene preflight failed</strong>{showPreflight && <ul>{report.issues.filter((item) => item.level === "error").map((item) => <li key={`${item.code}-${item.nodeId}`}>{item.message}</li>)}</ul>}</AbsoluteFill>;
  return <AbsoluteFill data-scene-program={program.id} style={{background, overflow: "hidden"}}><div style={{position: "absolute", inset: 0, transform: cameraTransform, transformOrigin: "center", perspective: program.camera?.perspective === undefined ? undefined : scalar(program.camera.perspective, runtime)}}><SceneNodeRenderer node={program.root} box={rootBox} runtime={runtime} program={program}/></div></AbsoluteFill>;
};

export const SceneStudioPreview: React.FC<SceneRuntimeProps> = (props) => <SceneRuntime {...props}/>;


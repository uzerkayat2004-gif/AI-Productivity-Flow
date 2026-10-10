import type {NodeType, SceneNode, ScenePreflightIssue, ScenePreflightReport, SceneProgram} from "./schema";

const nodeTypes = new Set<NodeType>([
  "group", "rect", "roundRect", "ellipse", "circle", "line", "path", "text", "image", "chart", "network", "timeline", "media", "three", "custom",
]);
const threePrimitives = new Set(["box", "sphere", "cylinder", "torus", "plane"]);

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value && typeof value === "object" && !Array.isArray(value));

const issue = (issues: ScenePreflightIssue[], level: ScenePreflightIssue["level"], code: string, message: string, nodeId?: string, path?: string) => {
  issues.push({level, code, message, nodeId, path});
};

const finite = (value: unknown) => typeof value === "number" && Number.isFinite(value);
const stringValue = (value: unknown) => typeof value === "string" && value.trim().length > 0;

export const preflightScene = (program: SceneProgram | unknown): ScenePreflightReport => {
  const issues: ScenePreflightIssue[] = [];
  if (!isRecord(program)) {
    issue(issues, "error", "program.invalid", "Scene program must be an object.");
    return {ok: false, issues, renderClass: "static", estimatedElementCount: 0, maxDepth: 0, anchors: []};
  }

  const raw = program as Partial<SceneProgram>;
  const renderClass = ["static", "motion-island", "continuous-2d", "webgl-3d", "media"].includes(String(raw.renderClass))
    ? raw.renderClass as ScenePreflightReport["renderClass"]
    : "static";
  const ids = new Set<string>();
  const anchorEntries = raw.anchors === undefined ? [] : Array.isArray(raw.anchors) ? raw.anchors : [];
  const anchors: string[] = [];
  if (raw.anchors !== undefined && !Array.isArray(raw.anchors)) issue(issues, "error", "anchors.invalid", "anchors must be an array.");
  for (const anchor of anchorEntries) {
    if (!isRecord(anchor) || !stringValue(anchor.id)) {
      issue(issues, "error", "anchors.id", "Every semantic anchor needs a stable id.");
      continue;
    }
    anchors.push(String(anchor.id));
  }
  const anchorSet = new Set(anchors);
  if (anchorSet.size !== anchors.length) issue(issues, "error", "anchors.duplicate", "Semantic anchor ids must be unique.");

  const assets = raw.assets === undefined ? [] : Array.isArray(raw.assets) ? raw.assets : [];
  const assetIds = new Set<string>();
  if (raw.assets !== undefined && !Array.isArray(raw.assets)) issue(issues, "error", "assets.invalid", "assets must be an array.");
  for (const asset of assets) {
    if (!isRecord(asset) || !stringValue(asset.id)) {
      issue(issues, "error", "asset.id", "Every asset needs a stable id.");
      continue;
    }
    const assetId = String(asset.id);
    if (assetIds.has(assetId)) issue(issues, "error", "asset.duplicate", `Duplicate asset id: ${assetId}.`);
    assetIds.add(assetId);
    if (!stringValue(asset.src)) issue(issues, "error", "asset.src", `Asset ${assetId} requires a non-empty src.`);
    if (!stringValue(asset.kind)) issue(issues, "warning", "asset.kind", `Asset ${assetId} has no declared kind.`);
  }

  let elementCount = 0;
  let maxDepth = 0;
  let hasThree = false;
  let hasMedia = false;

  if (!stringValue(raw.id)) issue(issues, "error", "program.id", "Scene program requires a stable id.");
  if (!finite(raw.fps) || Number(raw.fps) <= 0 || Number(raw.fps) > 240) issue(issues, "error", "program.fps", "fps must be a finite value between 1 and 240.");
  if (!finite(raw.width) || Number(raw.width) <= 0) issue(issues, "error", "program.width", "width must be a positive number.");
  if (!finite(raw.height) || Number(raw.height) <= 0) issue(issues, "error", "program.height", "height must be a positive number.");
  if (!finite(raw.durationInFrames) || Number(raw.durationInFrames) < 1) issue(issues, "error", "program.duration", "durationInFrames must be at least one frame.");
  if (!isRecord(raw.root)) issue(issues, "error", "program.root", "Scene program requires a root node.");
  if (!["static", "motion-island", "continuous-2d", "webgl-3d", "media"].includes(String(raw.renderClass))) issue(issues, "error", "program.renderClass", `Unknown render class: ${String(raw.renderClass)}.`);

  const visit = (candidate: unknown, depth: number, parentPath: string) => {
    elementCount += 1;
    maxDepth = Math.max(maxDepth, depth);
    if (!isRecord(candidate)) {
      issue(issues, "error", "node.invalid", "Node must be an object.", undefined, `${parentPath}/?`);
      return;
    }
    const node = candidate as SceneNode;
    const nodeId = stringValue(node.id) ? String(node.id) : undefined;
    const path = `${parentPath}/${nodeId ?? "?"}`;
    if (!nodeId) issue(issues, "error", "node.id", "Every node needs a stable id.", undefined, path);
    else if (ids.has(nodeId)) issue(issues, "error", "node.duplicate", `Duplicate node id: ${nodeId}.`, nodeId, path);
    else ids.add(nodeId);
    if (!nodeTypes.has(node.type as NodeType)) issue(issues, "error", "node.type", `Unsupported node type: ${String(node.type)}.`, nodeId, path);

    if (node.type === "text") {
      if (!isRecord(node.text) || !stringValue(node.text.text)) issue(issues, "error", "text.content", "Text nodes require text.text.", nodeId, path);
      const fontSize = node.style?.fontSize;
      if (typeof fontSize === "number" && fontSize < 12) issue(issues, "warning", "text.size", "Text smaller than 12px is difficult to read in a video frame.", nodeId, path);
    }
    if (node.type === "image" && !stringValue(node.src)) issue(issues, "error", "image.src", "Image nodes require src or an asset reference.", nodeId, path);
    if (node.type === "path" && !stringValue(node.path?.d)) issue(issues, "error", "path.d", "Path nodes require an SVG path string.", nodeId, path);
    if (node.type === "chart" && (!isRecord(node.chart) || !Array.isArray(node.chart.data))) issue(issues, "error", "chart.data", "Chart nodes require chart.data.", nodeId, path);
    if (node.type === "network" && (!isRecord(node.network) || !Array.isArray(node.network.nodes) || !Array.isArray(node.network.edges))) issue(issues, "error", "network.data", "Network nodes require nodes and edges arrays.", nodeId, path);
    if (node.type === "timeline" && (!isRecord(node.timeline) || !Array.isArray(node.timeline.items))) issue(issues, "error", "timeline.data", "Timeline nodes require timeline.items.", nodeId, path);
    if (node.type === "media") {
      hasMedia = true;
      if (!isRecord(node.media) || !stringValue(node.media.src)) issue(issues, "error", "media.src", "Media nodes require media.src.", nodeId, path);
      if (isRecord(node.media) && !["audio", "video"].includes(String(node.media.kind))) issue(issues, "error", "media.kind", "Media nodes require kind audio or video.", nodeId, path);
    }
    if (node.type === "three") {
      hasThree = true;
      if (!isRecord(node.three)) issue(issues, "warning", "three.spec", "Three node has no primitive spec; deterministic box fallback will be used.", nodeId, path);
      const primitive = node.three?.primitive;
      if (primitive !== undefined && !threePrimitives.has(String(primitive))) issue(issues, "warning", "three.primitive", `Unsupported Three primitive ${String(primitive)}; deterministic box geometry will be used.`, nodeId, path);
      if (node.three?.assetKey && !assetIds.has(String(node.three.assetKey))) issue(issues, "warning", "three.asset", `Three asset ${String(node.three.assetKey)} is not present in the asset manifest; fallback geometry will be used.`, nodeId, path);
      if (node.three?.flowPaths !== undefined && !Array.isArray(node.three.flowPaths)) issue(issues, "warning", "three.flowPaths", "Three flowPaths must be an array; malformed connectors will be ignored.", nodeId, path);
    }
    for (const anchor of Array.isArray(node.anchors) ? node.anchors : []) {
      if (!anchorSet.has(String(anchor))) issue(issues, "warning", "anchor.missing", `Node references unknown semantic anchor ${String(anchor)}.`, nodeId, path);
    }
    if (node.motion?.keyframes) {
      for (const property of Object.keys(node.motion.keyframes)) if (property.includes("transition") || property.includes("animation")) issue(issues, "error", "motion.css", "CSS transitions and animations are not allowed; use frame expressions.", nodeId, path);
    }
    if (node.children !== undefined && !Array.isArray(node.children)) {
      issue(issues, "error", "node.children", "Node children must be an array.", nodeId, path);
      return;
    }
    for (const child of Array.isArray(node.children) ? node.children : []) visit(child, depth + 1, path);
  };

  if (isRecord(raw.root)) visit(raw.root, 0, "root");
  if (elementCount > 2500) issue(issues, "warning", "budget.elements", `Scene contains ${elementCount} elements; consider splitting the scene or using a simpler representation.`);
  if (maxDepth > 30) issue(issues, "warning", "budget.depth", `Scene hierarchy depth is ${maxDepth}; deep nesting can make layout difficult to inspect.`);
  if (hasThree && renderClass !== "webgl-3d") issue(issues, "warning", "renderClass.three", "A three node is present but renderClass is not webgl-3d.");
  if (hasMedia && renderClass !== "media") issue(issues, "warning", "renderClass.media", "A media node is present but renderClass is not media.");
  if (hasThree && renderClass === "webgl-3d") issue(issues, "warning", "webgl.optional", "WebGL is optional at runtime; a deterministic 2D fallback will be rendered when Three.js is unavailable.");

  return {
    ok: !issues.some((entry) => entry.level === "error"),
    issues,
    renderClass,
    estimatedElementCount: elementCount,
    maxDepth,
    anchors,
  };
};

export const assertSceneProgram = (program: SceneProgram | unknown) => {
  const report = preflightScene(program);
  if (!report.ok) throw new Error(`Scene preflight failed: ${report.issues.filter((item) => item.level === "error").map((item) => item.message).join(" ")}`);
  return report;
};

export const inferRenderClass = (program: Pick<SceneProgram, "root" | "renderClass"> | unknown): ScenePreflightReport["renderClass"] => {
  let foundMedia = false;
  let foundThree = false;
  let hasMotion = false;
  const visit = (candidate: unknown) => {
    if (!isRecord(candidate)) return;
    const node = candidate as SceneNode;
    foundMedia ||= node.type === "media";
    foundThree ||= node.type === "three";
    hasMotion ||= Boolean(node.motion);
    for (const child of Array.isArray(node.children) ? node.children : []) visit(child);
  };
  if (isRecord(program)) visit(program.root);
  if (foundThree) return "webgl-3d";
  if (foundMedia) return "media";
  if (hasMotion) return "continuous-2d";
  return isRecord(program) && typeof program.renderClass === "string" ? program.renderClass as ScenePreflightReport["renderClass"] : "static";
};


/**
 * 3D Procedural Visual Compiler & Scene Graph Host for Video Flow V3.
 *
 * Implements:
 * 1. Procedural 3D scene graphs for all 9 canonical 3D representation types:
 *    ASSEMBLY, EXPLODED_ASSEMBLY, CUTAWAY, COMPONENT, LAYER_STACK_3D,
 *    FLOW_PATH, TRAJECTORY, MECHANISM, and SPATIAL_SYSTEM.
 * 2. Camera Shot Grammar controllers:
 *    - HeroFocus: Centered isometric focus with smooth depth
 *    - Inspect: Orbiting continuous arc around target
 *    - ExplodedAssembly: Dolly out with isometric tilt during disassembly
 *    - Overview: Wide top-down architectural perspective
 *    - Traverse: Spline camera motion through volumetric pipes
 * 3. Studio Lighting Rigs & PBR material wiring from ArtDirectionGenome.
 * 4. Performance Budgets: <=150 draw calls, <=250k triangles.
 * 5. Absolute-time deterministic evaluation: state = Scene(t).
 */

import * as THREE from "three";
import {
  ExecutableNode3D,
  ExecutableSceneProgram,
  Canonical3DRepresentationType,
} from "../contracts/video-program";
import {
  geometryCompiler3D,
  GeometryCompiler3D,
  Procedural3DResult,
  ArtDirectionGenomeLike,
  safeColor,
  easeInOutCubic,
  computePerformanceMetrics,
  PerformanceBudgetReport,
} from "./geometry";

export * from "./geometry";

export enum CameraShotGrammarType {
  HERO_FOCUS = "HeroFocus",
  INSPECT = "Inspect",
  EXPLODED_ASSEMBLY = "ExplodedAssembly",
  OVERVIEW = "Overview",
  TRAVERSE = "Traverse",
}

export interface EvaluatedNode3D {
  node_id: string;
  procedural_type: string;
  position: [number, number, number];
  rotation: [number, number, number];
  scale: [number, number, number];
  material: Record<string, any>;
}

export interface Scene3DLights {
  ambient: THREE.AmbientLight;
  key: THREE.DirectionalLight;
  fill: THREE.DirectionalLight;
  rim: THREE.DirectionalLight;
  accentPoint?: THREE.PointLight;
}

export interface CameraGrammarController {
  update: (camera: THREE.PerspectiveCamera, tSec: number, durationSec: number) => void;
  getTraverseSpline?: () => THREE.CatmullRomCurve3 | null;
}

export interface Scene3DContext {
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  group: THREE.Group;
  lights: Scene3DLights;
  controllers: {
    cameraController: CameraGrammarController;
    nodeUpdaters: Array<(tSec: number, durationSec: number, motionPurpose?: string) => void>;
  };
  compiledResults: Procedural3DResult[];
  dispose: () => void;
  getPerformanceReport: () => PerformanceBudgetReport;
}

// ----------------------------------------------------------------------------
// Studio Lighting Rig Factory
// ----------------------------------------------------------------------------

export function createLightingRig(
  genome?: ArtDirectionGenomeLike
): { lights: Scene3DLights; group: THREE.Group } {
  const lightGroup = new THREE.Group();
  lightGroup.name = "LightingRig";

  const rigSpec = genome?.lighting_rig as any;
  const rigName = typeof rigSpec === "string" ? rigSpec : (rigSpec?.name || "Technical High Key");
  const palette = (genome?.palette || {}) as any;

  let keyIntensity = 1.25;
  let keyColorHex = "#FFFFFF";
  let fillIntensity = 0.45;
  let fillColorHex = palette.secondary_info || palette.secondary || "#B0C4DE";
  let ambientIntensity = 0.35;
  let ambientColorHex = palette.environment || palette.background || "#1E293B";
  let rimIntensity = 0.65;
  let rimColorHex = "#FFFFFF";
  let accentPointIntensity = 0.8;
  const shadowsEnabled = true;

  if (typeof rigSpec === "object" && rigSpec !== null) {
    keyIntensity = rigSpec.key_light_intensity ?? keyIntensity;
    keyColorHex = rigSpec.key_light_color ?? keyColorHex;
    fillIntensity = rigSpec.fill_light_intensity ?? fillIntensity;
    fillColorHex = rigSpec.fill_light_color ?? fillColorHex;
    ambientIntensity = rigSpec.ambient_light_intensity ?? ambientIntensity;
    ambientColorHex = rigSpec.ambient_light_color ?? ambientColorHex;
    rimIntensity = rigSpec.rim_light_intensity ?? rimIntensity;
    rimColorHex = rigSpec.rim_light_color ?? rimColorHex;
    accentPointIntensity = rigSpec.accent_point_intensity ?? accentPointIntensity;
  } else if (typeof rigName === "string") {
    const nameLower = rigName.toLowerCase();
    if (nameLower.includes("high key") || nameLower.includes("pure") || nameLower.includes("technical")) {
      keyIntensity = 1.35;
      fillIntensity = 0.65;
      ambientIntensity = 0.5;
      rimIntensity = 0.7;
    } else if (nameLower.includes("warm") || nameLower.includes("documentary") || nameLower.includes("editorial")) {
      keyIntensity = 1.2;
      keyColorHex = "#FFF5E6";
      fillIntensity = 0.4;
      fillColorHex = "#EAD5B8";
      ambientIntensity = 0.28;
      rimIntensity = 0.8;
      rimColorHex = "#FFE4B5";
    } else if (nameLower.includes("cyber") || nameLower.includes("neon")) {
      keyIntensity = 1.1;
      keyColorHex = "#E0F2FE";
      fillIntensity = 0.5;
      fillColorHex = "#A855F7";
      ambientIntensity = 0.3;
      ambientColorHex = "#050811";
      rimIntensity = 1.2;
      rimColorHex = "#00FFD5";
      accentPointIntensity = 1.2;
    } else if (nameLower.includes("industrial") || nameLower.includes("minimal")) {
      keyIntensity = 1.4;
      fillIntensity = 0.35;
      ambientIntensity = 0.3;
      rimIntensity = 0.55;
    }
  }

  const keyColor = safeColor(keyColorHex, "#FFFFFF");
  const fillColor = safeColor(fillColorHex, "#B0C4DE");
  const ambColor = safeColor(ambientColorHex, "#1E293B").lerp(new THREE.Color("#FFFFFF"), 0.3);
  const rimColor = safeColor(rimColorHex, "#FFFFFF");
  const accentColHex = palette.accent || "#00E5FF";
  const accentColor = safeColor(accentColHex, "#00E5FF");

  const ambient = new THREE.AmbientLight(ambColor, ambientIntensity);
  lightGroup.add(ambient);

  const key = new THREE.DirectionalLight(keyColor, keyIntensity);
  key.position.set(5.5, 8.5, 6.5);
  key.castShadow = shadowsEnabled;
  key.shadow.mapSize.width = 1024;
  key.shadow.mapSize.height = 1024;
  key.shadow.camera.near = 0.5;
  key.shadow.camera.far = 30;
  key.shadow.camera.left = -7;
  key.shadow.camera.right = 7;
  key.shadow.camera.top = 7;
  key.shadow.camera.bottom = -7;
  key.shadow.bias = -0.0005;
  lightGroup.add(key);

  const fill = new THREE.DirectionalLight(fillColor, fillIntensity);
  fill.position.set(-6.5, 3.5, -4.5);
  lightGroup.add(fill);

  const rim = new THREE.DirectionalLight(rimColor, rimIntensity);
  rim.position.set(0, 6.0, -8.0);
  lightGroup.add(rim);

  const accentPoint = new THREE.PointLight(accentColor, accentPointIntensity, 14, 1.5);
  accentPoint.position.set(0, 1.8, 0);
  lightGroup.add(accentPoint);

  return {
    lights: { ambient, key, fill, rim, accentPoint },
    group: lightGroup,
  };
}

// ----------------------------------------------------------------------------
// Camera Shot Grammar Controllers
// ----------------------------------------------------------------------------

/**
 * 1. HeroFocus: Centered isometric focus with smooth depth & cinematic push-in.
 */
export function createHeroFocusController(
  targetCenter: THREE.Vector3 = new THREE.Vector3(0, 0, 0)
): CameraGrammarController {
  return {
    update: (camera, tSec, durationSec) => {
      const dur = Math.max(0.1, durationSec || 5.0);
      const progress = Math.max(0, Math.min(1, tSec / dur));

      // Subtle cinematic dolly-in
      const dollyFactor = 1.0 - 0.09 * easeInOutCubic(progress);
      const baseDistance = 6.8 * dollyFactor;

      // Smooth breathing pan
      const breatheX = 0.22 * Math.sin(tSec * 0.45);
      const breatheY = 0.12 * Math.cos(tSec * 0.55);

      camera.position.set(
        targetCenter.x + breatheX + 0.6,
        targetCenter.y + 1.6 + breatheY,
        targetCenter.z + baseDistance
      );
      camera.lookAt(targetCenter.x, targetCenter.y, targetCenter.z);
    },
  };
}

/**
 * 2. Inspect: Orbiting continuous arc around target.
 */
export function createInspectController(
  targetCenter: THREE.Vector3 = new THREE.Vector3(0, 0, 0)
): CameraGrammarController {
  return {
    update: (camera, tSec, _durationSec) => {
      const radius = 7.2;
      const orbitSpeed = 0.32;
      const angle = tSec * orbitSpeed + Math.PI / 4;
      const elevation = 2.4 + 0.35 * Math.sin(tSec * 0.7);

      camera.position.set(
        targetCenter.x + Math.sin(angle) * radius,
        targetCenter.y + elevation,
        targetCenter.z + Math.cos(angle) * radius
      );
      camera.lookAt(targetCenter.x, targetCenter.y + 0.2, targetCenter.z);
    },
  };
}

/**
 * 3. ExplodedAssembly: Dolly out with isometric tilt during disassembly.
 */
export function createExplodedAssemblyController(
  targetCenter: THREE.Vector3 = new THREE.Vector3(0, 0, 0)
): CameraGrammarController {
  return {
    update: (camera, tSec, durationSec) => {
      const dur = Math.max(0.1, durationSec || 5.0);
      const progress = Math.max(0, Math.min(1, tSec / dur));
      const explodeFactor = easeInOutCubic(Math.min(1, Math.max(0, (progress - 0.12) / 0.58)));

      // Isometric 35.264 deg elevation (atan(1/sqrt(2))), 45 deg azimuth
      const baseDist = 6.8;
      const expandedDist = 10.8;
      const dist = baseDist + (expandedDist - baseDist) * explodeFactor;

      const pitch = Math.atan(1 / Math.SQRT2);
      const yaw = Math.PI / 4;

      const x = targetCenter.x + dist * Math.cos(yaw) * Math.cos(pitch);
      const y = targetCenter.y + dist * Math.sin(pitch) + explodeFactor * 0.4;
      const z = targetCenter.z + dist * Math.sin(yaw) * Math.cos(pitch);

      camera.position.set(x, y, z);
      camera.lookAt(targetCenter.x, targetCenter.y + 0.35 * explodeFactor, targetCenter.z);
    },
  };
}

/**
 * 4. Overview: Wide top-down architectural perspective with gentle lateral scanning.
 */
export function createOverviewController(
  targetCenter: THREE.Vector3 = new THREE.Vector3(0, 0, 0)
): CameraGrammarController {
  return {
    update: (camera, tSec, durationSec) => {
      const dur = Math.max(0.1, durationSec || 5.0);
      const progress = Math.max(0, Math.min(1, tSec / dur));

      const dist = 9.2;
      const pitch = 0.95; // ~54.4 deg top-down angle
      const yaw = 0.55; // ~31.5 deg

      const scanOffset = (progress - 0.5) * 1.8;

      const x = targetCenter.x + dist * Math.cos(yaw) * Math.cos(pitch) + scanOffset;
      const y = targetCenter.y + dist * Math.sin(pitch);
      const z = targetCenter.z + dist * Math.sin(yaw) * Math.cos(pitch) + scanOffset * 0.4;

      camera.position.set(x, y, z);
      camera.lookAt(targetCenter.x + scanOffset * 0.7, targetCenter.y - 0.2, targetCenter.z);
    },
  };
}

/**
 * 5. Traverse: Spline camera motion through volumetric pipes and spatial scenes.
 */
export function createTraverseController(
  customSpline?: THREE.CatmullRomCurve3,
  targetCenter: THREE.Vector3 = new THREE.Vector3(0, 0, 0)
): CameraGrammarController {
  const curve =
    customSpline ||
    new THREE.CatmullRomCurve3(
      [
        new THREE.Vector3(-4.5, 0.2, 5.0),
        new THREE.Vector3(-2.2, 1.2, 2.5),
        new THREE.Vector3(0.0, 0.8, 0.5),
        new THREE.Vector3(2.2, 1.4, -1.5),
        new THREE.Vector3(4.2, 0.4, -3.8),
      ],
      false,
      "catmullrom",
      0.5
    );

  return {
    update: (camera, tSec, durationSec) => {
      const dur = Math.max(0.1, durationSec || 5.0);
      const rawProgress = Math.max(0, Math.min(1, tSec / dur));
      const u = easeInOutCubic(rawProgress);

      const eyePt = curve.getPointAt(u);
      const lookPt = curve.getPointAt(Math.min(1.0, u + 0.08));

      camera.position.copy(eyePt).add(targetCenter);
      camera.lookAt(lookPt.x + targetCenter.x, lookPt.y + targetCenter.y, lookPt.z + targetCenter.z);
    },
    getTraverseSpline: () => curve,
  };
}

/**
 * Factory dispatcher for Camera Shot Grammar controllers.
 */
export function createCameraController(
  shotGrammar: string = CameraShotGrammarType.HERO_FOCUS,
  targetCenter: THREE.Vector3 = new THREE.Vector3(0, 0, 0),
  customSpline?: THREE.CatmullRomCurve3
): CameraGrammarController {
  const grammar = (shotGrammar || CameraShotGrammarType.HERO_FOCUS).toLowerCase();

  if (grammar.includes("traverse") || grammar.includes("flythrough") || grammar.includes("pipe")) {
    return createTraverseController(customSpline, targetCenter);
  }
  if (grammar.includes("inspect") || grammar.includes("orbit")) {
    return createInspectController(targetCenter);
  }
  if (grammar.includes("exploded") || grammar.includes("explosion") || grammar.includes("axonometric")) {
    return createExplodedAssemblyController(targetCenter);
  }
  if (grammar.includes("overview") || grammar.includes("isometric") || grammar.includes("topdown") || grammar.includes("planar")) {
    return createOverviewController(targetCenter);
  }

  return createHeroFocusController(targetCenter);
}

// ----------------------------------------------------------------------------
// Scene Lifecycle Functions
// ----------------------------------------------------------------------------

/**
 * Creates and initializes a production Three.js scene, camera, lights, and procedural geometry graph.
 */
export function create3DScene(
  scene: ExecutableSceneProgram,
  genome?: ArtDirectionGenomeLike,
  width: number = 1920,
  height: number = 1080
): Scene3DContext {
  const threeScene = new THREE.Scene();

  const palette: Record<string, any> = genome?.palette || {};
  const bgHex = palette.environment || palette.background || "#080D1A";
  threeScene.background = safeColor(bgHex, "#080D1A");

  const aspect = width / Math.max(1, height);
  const fov = 42;
  const camera = new THREE.PerspectiveCamera(fov, aspect, 0.1, 1000);
  camera.position.set(0, 2, 7);

  // Setup Lighting Rig
  const { lights, group: lightGroup } = createLightingRig(genome);
  threeScene.add(lightGroup);

  // Root Object Group
  const rootGroup = new THREE.Group();
  rootGroup.name = "Scene3DRoot";
  threeScene.add(rootGroup);

  const compiledResults: Procedural3DResult[] = [];
  const nodeUpdaters: Array<(tSec: number, durationSec: number, motionPurpose?: string) => void> = [];

  // Determine active nodes
  let nodes = scene.nodes_3d || [];

  if (nodes.length === 0) {
    const repType = String(scene.representation_type || Canonical3DRepresentationType.ASSEMBLY).toUpperCase();
    let procType = Canonical3DRepresentationType.ASSEMBLY;

    if (repType.includes("EXPLODED") || repType === Canonical3DRepresentationType.EXPLODED_ASSEMBLY) {
      procType = Canonical3DRepresentationType.EXPLODED_ASSEMBLY;
    } else if (repType.includes("CUTAWAY") || repType === Canonical3DRepresentationType.CUTAWAY) {
      procType = Canonical3DRepresentationType.CUTAWAY;
    } else if (repType.includes("COMPONENT") || repType === Canonical3DRepresentationType.COMPONENT) {
      procType = Canonical3DRepresentationType.COMPONENT;
    } else if (repType.includes("LAYER_STACK") || repType.includes("LAYERSTACK") || repType === Canonical3DRepresentationType.LAYER_STACK_3D) {
      procType = Canonical3DRepresentationType.LAYER_STACK_3D;
    } else if (repType.includes("FLOW") || repType.includes("PIPE") || repType === Canonical3DRepresentationType.FLOW_PATH) {
      procType = Canonical3DRepresentationType.FLOW_PATH;
    } else if (repType.includes("TRAJECTORY") || repType.includes("ORBIT") || repType === Canonical3DRepresentationType.TRAJECTORY) {
      procType = Canonical3DRepresentationType.TRAJECTORY;
    } else if (repType.includes("MECHANISM") || repType.includes("GEAR") || repType === Canonical3DRepresentationType.MECHANISM) {
      procType = Canonical3DRepresentationType.MECHANISM;
    } else if (repType.includes("SPATIAL") || repType.includes("NETWORK") || repType === Canonical3DRepresentationType.SPATIAL_SYSTEM) {
      procType = Canonical3DRepresentationType.SPATIAL_SYSTEM;
    }

    nodes = [
      {
        node_id: `default_${procType.toLowerCase()}`,
        procedural_type: procType,
        transform: {
          position: [0, 0, 0] as [number, number, number],
          rotation: [0, 0, 0] as [number, number, number],
          scale: [1, 1, 1] as [number, number, number],
        },
        material_spec: {},
        animation_keyframes: [],
      },
    ];
  }

  // Compile all 3D nodes
  nodes.forEach((node) => {
    const result = geometryCompiler3D.compileProceduralNode(node, genome);
    rootGroup.add(result.group);
    compiledResults.push(result);
    nodeUpdaters.push((tSec, durationSec, motionPurpose) => {
      result.update(tSec, durationSec, motionPurpose);
    });
  });

  const targetCenter = new THREE.Vector3(0, 0, 0);

  // Camera Controller
  const shotGrammar =
    (scene as any).shot_grammar ||
    (scene.representation_type === Canonical3DRepresentationType.FLOW_PATH ? CameraShotGrammarType.TRAVERSE : null) ||
    genome?.camera_grammar ||
    CameraShotGrammarType.HERO_FOCUS;

  const cameraController = createCameraController(shotGrammar, targetCenter);

  // Initial update at t = 0
  cameraController.update(camera, 0, scene.duration_sec || 5.0);

  const dispose = () => {
    compiledResults.forEach((res) => res.dispose());
    threeScene.remove(rootGroup);
    threeScene.remove(lightGroup);
  };

  const getPerformanceReport = (): PerformanceBudgetReport => {
    return computePerformanceMetrics(rootGroup);
  };

  return {
    scene: threeScene,
    camera,
    group: rootGroup,
    lights,
    controllers: {
      cameraController,
      nodeUpdaters,
    },
    compiledResults,
    dispose,
    getPerformanceReport,
  };
}

/**
 * Updates a 3D scene at absolute time t (seconds) deterministically.
 */
export function update3DSceneAt(
  sceneContext: Scene3DContext,
  scene: ExecutableSceneProgram,
  tSec: number,
  width?: number,
  height?: number
): void {
  const durationSec = scene.duration_sec || 5.0;
  const motionPurpose = (scene as any).motion_purpose || "reveal";

  if (width && height && height > 0) {
    const aspect = width / height;
    if (Math.abs(sceneContext.camera.aspect - aspect) > 0.001) {
      sceneContext.camera.aspect = aspect;
      sceneContext.camera.updateProjectionMatrix();
    }
  }

  sceneContext.controllers.cameraController.update(sceneContext.camera, tSec, durationSec);

  sceneContext.controllers.nodeUpdaters.forEach((updater) => {
    updater(tSec, durationSec, motionPurpose);
  });
}

/**
 * Helper to inspect performance budget adherence.
 */
export function getScenePerformanceBudget(sceneContext: Scene3DContext): PerformanceBudgetReport {
  return sceneContext.getPerformanceReport();
}

// ----------------------------------------------------------------------------
// VisualCompiler3D Class (for backwards-compatibility & high-level queries)
// ----------------------------------------------------------------------------

export class VisualCompiler3D {
  /**
   * Deterministically evaluate 3D procedural nodes at absolute time t (seconds).
   */
  public evaluateAt(scene: ExecutableSceneProgram, tSec: number): EvaluatedNode3D[] {
    const progress = Math.max(0, Math.min(1, tSec / (scene.duration_sec || 1.0)));

    return (scene.nodes_3d || []).map((node) => {
      const transform = node.transform || { position: [0, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1] };
      const pos: [number, number, number] = [...transform.position];

      if (
        node.procedural_type === "ExplodedAssembly" ||
        node.procedural_type === Canonical3DRepresentationType.EXPLODED_ASSEMBLY
      ) {
        if (progress > 0.15) {
          const explodeFactor = Math.sin((progress - 0.15) * Math.PI);
          pos[0] += explodeFactor * 1.5;
          pos[1] += explodeFactor * 0.8;
        }
      }

      return {
        node_id: node.node_id,
        procedural_type: node.procedural_type,
        position: pos,
        rotation: transform.rotation,
        scale: transform.scale,
        material: node.material_spec || {},
      };
    });
  }
}

export const compiler3D = new VisualCompiler3D();

/**
 * 3D Procedural Visual Compiler & Scene Graph Host for Video Flow V3.
 * Procedural Three.js scene compilation for Assemblies, Components, VolumetricPipes, LayerStacks, and Cutaways.
 * Wires ArtDirectionGenome materials and lighting rigs with shot grammar camera controllers.
 * Enforces absolute-time property evaluation: state = Scene(t).
 */

import * as THREE from "three";
import { ExecutableNode3D, ExecutableSceneProgram } from "../contracts/video-program";
import {
  geometryCompiler3D,
  GeometryCompiler3D,
  Procedural3DResult,
  ArtDirectionGenomeLike,
  safeColor,
  easeInOutCubic,
} from "./geometry";

export * from "./geometry";

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
}

// ----------------------------------------------------------------------------
// Lighting Rig Factory
// ----------------------------------------------------------------------------

export function createLightingRig(
  genome?: ArtDirectionGenomeLike
): { lights: Scene3DLights; group: THREE.Group } {
  const lightGroup = new THREE.Group();
  lightGroup.name = "LightingRig";

  const rigSpec = genome?.lighting_rig as any;
  const rigName = typeof rigSpec === "string" ? rigSpec : (rigSpec?.name || "Technical Studio Key");
  const palette = (genome?.palette || {}) as any;

  let keyIntensity = 1.2;
  let keyColorHex = "#FFFFFF";
  let fillIntensity = 0.45;
  let ambientIntensity = 0.35;
  let rimIntensity = 0.6;
  const shadowsEnabled = true;

  if (typeof rigSpec === "object" && rigSpec !== null) {
    keyIntensity = rigSpec.key_light_intensity ?? keyIntensity;
    keyColorHex = rigSpec.key_light_color ?? keyColorHex;
    fillIntensity = rigSpec.fill_light_intensity ?? fillIntensity;
    ambientIntensity = rigSpec.ambient_light_intensity ?? ambientIntensity;
    rimIntensity = rigSpec.rim_light_intensity ?? rimIntensity;
  } else if (typeof rigName === "string") {
    const nameLower = rigName.toLowerCase();
    if (nameLower.includes("high key") || nameLower.includes("pure")) {
      keyIntensity = 1.3;
      fillIntensity = 0.7;
      ambientIntensity = 0.55;
    } else if (nameLower.includes("warm") || nameLower.includes("documentary")) {
      keyIntensity = 1.2;
      keyColorHex = "#FFF6EA";
      fillIntensity = 0.35;
      ambientIntensity = 0.25;
    } else if (nameLower.includes("sunlight")) {
      keyIntensity = 1.5;
      fillIntensity = 0.3;
      ambientIntensity = 0.25;
      rimIntensity = 0.8;
    }
  }

  const keyColor = safeColor(keyColorHex, "#FFFFFF");
  const fillColHex = palette.secondary_info || palette.secondary || "#B0C4DE";
  const fillColor = safeColor(fillColHex, "#B0C4DE");
  const ambColHex = palette.environment || palette.background || "#1E293B";
  const ambColor = safeColor(ambColHex, "#1E293B").lerp(new THREE.Color("#FFFFFF"), 0.35);
  const accentColHex = palette.accent || "#E56B00";
  const accentColor = safeColor(accentColHex, "#E56B00");

  const ambient = new THREE.AmbientLight(ambColor, ambientIntensity);
  lightGroup.add(ambient);

  const key = new THREE.DirectionalLight(keyColor, keyIntensity);
  key.position.set(5.5, 8.5, 6.5);
  key.castShadow = shadowsEnabled;
  key.shadow.mapSize.width = 1024;
  key.shadow.mapSize.height = 1024;
  key.shadow.camera.near = 0.5;
  key.shadow.camera.far = 30;
  key.shadow.camera.left = -6;
  key.shadow.camera.right = 6;
  key.shadow.camera.top = 6;
  key.shadow.camera.bottom = -6;
  key.shadow.bias = -0.0005;
  lightGroup.add(key);

  const fill = new THREE.DirectionalLight(fillColor, fillIntensity);
  fill.position.set(-6.5, 3.5, -4.5);
  lightGroup.add(fill);

  const rim = new THREE.DirectionalLight(keyColor, rimIntensity);
  rim.position.set(0, 6.0, -8.0);
  lightGroup.add(rim);

  const accentPoint = new THREE.PointLight(accentColor, 0.8, 14, 1.5);
  accentPoint.position.set(0, 1.8, 0);
  lightGroup.add(accentPoint);

  return {
    lights: { ambient, key, fill, rim, accentPoint },
    group: lightGroup,
  };
}

// ----------------------------------------------------------------------------
// Camera Grammar Controllers
// ----------------------------------------------------------------------------

export function createCameraController(
  shotGrammar: string = "HeroFocus",
  targetCenter: THREE.Vector3 = new THREE.Vector3(0, 0, 0)
): CameraGrammarController {
  const grammar = (shotGrammar || "HeroFocus").toLowerCase();

  if (grammar.includes("inspect") || grammar.includes("orbit")) {
    return {
      update: (camera, tSec, _durationSec) => {
        const radius = 7.2;
        const orbitSpeed = 0.35;
        const angle = tSec * orbitSpeed + Math.PI / 4;
        const elevation = 2.4 + 0.35 * Math.sin(tSec * 0.7);

        camera.position.set(
          targetCenter.x + Math.sin(angle) * radius,
          targetCenter.y + elevation,
          targetCenter.z + Math.cos(angle) * radius
        );
        camera.lookAt(targetCenter);
      },
    };
  }

  if (grammar.includes("exploded") || grammar.includes("explosion") || grammar.includes("axonometric")) {
    return {
      update: (camera, tSec, durationSec) => {
        const dur = Math.max(0.1, durationSec || 5.0);
        const progress = Math.max(0, Math.min(1, tSec / dur));
        const explodeFactor = easeInOutCubic(Math.min(1, Math.max(0, (progress - 0.15) / 0.55)));

        // Isometric 35.264 deg elevation, 45 deg azimuth with dynamic dolly-out
        const baseDist = 7.0;
        const expandedDist = 10.2;
        const dist = baseDist + (expandedDist - baseDist) * explodeFactor;

        const pitch = Math.atan(1 / Math.SQRT2); // ~35.264 deg
        const yaw = Math.PI / 4; // 45 deg

        const x = targetCenter.x + dist * Math.cos(yaw) * Math.cos(pitch);
        const y = targetCenter.y + dist * Math.sin(pitch);
        const z = targetCenter.z + dist * Math.sin(yaw) * Math.cos(pitch);

        camera.position.set(x, y, z);
        camera.lookAt(targetCenter.x, targetCenter.y + 0.2 * explodeFactor, targetCenter.z);
      },
    };
  }

  if (grammar.includes("overview") || grammar.includes("isometric") || grammar.includes("planar")) {
    return {
      update: (camera, tSec, durationSec) => {
        const dur = Math.max(0.1, durationSec || 5.0);
        const progress = Math.max(0, Math.min(1, tSec / dur));

        const dist = 8.5;
        const pitch = 0.55; // ~31.5 deg
        const yaw = 0.65; // ~37 deg

        // Smooth lateral scan
        const scanOffset = (progress - 0.5) * 1.6;

        const x = targetCenter.x + dist * Math.cos(yaw) * Math.cos(pitch) + scanOffset;
        const y = targetCenter.y + dist * Math.sin(pitch);
        const z = targetCenter.z + dist * Math.sin(yaw) * Math.cos(pitch) + scanOffset * 0.5;

        camera.position.set(x, y, z);
        camera.lookAt(targetCenter.x + scanOffset * 0.8, targetCenter.y, targetCenter.z);
      },
    };
  }

  // Default: HeroFocus (Dynamic cinematic framing with subtle dolly-in)
  return {
    update: (camera, tSec, durationSec) => {
      const dur = Math.max(0.1, durationSec || 5.0);
      const progress = Math.max(0, Math.min(1, tSec / dur));

      // Subtle cinematic push-in
      const dollyIn = 1.0 - 0.08 * easeInOutCubic(progress);
      const baseDistance = 6.8 * dollyIn;

      // Subtle breathing pan
      const breatheX = 0.25 * Math.sin(tSec * 0.5);
      const breatheY = 0.12 * Math.cos(tSec * 0.6);

      camera.position.set(
        targetCenter.x + breatheX + 0.8,
        targetCenter.y + 1.8 + breatheY,
        targetCenter.z + baseDistance
      );
      camera.lookAt(targetCenter.x, targetCenter.y, targetCenter.z);
    },
  };
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
  const bgHex = palette.environment || palette.background || "#121417";
  threeScene.background = safeColor(bgHex, "#121417");

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

  // Compile all 3D nodes
  const nodes = Array.isArray(scene.nodes_3d) && scene.nodes_3d.length > 0
    ? scene.nodes_3d
    : [
        {
          node_id: "default_assembly",
          procedural_type: "Assembly",
          transform: {
            position: [0, 0, 0] as [number, number, number],
            rotation: [0, 0, 0] as [number, number, number],
            scale: [1, 1, 1] as [number, number, number],
          },
          material_spec: {},
          animation_keyframes: [],
        },
      ];

  nodes.forEach((node) => {
    const result = geometryCompiler3D.compileProceduralNode(node, genome);
    rootGroup.add(result.group);
    compiledResults.push(result);
    nodeUpdaters.push((tSec, durationSec, motionPurpose) => {
      result.update(tSec, durationSec, motionPurpose);
    });
  });

  // Target center calculation
  const targetCenter = new THREE.Vector3(0, 0, 0);

  // Camera Controller
  const shotGrammar = (scene as any).shot_grammar || genome?.camera_grammar || "HeroFocus";
  const cameraController = createCameraController(shotGrammar, targetCenter);

  // Initial update
  cameraController.update(camera, 0, scene.duration_sec || 5.0);

  const dispose = () => {
    compiledResults.forEach((res) => res.dispose());
    threeScene.remove(rootGroup);
    threeScene.remove(lightGroup);
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

  // Update aspect ratio if dimensions changed
  if (width && height && height > 0) {
    const aspect = width / height;
    if (Math.abs(sceneContext.camera.aspect - aspect) > 0.001) {
      sceneContext.camera.aspect = aspect;
      sceneContext.camera.updateProjectionMatrix();
    }
  }

  // Update camera grammar
  sceneContext.controllers.cameraController.update(sceneContext.camera, tSec, durationSec);

  // Update all procedural node animations
  sceneContext.controllers.nodeUpdaters.forEach((updater) => {
    updater(tSec, durationSec, motionPurpose);
  });
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

      // Exploded assembly procedural animation curves
      if (node.procedural_type === "ExplodedAssembly" && progress > 0.15) {
        const explodeFactor = Math.sin((progress - 0.15) * Math.PI);
        pos[0] += explodeFactor * 1.5;
        pos[1] += explodeFactor * 0.8;
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

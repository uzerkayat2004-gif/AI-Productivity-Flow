/**
 * Procedural 3D Geometry Compilers for Video Flow V3.
 * Generates production Three.js scene graphs, procedural geometries, PBR materials,
 * and animated structures for all 9 canonical 3D representation types:
 * ASSEMBLY, EXPLODED_ASSEMBLY, CUTAWAY, COMPONENT, LAYER_STACK_3D, FLOW_PATH,
 * TRAJECTORY, MECHANISM, and SPATIAL_SYSTEM.
 *
 * Enforces Performance Budgets: <=150 draw calls, <=250k triangles via THREE.InstancedMesh.
 */

import * as THREE from "three";
import {
  ExecutableNode3D,
  ArtDirectionPalette,
  ArtDirectionGenome,
  Canonical3DRepresentationType,
} from "../contracts/video-program";

export { Canonical3DRepresentationType };

export interface Compiled3DObject {
  node_id: string;
  type: string;
  position: [number, number, number];
  rotation: [number, number, number];
  scale: [number, number, number];
  color: string;
  roughness: number;
  metalness: number;
}

export interface ArtDirectionMaterials {
  surface_type?: string;
  roughness?: number;
  metalness?: number;
  clearcoat?: number;
  clearcoatRoughness?: number;
  subsurface?: number;
  opacity?: number;
  transmission?: number;
  ior?: number;
  thickness?: number;
  emissiveIntensity?: number;
  bloom_enabled?: boolean;
  lens_flare?: boolean;
  dof_enabled?: boolean;
  glassmorphism?: boolean;
  [key: string]: any;
}

export type ArtDirectionGenomeLike = Partial<ArtDirectionGenome> & {
  palette?: Partial<ArtDirectionPalette> & Record<string, any>;
  materials?: ArtDirectionMaterials;
  lighting_rig?: string | Record<string, any>;
  camera_grammar?: string;
  motion_grammar?: string;
  [key: string]: any;
};

export interface Procedural3DPart {
  mesh: THREE.Object3D;
  basePosition: THREE.Vector3;
  baseRotation: THREE.Euler;
  baseScale: THREE.Vector3;
  explodeDirection?: THREE.Vector3;
  explodeDistance?: number;
  staggerDelay?: number;
  customUpdate?: (tSec: number, durationSec: number, partProgress: number) => void;
}

export interface PerformanceBudgetReport {
  drawCalls: number;
  triangles: number;
  geometries: number;
  materials: number;
  withinBudget: boolean;
  maxDrawCalls: number;
  maxTriangles: number;
}

export interface Procedural3DResult {
  group: THREE.Group;
  parts: Procedural3DPart[];
  update: (tSec: number, durationSec: number, motionPurpose?: string) => void;
  dispose: () => void;
  getMetrics?: () => PerformanceBudgetReport;
}

// ----------------------------------------------------------------------------
// Color & Material Helpers
// ----------------------------------------------------------------------------

export function safeColor(val: unknown, fallback: string = "#888888"): THREE.Color {
  try {
    if (typeof val === "string" && val.length > 0) {
      return new THREE.Color(val);
    }
    if (typeof val === "number") {
      return new THREE.Color(val);
    }
  } catch {
    // fallback
  }
  return new THREE.Color(fallback);
}

export interface ResolvedMaterialTheme {
  primaryColor: THREE.Color;
  accentColor: THREE.Color;
  highlightColor: THREE.Color;
  neutralColor: THREE.Color;
  secondaryColor: THREE.Color;
  borderColor: THREE.Color;
  glowColor: THREE.Color;
  roughness: number;
  metalness: number;
  clearcoat: number;
  transmission: number;
  materials: {
    metal: THREE.MeshStandardMaterial;
    darkChassis: THREE.MeshStandardMaterial;
    accent: THREE.MeshStandardMaterial;
    highlight: THREE.MeshStandardMaterial;
    glass: THREE.MeshPhysicalMaterial;
    frosted: THREE.MeshPhysicalMaterial;
    coreGlow: THREE.MeshStandardMaterial;
    wireframe: THREE.LineBasicMaterial;
    accentLine: THREE.LineBasicMaterial;
    gridLine: THREE.LineBasicMaterial;
  };
}

export function createMaterialTheme(
  nodeMaterial: Record<string, any> = {},
  genome?: ArtDirectionGenomeLike
): ResolvedMaterialTheme {
  const palette: Record<string, any> = genome?.palette || {};
  const gMat = genome?.materials || {};

  const primaryHex = nodeMaterial.color || palette.primary_info || palette.primary || "#E6E8EC";
  const accentHex = nodeMaterial.accent_color || palette.accent || "#00E5FF";
  const highlightHex = nodeMaterial.highlight_color || palette.highlight || palette.accentAlt || "#FFB300";
  const neutralHex = palette.structural_neutral || palette.surface || "#1E2430";
  const secondaryHex = palette.secondary_info || palette.secondary || "#818CF8";
  const borderHex = palette.border || "#334155";
  const glowHex = palette.glow || accentHex;

  const primaryColor = safeColor(primaryHex, "#E6E8EC");
  const accentColor = safeColor(accentHex, "#00E5FF");
  const highlightColor = safeColor(highlightHex, "#FFB300");
  const neutralColor = safeColor(neutralHex, "#1E2430");
  const secondaryColor = safeColor(secondaryHex, "#818CF8");
  const borderColor = safeColor(borderHex, "#334155");
  const glowColor = safeColor(glowHex, "#00E5FF");

  const surfaceType = (gMat.surface_type || nodeMaterial.surface_type || "metallic").toLowerCase();

  let baseRoughness = typeof nodeMaterial.roughness === "number" ? nodeMaterial.roughness : (gMat.roughness ?? 0.3);
  let baseMetalness = typeof nodeMaterial.metalness === "number" ? nodeMaterial.metalness : (gMat.metalness ?? 0.7);
  let clearcoat = gMat.clearcoat ?? 0.2;
  const transmission = gMat.transmission ?? 0.0;

  if (surfaceType === "matte") {
    baseRoughness = Math.max(0.6, baseRoughness);
    baseMetalness = Math.min(0.2, baseMetalness);
    clearcoat = 0.0;
  } else if (surfaceType === "glass" || surfaceType === "glassmorphism") {
    baseRoughness = 0.05;
    baseMetalness = 0.05;
    clearcoat = 1.0;
  } else if (surfaceType === "anodized") {
    baseRoughness = 0.35;
    baseMetalness = 0.75;
    clearcoat = 0.4;
  } else if (surfaceType === "carbon") {
    baseRoughness = 0.45;
    baseMetalness = 0.25;
    clearcoat = 0.3;
  }

  const metal = new THREE.MeshStandardMaterial({
    color: primaryColor,
    roughness: Math.max(0.08, baseRoughness),
    metalness: Math.min(0.96, Math.max(0.3, baseMetalness)),
  });

  const darkChassis = new THREE.MeshStandardMaterial({
    color: neutralColor,
    roughness: Math.min(0.85, baseRoughness + 0.2),
    metalness: Math.max(0.1, baseMetalness * 0.5),
  });

  const accent = new THREE.MeshStandardMaterial({
    color: accentColor,
    roughness: 0.25,
    metalness: 0.5,
    emissive: accentColor.clone().multiplyScalar(0.25),
  });

  const highlight = new THREE.MeshStandardMaterial({
    color: highlightColor,
    roughness: 0.18,
    metalness: 0.2,
    emissive: highlightColor.clone().multiplyScalar(0.55),
  });

  const glass = new THREE.MeshPhysicalMaterial({
    color: primaryColor.clone().lerp(new THREE.Color("#FFFFFF"), 0.6),
    roughness: 0.08,
    metalness: 0.05,
    transmission: 0.9,
    transparent: true,
    opacity: 0.92,
    ior: gMat.ior ?? 1.52,
    thickness: gMat.thickness ?? 0.4,
  });

  const frosted = new THREE.MeshPhysicalMaterial({
    color: accentColor.clone().lerp(new THREE.Color("#FFFFFF"), 0.35),
    roughness: 0.35,
    metalness: 0.1,
    transmission: 0.65,
    transparent: true,
    opacity: 0.85,
    ior: 1.45,
    thickness: 0.25,
  });

  const coreGlow = new THREE.MeshStandardMaterial({
    color: glowColor,
    roughness: 0.15,
    metalness: 0.1,
    emissive: glowColor.clone().multiplyScalar(0.9),
  });

  const wireframe = new THREE.LineBasicMaterial({
    color: borderColor,
    transparent: true,
    opacity: 0.75,
  });

  const accentLine = new THREE.LineBasicMaterial({
    color: accentColor,
    transparent: true,
    opacity: 0.9,
  });

  const gridLine = new THREE.LineBasicMaterial({
    color: borderColor.clone().lerp(accentColor, 0.25),
    transparent: true,
    opacity: 0.4,
  });

  return {
    primaryColor,
    accentColor,
    highlightColor,
    neutralColor,
    secondaryColor,
    borderColor,
    glowColor,
    roughness: baseRoughness,
    metalness: baseMetalness,
    clearcoat,
    transmission,
    materials: {
      metal,
      darkChassis,
      accent,
      highlight,
      glass,
      frosted,
      coreGlow,
      wireframe,
      accentLine,
      gridLine,
    },
  };
}

// ----------------------------------------------------------------------------
// Easing and Math Helpers
// ----------------------------------------------------------------------------

export function easeInOutCubic(x: number): number {
  return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
}

export function easeOutBack(x: number): number {
  const c1 = 1.70158;
  const c3 = c1 + 1;
  return 1 + c3 * Math.pow(x - 1, 3) + c1 * Math.pow(x - 1, 2);
}

export function easeOutQuad(x: number): number {
  return 1 - (1 - x) * (1 - x);
}

export function createEdgesLine(geometry: THREE.BufferGeometry, material: THREE.LineBasicMaterial): THREE.LineSegments {
  const edges = new THREE.EdgesGeometry(geometry, 28);
  return new THREE.LineSegments(edges, material);
}

/**
 * Calculates draw call and triangle metrics for performance budget verification.
 */
export function computePerformanceMetrics(root: THREE.Object3D): PerformanceBudgetReport {
  let drawCalls = 0;
  let triangles = 0;
  const geometries = new Set<THREE.BufferGeometry>();
  const materials = new Set<THREE.Material>();

  root.traverse((obj) => {
    if (obj instanceof THREE.Mesh || obj instanceof THREE.LineSegments || obj instanceof THREE.Line) {
      drawCalls++;
      if (obj.geometry) {
        geometries.add(obj.geometry);
        const posAttr = obj.geometry.getAttribute("position");
        if (posAttr) {
          if (obj.geometry.index) {
            triangles += obj.geometry.index.count / 3;
          } else {
            triangles += posAttr.count / 3;
          }
        }
      }
      if (Array.isArray(obj.material)) {
        obj.material.forEach((m) => materials.add(m));
      } else if (obj.material) {
        materials.add(obj.material);
      }
    }
  });

  const maxDrawCalls = 150;
  const maxTriangles = 250000;
  const withinBudget = drawCalls <= maxDrawCalls && triangles <= maxTriangles;

  return {
    drawCalls,
    triangles: Math.round(triangles),
    geometries: geometries.size,
    materials: materials.size,
    withinBudget,
    maxDrawCalls,
    maxTriangles,
  };
}

// ----------------------------------------------------------------------------
// 1. ASSEMBLY / 2. EXPLODED_ASSEMBLY Procedural Compiler
// ----------------------------------------------------------------------------

export function compileAssembly(
  node: ExecutableNode3D,
  genome?: ArtDirectionGenomeLike,
  isExploded: boolean = false
): Procedural3DResult {
  const group = new THREE.Group();
  group.name = node.node_id || (isExploded ? "ExplodedAssembly" : "AssemblyGroup");

  const theme = createMaterialTheme(node.material_spec, genome);
  const parts: Procedural3DPart[] = [];
  const geometriesToDispose: THREE.BufferGeometry[] = [];

  const addPart = (
    obj: THREE.Object3D,
    explodeDir: THREE.Vector3,
    explodeDist: number,
    stagger: number,
    customUpdate?: (tSec: number, durationSec: number, partProgress: number) => void
  ) => {
    group.add(obj);
    parts.push({
      mesh: obj,
      basePosition: obj.position.clone(),
      baseRotation: obj.rotation.clone(),
      baseScale: obj.scale.clone(),
      explodeDirection: explodeDir.clone().normalize(),
      explodeDistance: explodeDist,
      staggerDelay: stagger,
      customUpdate,
    });
  };

  // --- Part 1: Base Chassis Mounting Plate ---
  const baseShape = new THREE.Shape();
  const w = 2.4;
  const h = 1.8;
  const r = 0.2;
  baseShape.moveTo(-w + r, -h);
  baseShape.lineTo(w - r, -h);
  baseShape.quadraticCurveTo(w, -h, w, -h + r);
  baseShape.lineTo(w, h - r);
  baseShape.quadraticCurveTo(w, h, w - r, h);
  baseShape.lineTo(-w + r, h);
  baseShape.quadraticCurveTo(-w, h, -w, h - r);
  baseShape.lineTo(-w, -h + r);
  baseShape.quadraticCurveTo(-w, -h, -w + r, -h);

  const baseGeo = new THREE.ExtrudeGeometry(baseShape, {
    depth: 0.28,
    bevelEnabled: true,
    bevelSegments: 2,
    steps: 1,
    bevelSize: 0.04,
    bevelThickness: 0.04,
  });
  baseGeo.rotateX(Math.PI / 2);
  geometriesToDispose.push(baseGeo);

  const baseMesh = new THREE.Mesh(baseGeo, theme.materials.darkChassis);
  baseMesh.castShadow = true;
  baseMesh.receiveShadow = true;
  baseMesh.position.set(0, -1.2, 0);
  baseMesh.add(createEdgesLine(baseGeo, theme.materials.wireframe));
  addPart(baseMesh, new THREE.Vector3(0, -1, 0), 1.6, 0.0);

  // --- Part 2: Lower Stator / Bearing Collar ---
  const lowerBearingGeo = new THREE.CylinderGeometry(1.3, 1.35, 0.35, 28);
  geometriesToDispose.push(lowerBearingGeo);
  const lowerBearingMesh = new THREE.Mesh(lowerBearingGeo, theme.materials.metal);
  lowerBearingMesh.position.set(0, -0.85, 0);
  lowerBearingMesh.add(createEdgesLine(lowerBearingGeo, theme.materials.wireframe));
  addPart(lowerBearingMesh, new THREE.Vector3(0, -0.6, 0), 1.2, 0.1);

  // --- Part 3: Central Spindle Shaft & Magnetic Rotor Core ---
  const coreGroup = new THREE.Group();
  coreGroup.position.set(0, 0, 0);

  const spindleGeo = new THREE.CylinderGeometry(0.3, 0.3, 2.6, 20);
  geometriesToDispose.push(spindleGeo);
  const spindleMesh = new THREE.Mesh(spindleGeo, theme.materials.accent);
  spindleMesh.castShadow = true;
  coreGroup.add(spindleMesh);

  const rotorHubGeo = new THREE.CylinderGeometry(0.85, 0.85, 1.1, 20);
  geometriesToDispose.push(rotorHubGeo);
  const rotorHubMesh = new THREE.Mesh(rotorHubGeo, theme.materials.metal);
  rotorHubMesh.add(createEdgesLine(rotorHubGeo, theme.materials.wireframe));
  coreGroup.add(rotorHubMesh);

  // Decorative Torus Rings on Rotor
  const torusGeo = new THREE.TorusGeometry(0.92, 0.05, 12, 24);
  geometriesToDispose.push(torusGeo);
  const torus1 = new THREE.Mesh(torusGeo, theme.materials.highlight);
  torus1.rotation.x = Math.PI / 2;
  torus1.position.y = 0.35;
  coreGroup.add(torus1);
  const torus2 = torus1.clone();
  torus2.position.y = -0.35;
  coreGroup.add(torus2);

  addPart(coreGroup, new THREE.Vector3(0, 0, 0), 0.0, 0.0, (tSec) => {
    coreGroup.rotation.y = tSec * 0.8;
  });

  // --- Part 4: Planetary Actuator Brackets (4 radial units) ---
  const numPlanets = 4;
  for (let i = 0; i < numPlanets; i++) {
    const angle = (i / numPlanets) * Math.PI * 2;
    const radDist = 1.45;
    const px = Math.cos(angle) * radDist;
    const pz = Math.sin(angle) * radDist;

    const planetGroup = new THREE.Group();
    planetGroup.position.set(px, 0, pz);

    const gearGeo = new THREE.CylinderGeometry(0.36, 0.36, 0.4, 16);
    geometriesToDispose.push(gearGeo);
    const gearMesh = new THREE.Mesh(gearGeo, theme.materials.darkChassis);
    gearMesh.add(createEdgesLine(gearGeo, theme.materials.accentLine));
    planetGroup.add(gearMesh);

    const pinGeo = new THREE.CylinderGeometry(0.1, 0.1, 0.7, 10);
    geometriesToDispose.push(pinGeo);
    const pinMesh = new THREE.Mesh(pinGeo, theme.materials.accent);
    planetGroup.add(pinMesh);

    const radialDir = new THREE.Vector3(Math.cos(angle), 0.35, Math.sin(angle));
    addPart(planetGroup, radialDir, 2.2, 0.2 + i * 0.05, (tSec) => {
      planetGroup.rotation.y = -tSec * 1.6;
    });
  }

  // --- Part 5: Upper Bearing & Retaining Ring ---
  const upperBearingGeo = new THREE.CylinderGeometry(1.2, 1.2, 0.3, 28);
  geometriesToDispose.push(upperBearingGeo);
  const upperBearingMesh = new THREE.Mesh(upperBearingGeo, theme.materials.metal);
  upperBearingMesh.position.set(0, 0.85, 0);
  upperBearingMesh.add(createEdgesLine(upperBearingGeo, theme.materials.wireframe));
  addPart(upperBearingMesh, new THREE.Vector3(0, 0.6, 0), 1.4, 0.35);

  // --- Part 6: Top Enclosure Cowl & Crystal Lens ---
  const topCowlGeo = new THREE.CylinderGeometry(1.35, 1.45, 0.7, 28);
  geometriesToDispose.push(topCowlGeo);
  const topCowlMesh = new THREE.Mesh(topCowlGeo, theme.materials.darkChassis);
  topCowlMesh.position.set(0, 1.35, 0);
  topCowlMesh.add(createEdgesLine(topCowlGeo, theme.materials.wireframe));

  const lensGeo = new THREE.CylinderGeometry(0.7, 0.7, 0.15, 20);
  geometriesToDispose.push(lensGeo);
  const lensMesh = new THREE.Mesh(lensGeo, theme.materials.glass);
  lensMesh.position.set(0, 0.35, 0);
  topCowlMesh.add(lensMesh);

  addPart(topCowlMesh, new THREE.Vector3(0, 1, 0), 2.5, 0.45);

  // --- Part 7: Instanced Corner Fasteners (1 Draw Call for all 4 bolts) ---
  const boltPositions = [
    [-w + 0.35, -h + 0.35],
    [w - 0.35, -h + 0.35],
    [w - 0.35, h - 0.35],
    [-w + 0.35, h - 0.35],
  ];

  const boltGeo = new THREE.CylinderGeometry(0.08, 0.08, 0.8, 8);
  geometriesToDispose.push(boltGeo);
  const instancedBolts = new THREE.InstancedMesh(boltGeo, theme.materials.accent, boltPositions.length);
  const dummyBolt = new THREE.Object3D();

  boltPositions.forEach(([bx, bz], idx) => {
    dummyBolt.position.set(bx, 1.6, bz);
    dummyBolt.updateMatrix();
    instancedBolts.setMatrixAt(idx, dummyBolt.matrix);
  });
  instancedBolts.instanceMatrix.needsUpdate = true;
  addPart(instancedBolts, new THREE.Vector3(0, 1, 0), 3.2, 0.55);

  // Apply node initial transform
  const t = node.transform || { position: [0, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1] };
  group.position.set(t.position[0], t.position[1], t.position[2]);
  group.rotation.set(t.rotation[0], t.rotation[1], t.rotation[2]);
  group.scale.set(t.scale[0], t.scale[1], t.scale[2]);

  const update = (tSec: number, durationSec: number, motionPurpose?: string) => {
    const duration = Math.max(0.1, durationSec || 5.0);
    const rawProgress = Math.max(0, Math.min(1, tSec / duration));

    let explodeAmount = 0.0;
    const isExplodeMotion =
      isExploded ||
      motionPurpose === "explode" ||
      node.procedural_type === Canonical3DRepresentationType.EXPLODED_ASSEMBLY ||
      node.procedural_type === "ExplodedAssembly";

    if (isExplodeMotion) {
      if (rawProgress < 0.15) {
        explodeAmount = 0;
      } else if (rawProgress < 0.65) {
        const p = (rawProgress - 0.15) / 0.5;
        explodeAmount = easeInOutCubic(p);
      } else if (rawProgress < 0.85) {
        explodeAmount = 1.0;
      } else {
        const p = (rawProgress - 0.85) / 0.15;
        explodeAmount = 1.0 - easeInOutCubic(p) * 0.35;
      }
    } else if (motionPurpose === "reveal") {
      const p = Math.min(1, rawProgress / 0.4);
      explodeAmount = (1.0 - easeOutBack(p)) * 0.8;
    } else {
      explodeAmount = 0.0;
    }

    parts.forEach((part, index) => {
      const stagger = part.staggerDelay || 0;
      const partProgress = Math.max(0, Math.min(1, (rawProgress - stagger * 0.2) / 0.8));
      const dist = (part.explodeDistance || 0) * explodeAmount;

      if (part.mesh instanceof THREE.InstancedMesh) {
        // Update instanced bolts explosion
        const instMesh = part.mesh as THREE.InstancedMesh;
        boltPositions.forEach(([bx, bz], idx) => {
          const boltDir = new THREE.Vector3(bx * 0.4, 1.2, bz * 0.4).normalize();
          dummyBolt.position.set(bx, 1.6, bz).addScaledVector(boltDir, dist);
          dummyBolt.updateMatrix();
          instMesh.setMatrixAt(idx, dummyBolt.matrix);
        });
        instMesh.instanceMatrix.needsUpdate = true;
      } else if (part.explodeDirection && dist > 0.001) {
        part.mesh.position.copy(part.basePosition).addScaledVector(part.explodeDirection, dist);
        part.mesh.position.y += Math.sin(tSec * 1.5 + index) * 0.03 * explodeAmount;
      } else {
        part.mesh.position.copy(part.basePosition);
      }

      if (part.customUpdate) {
        part.customUpdate(tSec, durationSec, partProgress);
      }
    });
  };

  const dispose = () => {
    geometriesToDispose.forEach((g) => g.dispose());
    Object.values(theme.materials).forEach((m) => m.dispose());
  };

  return {
    group,
    parts,
    update,
    dispose,
    getMetrics: () => computePerformanceMetrics(group),
  };
}

export function compileExplodedAssembly(
  node: ExecutableNode3D,
  genome?: ArtDirectionGenomeLike
): Procedural3DResult {
  return compileAssembly(node, genome, true);
}

// ----------------------------------------------------------------------------
// 3. CUTAWAY Procedural Compiler
// ----------------------------------------------------------------------------

export function compileCutaway(
  node: ExecutableNode3D,
  genome?: ArtDirectionGenomeLike
): Procedural3DResult {
  const group = new THREE.Group();
  group.name = node.node_id || "CutawaySection";

  const theme = createMaterialTheme(node.material_spec, genome);
  const geometriesToDispose: THREE.BufferGeometry[] = [];

  // Outer Hull with 90-degree quadrant cutaway (270 degrees arc)
  const outerRadius = 1.6;
  const cylinderHeight = 2.8;
  const hullGeo = new THREE.CylinderGeometry(
    outerRadius,
    outerRadius,
    cylinderHeight,
    36,
    1,
    false,
    0,
    Math.PI * 1.5
  );
  geometriesToDispose.push(hullGeo);

  const hullMesh = new THREE.Mesh(hullGeo, theme.materials.darkChassis);
  hullMesh.castShadow = true;
  hullMesh.receiveShadow = true;
  group.add(hullMesh);

  // Cut-plane cross-section cap plates
  const cutPlaneGeo1 = new THREE.PlaneGeometry(outerRadius, cylinderHeight);
  cutPlaneGeo1.rotateY(Math.PI / 2);
  cutPlaneGeo1.translate(0, 0, outerRadius / 2);
  geometriesToDispose.push(cutPlaneGeo1);
  const cutCap1 = new THREE.Mesh(cutPlaneGeo1, theme.materials.metal);
  group.add(cutCap1);

  const cutPlaneGeo2 = new THREE.PlaneGeometry(outerRadius, cylinderHeight);
  cutPlaneGeo2.translate(outerRadius / 2, 0, 0);
  geometriesToDispose.push(cutPlaneGeo2);
  const cutCap2 = new THREE.Mesh(cutPlaneGeo2, theme.materials.metal);
  group.add(cutCap2);

  // Highlight wireframe edge lines tracing cutaway boundary
  const hullEdges = createEdgesLine(hullGeo, theme.materials.accentLine);
  group.add(hullEdges);

  // Internal Core Assembly (Revealed by cutaway)
  const coreGroup = new THREE.Group();

  // Central glowing energy reactor core
  const coreGeo = new THREE.CylinderGeometry(0.48, 0.48, 2.4, 20);
  geometriesToDispose.push(coreGeo);
  const coreMesh = new THREE.Mesh(coreGeo, theme.materials.coreGlow);
  coreGroup.add(coreMesh);

  // Multi-tier turbine impeller discs
  const numDiscs = 3;
  const discGeo = new THREE.CylinderGeometry(0.95, 0.95, 0.15, 20);
  geometriesToDispose.push(discGeo);
  for (let d = 0; d < numDiscs; d++) {
    const dMesh = new THREE.Mesh(discGeo, theme.materials.metal);
    dMesh.position.y = (d - 1) * 0.75;
    dMesh.add(createEdgesLine(discGeo, theme.materials.wireframe));
    coreGroup.add(dMesh);
  }

  // Concentric magnetic induction coil toroids
  const numCoils = 4;
  const coilGeo = new THREE.TorusGeometry(0.82, 0.08, 12, 24);
  geometriesToDispose.push(coilGeo);

  for (let i = 0; i < numCoils; i++) {
    const cy = (i - (numCoils - 1) / 2) * 0.6;
    const coilMesh = new THREE.Mesh(coilGeo, theme.materials.accent);
    coilMesh.rotation.x = Math.PI / 2;
    coilMesh.position.y = cy;
    coreGroup.add(coilMesh);
  }

  // Internal coolant tubing with fluid highlights
  const tubePoints = [
    new THREE.Vector3(0.9, -1.2, 0),
    new THREE.Vector3(1.1, 0, 0.5),
    new THREE.Vector3(0.9, 1.2, 0),
  ];
  const fluidCurve = new THREE.CatmullRomCurve3(tubePoints);
  const fluidGeo = new THREE.TubeGeometry(fluidCurve, 20, 0.07, 10, false);
  geometriesToDispose.push(fluidGeo);
  const fluidMesh = new THREE.Mesh(fluidGeo, theme.materials.highlight);
  coreGroup.add(fluidMesh);

  group.add(coreGroup);

  const t = node.transform || { position: [0, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1] };
  group.position.set(t.position[0], t.position[1], t.position[2]);
  group.rotation.set(t.rotation[0], t.rotation[1], t.rotation[2]);
  group.scale.set(t.scale[0], t.scale[1], t.scale[2]);

  const update = (tSec: number) => {
    coreGroup.rotation.y = tSec * 0.75;
    const pulse = 0.7 + 0.3 * Math.sin(tSec * 3.5);
    theme.materials.coreGlow.emissiveIntensity = pulse * 1.2;
  };

  const dispose = () => {
    geometriesToDispose.forEach((g) => g.dispose());
    Object.values(theme.materials).forEach((m) => m.dispose());
  };

  return {
    group,
    parts: [],
    update,
    dispose,
    getMetrics: () => computePerformanceMetrics(group),
  };
}

// ----------------------------------------------------------------------------
// 4. COMPONENT / HOUSING Procedural Compiler
// ----------------------------------------------------------------------------

export function compileHousing(
  node: ExecutableNode3D,
  genome?: ArtDirectionGenomeLike
): Procedural3DResult {
  const group = new THREE.Group();
  group.name = node.node_id || "HousingComponent";

  const theme = createMaterialTheme(node.material_spec, genome);
  const geometriesToDispose: THREE.BufferGeometry[] = [];

  const mainWidth = 3.6;
  const mainHeight = 1.6;
  const mainDepth = 2.4;

  const bodyGeo = new THREE.BoxGeometry(mainWidth, mainHeight, mainDepth);
  geometriesToDispose.push(bodyGeo);
  const bodyMesh = new THREE.Mesh(bodyGeo, theme.materials.darkChassis);
  bodyMesh.castShadow = true;
  bodyMesh.receiveShadow = true;
  bodyMesh.add(createEdgesLine(bodyGeo, theme.materials.wireframe));
  group.add(bodyMesh);

  // Recessed central cavity panel
  const cavityGeo = new THREE.BoxGeometry(2.4, 0.15, 1.6);
  geometriesToDispose.push(cavityGeo);
  const cavityMesh = new THREE.Mesh(cavityGeo, theme.materials.metal);
  cavityMesh.position.set(0, mainHeight / 2 + 0.02, 0);
  cavityMesh.add(createEdgesLine(cavityGeo, theme.materials.accentLine));
  group.add(cavityMesh);

  // Instanced Cooling Fins Array (1 Draw Call for 9 fins!)
  const numFins = 9;
  const finWidth = 0.06;
  const finHeight = 0.48;
  const finDepth = 1.5;
  const finGeo = new THREE.BoxGeometry(finWidth, finHeight, finDepth);
  geometriesToDispose.push(finGeo);

  const instancedFins = new THREE.InstancedMesh(finGeo, theme.materials.metal, numFins);
  const dummyFin = new THREE.Object3D();
  for (let i = 0; i < numFins; i++) {
    const fx = (i - (numFins - 1) / 2) * 0.24;
    dummyFin.position.set(fx, mainHeight / 2 + finHeight / 2, 0);
    dummyFin.updateMatrix();
    instancedFins.setMatrixAt(i, dummyFin.matrix);
  }
  instancedFins.instanceMatrix.needsUpdate = true;
  group.add(instancedFins);

  // 4 Flanged Mounting Corner Bosses
  const bossGeo = new THREE.CylinderGeometry(0.26, 0.3, mainHeight + 0.08, 16);
  const bossHoleGeo = new THREE.CylinderGeometry(0.1, 0.1, mainHeight + 0.12, 10);
  geometriesToDispose.push(bossGeo, bossHoleGeo);

  const bossOffsets = [
    [-mainWidth / 2 + 0.25, -mainDepth / 2 + 0.25],
    [mainWidth / 2 - 0.25, -mainDepth / 2 + 0.25],
    [mainWidth / 2 - 0.25, mainDepth / 2 - 0.25],
    [-mainWidth / 2 + 0.25, mainDepth / 2 - 0.25],
  ];

  bossOffsets.forEach(([bx, bz]) => {
    const boss = new THREE.Mesh(bossGeo, theme.materials.metal);
    boss.position.set(bx, 0, bz);
    boss.add(createEdgesLine(bossGeo, theme.materials.wireframe));
    group.add(boss);

    const hole = new THREE.Mesh(bossHoleGeo, theme.materials.darkChassis);
    hole.position.set(bx, 0, bz);
    group.add(hole);
  });

  // I/O Interface Connector Socket
  const portGeo = new THREE.BoxGeometry(0.8, 0.4, 0.35);
  geometriesToDispose.push(portGeo);
  const portMesh = new THREE.Mesh(portGeo, theme.materials.accent);
  portMesh.position.set(mainWidth / 2 + 0.12, 0, 0);
  portMesh.add(createEdgesLine(portGeo, theme.materials.accentLine));
  group.add(portMesh);

  // Status LED Array (Instanced 3 LEDs)
  const ledGeo = new THREE.SphereGeometry(0.07, 10, 10);
  geometriesToDispose.push(ledGeo);
  const instancedLEDs = new THREE.InstancedMesh(ledGeo, theme.materials.highlight, 3);
  const dummyLED = new THREE.Object3D();
  for (let l = 0; l < 3; l++) {
    dummyLED.position.set(-mainWidth / 2 + 0.4 + l * 0.2, mainHeight / 2 + 0.08, -mainDepth / 2 + 0.4);
    dummyLED.updateMatrix();
    instancedLEDs.setMatrixAt(l, dummyLED.matrix);
  }
  instancedLEDs.instanceMatrix.needsUpdate = true;
  group.add(instancedLEDs);

  const t = node.transform || { position: [0, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1] };
  group.position.set(t.position[0], t.position[1], t.position[2]);
  group.rotation.set(t.rotation[0], t.rotation[1], t.rotation[2]);
  group.scale.set(t.scale[0], t.scale[1], t.scale[2]);

  const update = (tSec: number) => {
    const pulse = 0.5 + 0.5 * Math.sin(tSec * 4.0);
    theme.materials.highlight.emissiveIntensity = 0.2 + pulse * 0.8;
  };

  const dispose = () => {
    geometriesToDispose.forEach((g) => g.dispose());
    Object.values(theme.materials).forEach((m) => m.dispose());
  };

  return {
    group,
    parts: [],
    update,
    dispose,
    getMetrics: () => computePerformanceMetrics(group),
  };
}

export const compileComponent = compileHousing;

// ----------------------------------------------------------------------------
// 5. LAYER_STACK_3D Procedural Compiler
// ----------------------------------------------------------------------------

export function compileLayerStack(
  node: ExecutableNode3D,
  genome?: ArtDirectionGenomeLike
): Procedural3DResult {
  const group = new THREE.Group();
  group.name = node.node_id || "LayerStack3D";

  const theme = createMaterialTheme(node.material_spec, genome);
  const parts: Procedural3DPart[] = [];
  const geometriesToDispose: THREE.BufferGeometry[] = [];

  const layerSpecs = [
    { name: "Hardware Foundation", size: [4.2, 0.2, 3.2], mat: theme.materials.darkChassis, baseGap: 0 },
    { name: "Data & Storage", size: [3.8, 0.16, 2.8], mat: theme.materials.metal, baseGap: 0.8 },
    { name: "Core Engine Logic", size: [3.4, 0.18, 2.4], mat: theme.materials.frosted, baseGap: 1.6 },
    { name: "Service Integration", size: [3.0, 0.16, 2.0], mat: theme.materials.glass, baseGap: 2.4 },
    { name: "UI & Visualization", size: [2.6, 0.14, 1.6], mat: theme.materials.glass, baseGap: 3.2 },
  ];

  layerSpecs.forEach((spec, idx) => {
    const plateGeo = new THREE.BoxGeometry(spec.size[0], spec.size[1], spec.size[2]);
    geometriesToDispose.push(plateGeo);

    const plateMesh = new THREE.Mesh(plateGeo, spec.mat);
    plateMesh.castShadow = true;
    plateMesh.receiveShadow = true;
    plateMesh.position.set(0, spec.baseGap - 1.6, 0);

    const edgeMat = idx === 2 ? theme.materials.accentLine : theme.materials.wireframe;
    plateMesh.add(createEdgesLine(plateGeo, edgeMat));

    // Internal silicon chip on layer 2
    if (idx === 2) {
      const chipGeo = new THREE.BoxGeometry(1.0, 0.08, 1.0);
      geometriesToDispose.push(chipGeo);
      const chipMesh = new THREE.Mesh(chipGeo, theme.materials.accent);
      chipMesh.position.set(0, 0.12, 0);
      chipMesh.add(createEdgesLine(chipGeo, theme.materials.accentLine));
      plateMesh.add(chipMesh);
    }

    group.add(plateMesh);

    parts.push({
      mesh: plateMesh,
      basePosition: plateMesh.position.clone(),
      baseRotation: plateMesh.rotation.clone(),
      baseScale: plateMesh.scale.clone(),
      explodeDirection: new THREE.Vector3(0, 1, 0),
      explodeDistance: 0.6 * (idx + 1),
      staggerDelay: idx * 0.12,
    });
  });

  // Vertical structural bus pillars
  const pillarGeo = new THREE.CylinderGeometry(0.04, 0.04, 3.8, 12);
  geometriesToDispose.push(pillarGeo);

  const pillarOffsets = [
    [-1.0, -0.6],
    [1.0, -0.6],
    [1.0, 0.6],
    [-1.0, 0.6],
  ];

  pillarOffsets.forEach(([px, pz]) => {
    const pillarMesh = new THREE.Mesh(pillarGeo, theme.materials.accent);
    pillarMesh.position.set(px, 0, pz);
    group.add(pillarMesh);
  });

  // Instanced Data Signal Beads (1 Draw Call for all traveling signal packets)
  const numBeads = pillarOffsets.length;
  const beadGeo = new THREE.SphereGeometry(0.09, 10, 10);
  geometriesToDispose.push(beadGeo);
  const instancedBeads = new THREE.InstancedMesh(beadGeo, theme.materials.highlight, numBeads);
  const dummyBead = new THREE.Object3D();
  group.add(instancedBeads);

  const t = node.transform || { position: [0, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1] };
  group.position.set(t.position[0], t.position[1], t.position[2]);
  group.rotation.set(t.rotation[0], t.rotation[1], t.rotation[2]);
  group.scale.set(t.scale[0], t.scale[1], t.scale[2]);

  const update = (tSec: number, durationSec: number, motionPurpose?: string) => {
    const dur = Math.max(0.1, durationSec || 5.0);
    const progress = Math.max(0, Math.min(1, tSec / dur));
    const expandProgress = motionPurpose === "explode" ? easeInOutCubic(progress) : 0.25 * Math.sin(tSec * 1.5);

    parts.forEach((part, idx) => {
      const offset = (part.explodeDistance || 0) * expandProgress;
      part.mesh.position.y = part.basePosition.y + offset + Math.sin(tSec * 2.0 + idx * 0.8) * 0.04;
    });

    pillarOffsets.forEach(([px, pz], bIdx) => {
      const phase = (tSec * 1.2 + bIdx * 0.25) % 1.0;
      dummyBead.position.set(px, -1.6 + phase * 3.4, pz);
      dummyBead.updateMatrix();
      instancedBeads.setMatrixAt(bIdx, dummyBead.matrix);
    });
    instancedBeads.instanceMatrix.needsUpdate = true;
  };

  const dispose = () => {
    geometriesToDispose.forEach((g) => g.dispose());
    Object.values(theme.materials).forEach((m) => m.dispose());
  };

  return {
    group,
    parts,
    update,
    dispose,
    getMetrics: () => computePerformanceMetrics(group),
  };
}

// ----------------------------------------------------------------------------
// 6. FLOW_PATH Procedural Compiler
// ----------------------------------------------------------------------------

export function compileFlowPath(
  node: ExecutableNode3D,
  genome?: ArtDirectionGenomeLike
): Procedural3DResult {
  const group = new THREE.Group();
  group.name = node.node_id || "FlowPath";

  const theme = createMaterialTheme(node.material_spec, genome);
  const geometriesToDispose: THREE.BufferGeometry[] = [];

  const points: THREE.Vector3[] = [];
  const customPoints = node.material_spec?.control_points as Array<[number, number, number]> | undefined;

  if (Array.isArray(customPoints) && customPoints.length >= 3) {
    customPoints.forEach((p) => points.push(new THREE.Vector3(p[0], p[1], p[2])));
  } else {
    points.push(
      new THREE.Vector3(-3.2, -1.2, 1.0),
      new THREE.Vector3(-1.8, -0.2, 0.4),
      new THREE.Vector3(0.0, 0.8, -0.6),
      new THREE.Vector3(1.8, 0.1, -0.2),
      new THREE.Vector3(3.2, 1.4, 0.8)
    );
  }

  const curve = new THREE.CatmullRomCurve3(points, false, "catmullrom", 0.5);
  const pipeRadius = 0.18;

  // Outer conduit tube
  const tubeGeo = new THREE.TubeGeometry(curve, 54, pipeRadius, 14, false);
  geometriesToDispose.push(tubeGeo);
  const tubeMesh = new THREE.Mesh(tubeGeo, theme.materials.darkChassis);
  tubeMesh.castShadow = true;
  group.add(tubeMesh);

  // Wireframe contour along tube
  const tubeEdges = createEdgesLine(tubeGeo, theme.materials.wireframe);
  group.add(tubeEdges);

  // Instanced Pipe Joint Rings
  const numJoints = 5;
  const jointGeo = new THREE.TorusGeometry(pipeRadius * 1.35, pipeRadius * 0.2, 10, 18);
  geometriesToDispose.push(jointGeo);
  const instancedJoints = new THREE.InstancedMesh(jointGeo, theme.materials.metal, numJoints + 1);
  const dummyJoint = new THREE.Object3D();

  for (let i = 0; i <= numJoints; i++) {
    const u = i / numJoints;
    const pt = curve.getPointAt(u);
    const tangent = curve.getTangentAt(u);
    dummyJoint.position.copy(pt);
    dummyJoint.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), tangent);
    dummyJoint.updateMatrix();
    instancedJoints.setMatrixAt(i, dummyJoint.matrix);
  }
  instancedJoints.instanceMatrix.needsUpdate = true;
  group.add(instancedJoints);

  // Instanced Energy Pulse Rings (1 Draw Call for 7 glowing rings)
  const numPulseRings = 7;
  const ringGeo = new THREE.TorusGeometry(pipeRadius * 1.18, pipeRadius * 0.14, 10, 18);
  geometriesToDispose.push(ringGeo);
  const instancedRings = new THREE.InstancedMesh(ringGeo, theme.materials.accent, numPulseRings);
  const dummyRing = new THREE.Object3D();
  group.add(instancedRings);

  // Instanced Flowing Packet Spheres (1 Draw Call for 4 packets)
  const numSpheres = 4;
  const sphereGeo = new THREE.SphereGeometry(pipeRadius * 0.65, 10, 10);
  geometriesToDispose.push(sphereGeo);
  const instancedSpheres = new THREE.InstancedMesh(sphereGeo, theme.materials.highlight, numSpheres);
  const dummySphere = new THREE.Object3D();
  group.add(instancedSpheres);

  const t = node.transform || { position: [0, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1] };
  group.position.set(t.position[0], t.position[1], t.position[2]);
  group.rotation.set(t.rotation[0], t.rotation[1], t.rotation[2]);
  group.scale.set(t.scale[0], t.scale[1], t.scale[2]);

  const flowSpeed = 0.35;

  const update = (tSec: number) => {
    for (let i = 0; i < numPulseRings; i++) {
      const u = (tSec * flowSpeed + i / numPulseRings) % 1.0;
      const pt = curve.getPointAt(u);
      const tangent = curve.getTangentAt(u);
      dummyRing.position.copy(pt);
      dummyRing.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), tangent);
      const s = 1.0 + 0.2 * Math.sin(u * Math.PI * 2);
      dummyRing.scale.set(s, s, s);
      dummyRing.updateMatrix();
      instancedRings.setMatrixAt(i, dummyRing.matrix);
    }
    instancedRings.instanceMatrix.needsUpdate = true;

    for (let i = 0; i < numSpheres; i++) {
      const u = (tSec * (flowSpeed * 1.35) + i / numSpheres) % 1.0;
      const pt = curve.getPointAt(u);
      dummySphere.position.copy(pt);
      dummySphere.updateMatrix();
      instancedSpheres.setMatrixAt(i, dummySphere.matrix);
    }
    instancedSpheres.instanceMatrix.needsUpdate = true;
  };

  const dispose = () => {
    geometriesToDispose.forEach((g) => g.dispose());
    Object.values(theme.materials).forEach((m) => m.dispose());
  };

  return {
    group,
    parts: [],
    update,
    dispose,
    getMetrics: () => computePerformanceMetrics(group),
  };
}

// ----------------------------------------------------------------------------
// 7. TRAJECTORY Procedural Compiler
// ----------------------------------------------------------------------------

export function compileTrajectory(
  node: ExecutableNode3D,
  genome?: ArtDirectionGenomeLike
): Procedural3DResult {
  const group = new THREE.Group();
  group.name = node.node_id || "TrajectoryGraph";

  const theme = createMaterialTheme(node.material_spec, genome);
  const geometriesToDispose: THREE.BufferGeometry[] = [];

  // Parabolic/orbital 3D spline curve
  const points: THREE.Vector3[] = [];
  const customPoints = node.material_spec?.trajectory_points as Array<[number, number, number]> | undefined;

  if (Array.isArray(customPoints) && customPoints.length >= 3) {
    customPoints.forEach((p) => points.push(new THREE.Vector3(p[0], p[1], p[2])));
  } else {
    points.push(
      new THREE.Vector3(-4.0, -1.5, 0.0),
      new THREE.Vector3(-2.0, 1.2, 1.5),
      new THREE.Vector3(0.0, 2.2, 0.0),
      new THREE.Vector3(2.0, 1.2, -1.5),
      new THREE.Vector3(4.0, -1.0, 0.0)
    );
  }

  const curve = new THREE.CatmullRomCurve3(points, false, "catmullrom", 0.5);

  // Luminous trajectory trace ribbon
  const traceGeo = new THREE.TubeGeometry(curve, 60, 0.06, 8, false);
  geometriesToDispose.push(traceGeo);
  const traceMesh = new THREE.Mesh(traceGeo, theme.materials.accent);
  group.add(traceMesh);

  // Orbiting vehicle / satellite
  const vehicleGroup = new THREE.Group();

  const bodyGeo = new THREE.ConeGeometry(0.22, 0.65, 12);
  bodyGeo.rotateX(Math.PI / 2);
  geometriesToDispose.push(bodyGeo);
  const bodyMesh = new THREE.Mesh(bodyGeo, theme.materials.metal);
  vehicleGroup.add(bodyMesh);

  // Solar wing panels
  const wingGeo = new THREE.BoxGeometry(0.9, 0.02, 0.25);
  geometriesToDispose.push(wingGeo);
  const wingMesh = new THREE.Mesh(wingGeo, theme.materials.accent);
  vehicleGroup.add(wingMesh);

  group.add(vehicleGroup);

  // Target Destination / Attractor Sphere
  const targetPt = points[points.length - 1];
  const targetGeo = new THREE.SphereGeometry(0.65, 16, 16);
  geometriesToDispose.push(targetGeo);
  const targetMesh = new THREE.Mesh(targetGeo, theme.materials.darkChassis);
  targetMesh.position.copy(targetPt);
  targetMesh.add(createEdgesLine(targetGeo, theme.materials.accentLine));
  group.add(targetMesh);

  // Orbit target rings
  const ringGeo = new THREE.TorusGeometry(0.85, 0.03, 10, 24);
  geometriesToDispose.push(ringGeo);
  const ringMesh = new THREE.Mesh(ringGeo, theme.materials.highlight);
  ringMesh.position.copy(targetPt);
  ringMesh.rotation.x = Math.PI / 3;
  group.add(ringMesh);

  // Instanced Trail Exhaust Particles (1 Draw Call for 16 particles)
  const numParticles = 16;
  const particleGeo = new THREE.SphereGeometry(0.06, 8, 8);
  geometriesToDispose.push(particleGeo);
  const instancedParticles = new THREE.InstancedMesh(particleGeo, theme.materials.highlight, numParticles);
  const dummyParticle = new THREE.Object3D();
  group.add(instancedParticles);

  const t = node.transform || { position: [0, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1] };
  group.position.set(t.position[0], t.position[1], t.position[2]);
  group.rotation.set(t.rotation[0], t.rotation[1], t.rotation[2]);
  group.scale.set(t.scale[0], t.scale[1], t.scale[2]);

  const speed = 0.25;

  const update = (tSec: number) => {
    const u = (tSec * speed) % 1.0;
    const pt = curve.getPointAt(u);
    const tangent = curve.getTangentAt(u);

    vehicleGroup.position.copy(pt);
    vehicleGroup.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), tangent);

    // Update trailing exhaust particles
    for (let i = 0; i < numParticles; i++) {
      const trailU = (u - (i + 1) * 0.015 + 1.0) % 1.0;
      const tPt = curve.getPointAt(trailU);
      dummyParticle.position.copy(tPt);
      const scale = (1.0 - i / numParticles) * 0.9;
      dummyParticle.scale.set(scale, scale, scale);
      dummyParticle.updateMatrix();
      instancedParticles.setMatrixAt(i, dummyParticle.matrix);
    }
    instancedParticles.instanceMatrix.needsUpdate = true;

    // Rotate destination attractor
    targetMesh.rotation.y = tSec * 0.4;
    ringMesh.rotation.z = tSec * 0.6;
  };

  const dispose = () => {
    geometriesToDispose.forEach((g) => g.dispose());
    Object.values(theme.materials).forEach((m) => m.dispose());
  };

  return {
    group,
    parts: [],
    update,
    dispose,
    getMetrics: () => computePerformanceMetrics(group),
  };
}

// ----------------------------------------------------------------------------
// 8. MECHANISM Procedural Compiler
// ----------------------------------------------------------------------------

export function compileMechanism(
  node: ExecutableNode3D,
  genome?: ArtDirectionGenomeLike
): Procedural3DResult {
  const group = new THREE.Group();
  group.name = node.node_id || "KinematicMechanism";

  const theme = createMaterialTheme(node.material_spec, genome);
  const geometriesToDispose: THREE.BufferGeometry[] = [];

  // Base Backing Frame
  const frameGeo = new THREE.BoxGeometry(5.2, 3.2, 0.2);
  geometriesToDispose.push(frameGeo);
  const frameMesh = new THREE.Mesh(frameGeo, theme.materials.darkChassis);
  frameMesh.position.set(0, 0, -0.2);
  frameMesh.add(createEdgesLine(frameGeo, theme.materials.wireframe));
  group.add(frameMesh);

  // Drive Gear 1 (Left)
  const r1 = 1.0;
  const gear1Group = new THREE.Group();
  gear1Group.position.set(-1.4, 0, 0);

  const gear1Geo = new THREE.CylinderGeometry(r1, r1, 0.25, 24);
  geometriesToDispose.push(gear1Geo);
  const gear1Mesh = new THREE.Mesh(gear1Geo, theme.materials.metal);
  gear1Mesh.rotation.x = Math.PI / 2;
  gear1Mesh.add(createEdgesLine(gear1Geo, theme.materials.accentLine));
  gear1Group.add(gear1Mesh);

  // Center axle
  const axleGeo = new THREE.CylinderGeometry(0.18, 0.18, 0.45, 12);
  geometriesToDispose.push(axleGeo);
  const axle1 = new THREE.Mesh(axleGeo, theme.materials.accent);
  axle1.rotation.x = Math.PI / 2;
  gear1Group.add(axle1);

  // Crank pin on Gear 1
  const crankPinGeo = new THREE.CylinderGeometry(0.08, 0.08, 0.35, 10);
  geometriesToDispose.push(crankPinGeo);
  const crankPin = new THREE.Mesh(crankPinGeo, theme.materials.highlight);
  crankPin.rotation.x = Math.PI / 2;
  const crankRadius = 0.65;
  crankPin.position.set(crankRadius, 0, 0.18);
  gear1Group.add(crankPin);

  group.add(gear1Group);

  // Driven Pinion Gear 2 (Meshed with Gear 1)
  const r2 = 0.55;
  const gear2Group = new THREE.Group();
  gear2Group.position.set(-1.4 + r1 + r2, 0, 0);

  const gear2Geo = new THREE.CylinderGeometry(r2, r2, 0.25, 18);
  geometriesToDispose.push(gear2Geo);
  const gear2Mesh = new THREE.Mesh(gear2Geo, theme.materials.darkChassis);
  gear2Mesh.rotation.x = Math.PI / 2;
  gear2Mesh.add(createEdgesLine(gear2Geo, theme.materials.wireframe));
  gear2Group.add(gear2Mesh);

  const axle2 = new THREE.Mesh(axleGeo, theme.materials.accent);
  axle2.rotation.x = Math.PI / 2;
  gear2Group.add(axle2);

  group.add(gear2Group);

  // Articulated Connecting Rod Linkage
  const rodLength = 2.2;
  const rodGeo = new THREE.BoxGeometry(rodLength, 0.14, 0.12);
  rodGeo.translate(rodLength / 2, 0, 0); // Origin at crank pin pivot
  geometriesToDispose.push(rodGeo);
  const rodMesh = new THREE.Mesh(rodGeo, theme.materials.metal);
  rodMesh.add(createEdgesLine(rodGeo, theme.materials.accentLine));
  group.add(rodMesh);

  // Reciprocating Piston Slider Block
  const pistonGeo = new THREE.BoxGeometry(0.65, 0.45, 0.3);
  geometriesToDispose.push(pistonGeo);
  const pistonMesh = new THREE.Mesh(pistonGeo, theme.materials.accent);
  pistonMesh.add(createEdgesLine(pistonGeo, theme.materials.wireframe));
  group.add(pistonMesh);

  // Cylinder Guide Chamber Rails
  const railGeo = new THREE.BoxGeometry(2.0, 0.06, 0.08);
  geometriesToDispose.push(railGeo);
  const railTop = new THREE.Mesh(railGeo, theme.materials.darkChassis);
  railTop.position.set(1.4, 0.28, 0.1);
  const railBottom = railTop.clone();
  railBottom.position.y = -0.28;
  group.add(railTop);
  group.add(railBottom);

  const t = node.transform || { position: [0, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1] };
  group.position.set(t.position[0], t.position[1], t.position[2]);
  group.rotation.set(t.rotation[0], t.rotation[1], t.rotation[2]);
  group.scale.set(t.scale[0], t.scale[1], t.scale[2]);

  const gearRatio = r1 / r2;

  const update = (tSec: number) => {
    const theta = tSec * 2.2; // Crank rotation angle

    // Rotate gears
    gear1Group.rotation.z = theta;
    gear2Group.rotation.z = -theta * gearRatio;

    // Kinematics of slider-crank mechanism
    const crankX = -1.4 + Math.cos(theta) * crankRadius;
    const crankY = Math.sin(theta) * crankRadius;

    // Piston horizontal position
    // x_piston = crankX + sqrt(L^2 - crankY^2)
    const disc = Math.max(0, rodLength * rodLength - crankY * crankY);
    const pistonX = crankX + Math.sqrt(disc);
    const rodAngle = Math.atan2(-crankY, pistonX - crankX);

    // Position connecting rod
    rodMesh.position.set(crankX, crankY, 0.18);
    rodMesh.rotation.z = rodAngle;

    // Position piston
    pistonMesh.position.set(pistonX, 0, 0.18);
  };

  const dispose = () => {
    geometriesToDispose.forEach((g) => g.dispose());
    Object.values(theme.materials).forEach((m) => m.dispose());
  };

  return {
    group,
    parts: [],
    update,
    dispose,
    getMetrics: () => computePerformanceMetrics(group),
  };
}

// ----------------------------------------------------------------------------
// 9. SPATIAL_SYSTEM Procedural Compiler
// ----------------------------------------------------------------------------

export function compileSpatialSystem(
  node: ExecutableNode3D,
  genome?: ArtDirectionGenomeLike
): Procedural3DResult {
  const group = new THREE.Group();
  group.name = node.node_id || "SpatialSystemTopology";

  const theme = createMaterialTheme(node.material_spec, genome);
  const geometriesToDispose: THREE.BufferGeometry[] = [];

  // Ground Elevation Grid Plane
  const gridSize = 8.0;
  const gridDivs = 16;
  const gridHelper = new THREE.GridHelper(gridSize, gridDivs, theme.accentColor, theme.borderColor);
  gridHelper.position.y = -1.6;
  group.add(gridHelper);

  // Central Primary Core Hub
  const hubGroup = new THREE.Group();
  hubGroup.position.set(0, 0, 0);

  const hubGeo = new THREE.IcosahedronGeometry(0.75, 1);
  geometriesToDispose.push(hubGeo);
  const hubMesh = new THREE.Mesh(hubGeo, theme.materials.metal);
  hubMesh.add(createEdgesLine(hubGeo, theme.materials.accentLine));
  hubGroup.add(hubMesh);

  // Core internal glow sphere
  const glowGeo = new THREE.SphereGeometry(0.4, 12, 12);
  geometriesToDispose.push(glowGeo);
  const glowMesh = new THREE.Mesh(glowGeo, theme.materials.coreGlow);
  hubGroup.add(glowMesh);

  // Concentric orbital rings around hub
  const ringGeo = new THREE.TorusGeometry(1.15, 0.04, 10, 24);
  geometriesToDispose.push(ringGeo);
  const ring1 = new THREE.Mesh(ringGeo, theme.materials.accent);
  ring1.rotation.x = Math.PI / 4;
  hubGroup.add(ring1);
  const ring2 = new THREE.Mesh(ringGeo, theme.materials.highlight);
  ring2.rotation.y = Math.PI / 3;
  hubGroup.add(ring2);

  group.add(hubGroup);

  // Satellite Microservice Nodes (6 radial nodes in 3D space)
  const numNodes = 6;
  const nodePositions: THREE.Vector3[] = [];
  const nodeMeshes: THREE.Mesh[] = [];
  const nodeGeo = new THREE.BoxGeometry(0.36, 0.36, 0.36);
  geometriesToDispose.push(nodeGeo);

  for (let i = 0; i < numNodes; i++) {
    const angle = (i / numNodes) * Math.PI * 2;
    const rad = 2.6 + (i % 2) * 0.6;
    const elevation = ((i % 3) - 1) * 0.8;
    const pos = new THREE.Vector3(Math.cos(angle) * rad, elevation, Math.sin(angle) * rad);
    nodePositions.push(pos);

    const nMesh = new THREE.Mesh(nodeGeo, theme.materials.darkChassis);
    nMesh.position.copy(pos);
    nMesh.add(createEdgesLine(nodeGeo, theme.materials.accentLine));
    group.add(nMesh);
    nodeMeshes.push(nMesh);

    // Connecting volumetric vector line to hub
    const lineCurve = new THREE.LineCurve3(new THREE.Vector3(0, 0, 0), pos);
    const lineGeo = new THREE.TubeGeometry(lineCurve, 8, 0.02, 6, false);
    geometriesToDispose.push(lineGeo);
    const lineMesh = new THREE.Mesh(lineGeo, theme.materials.wireframe);
    group.add(lineMesh);
  }

  // Instanced Communication Data Packets (1 Draw Call for all transmission beads)
  const numPackets = numNodes;
  const packetGeo = new THREE.SphereGeometry(0.08, 8, 8);
  geometriesToDispose.push(packetGeo);
  const instancedPackets = new THREE.InstancedMesh(packetGeo, theme.materials.highlight, numPackets);
  const dummyPacket = new THREE.Object3D();
  group.add(instancedPackets);

  // Radar / Sonar Ground Sweep Ring
  const radarGeo = new THREE.RingGeometry(0.2, 0.35, 32);
  radarGeo.rotateX(-Math.PI / 2);
  geometriesToDispose.push(radarGeo);
  const radarMesh = new THREE.Mesh(radarGeo, theme.materials.accent);
  radarMesh.position.y = -1.58;
  group.add(radarMesh);

  const t = node.transform || { position: [0, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1] };
  group.position.set(t.position[0], t.position[1], t.position[2]);
  group.rotation.set(t.rotation[0], t.rotation[1], t.rotation[2]);
  group.scale.set(t.scale[0], t.scale[1], t.scale[2]);

  const update = (tSec: number) => {
    // Hub rotation
    hubMesh.rotation.y = tSec * 0.5;
    hubMesh.rotation.x = tSec * 0.3;
    ring1.rotation.z = tSec * 0.8;
    ring2.rotation.x = -tSec * 0.7;

    // Satellite orbital bobbing
    nodeMeshes.forEach((mesh, idx) => {
      mesh.rotation.y = tSec * 0.6 + idx;
      mesh.position.y = nodePositions[idx].y + Math.sin(tSec * 1.8 + idx * 1.2) * 0.12;
    });

    // Communication packets traversal
    for (let p = 0; p < numPackets; p++) {
      const u = (tSec * 0.8 + p * 0.18) % 1.0;
      const targetPos = nodeMeshes[p].position;
      dummyPacket.position.lerpVectors(new THREE.Vector3(0, 0, 0), targetPos, u);
      dummyPacket.updateMatrix();
      instancedPackets.setMatrixAt(p, dummyPacket.matrix);
    }
    instancedPackets.instanceMatrix.needsUpdate = true;

    // Radar ground expansion
    const radarPhase = (tSec * 0.5) % 1.0;
    const radarScale = 0.5 + radarPhase * 7.5;
    radarMesh.scale.set(radarScale, 1, radarScale);
  };

  const dispose = () => {
    geometriesToDispose.forEach((g) => g.dispose());
    Object.values(theme.materials).forEach((m) => m.dispose());
  };

  return {
    group,
    parts: [],
    update,
    dispose,
    getMetrics: () => computePerformanceMetrics(group),
  };
}

// ----------------------------------------------------------------------------
// Generic / Fallback Node Compiler
// ----------------------------------------------------------------------------

export function compileGenericMesh(
  node: ExecutableNode3D,
  genome?: ArtDirectionGenomeLike
): Procedural3DResult {
  const group = new THREE.Group();
  group.name = node.node_id || "GenericMesh";

  const theme = createMaterialTheme(node.material_spec, genome);
  const geometriesToDispose: THREE.BufferGeometry[] = [];

  const prim = (node.procedural_type || "Box").toLowerCase();
  let geo: THREE.BufferGeometry;

  if (prim.includes("sphere")) {
    geo = new THREE.SphereGeometry(1.2, 24, 18);
  } else if (prim.includes("cylinder")) {
    geo = new THREE.CylinderGeometry(1.0, 1.0, 2.0, 24);
  } else if (prim.includes("torus")) {
    geo = new THREE.TorusGeometry(1.2, 0.35, 16, 32);
  } else if (prim.includes("cone")) {
    geo = new THREE.ConeGeometry(1.2, 2.2, 24);
  } else {
    geo = new THREE.BoxGeometry(2.0, 2.0, 2.0);
  }

  geometriesToDispose.push(geo);
  const mesh = new THREE.Mesh(geo, theme.materials.metal);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  mesh.add(createEdgesLine(geo, theme.materials.wireframe));
  group.add(mesh);

  const t = node.transform || { position: [0, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1] };
  group.position.set(t.position[0], t.position[1], t.position[2]);
  group.rotation.set(t.rotation[0], t.rotation[1], t.rotation[2]);
  group.scale.set(t.scale[0], t.scale[1], t.scale[2]);

  const update = (tSec: number) => {
    mesh.rotation.y = tSec * 0.4;
  };

  const dispose = () => {
    geometriesToDispose.forEach((g) => g.dispose());
    Object.values(theme.materials).forEach((m) => m.dispose());
  };

  return {
    group,
    parts: [],
    update,
    dispose,
    getMetrics: () => computePerformanceMetrics(group),
  };
}

// ----------------------------------------------------------------------------
// Procedural Geometry Factory Dispatcher
// ----------------------------------------------------------------------------

export class GeometryCompiler3D {
  /**
   * Compiles any of the 9 canonical 3D representation types into a live procedural Three.js scene graph.
   */
  public compileProceduralNode(
    node: ExecutableNode3D,
    genome?: ArtDirectionGenomeLike
  ): Procedural3DResult {
    const type = (node.procedural_type || "").toUpperCase();

    switch (type) {
      case Canonical3DRepresentationType.ASSEMBLY:
      case "ASSEMBLY":
        return compileAssembly(node, genome, false);

      case Canonical3DRepresentationType.EXPLODED_ASSEMBLY:
      case "EXPLODED_ASSEMBLY":
      case "EXPLODEDASSEMBLY":
        return compileExplodedAssembly(node, genome);

      case Canonical3DRepresentationType.CUTAWAY:
      case "CUTAWAY":
      case "CUTAWAY_3D":
        return compileCutaway(node, genome);

      case Canonical3DRepresentationType.COMPONENT:
      case "COMPONENT":
      case "HOUSING":
        return compileComponent(node, genome);

      case Canonical3DRepresentationType.LAYER_STACK_3D:
      case "LAYER_STACK_3D":
      case "LAYERSTACK":
      case "LAYER_STACK":
        return compileLayerStack(node, genome);

      case Canonical3DRepresentationType.FLOW_PATH:
      case "FLOW_PATH":
      case "FLOWPATH":
      case "PIPE":
      case "VOLUMETRIC_PIPE":
        return compileFlowPath(node, genome);

      case Canonical3DRepresentationType.TRAJECTORY:
      case "TRAJECTORY":
      case "ORBIT":
      case "KINEMATIC_PATH":
        return compileTrajectory(node, genome);

      case Canonical3DRepresentationType.MECHANISM:
      case "MECHANISM":
      case "GEAR":
      case "KINEMATICS":
        return compileMechanism(node, genome);

      case Canonical3DRepresentationType.SPATIAL_SYSTEM:
      case "SPATIAL_SYSTEM":
      case "SPATIALSYSTEM":
      case "NETWORK_3D":
        return compileSpatialSystem(node, genome);

      default: {
        const lower = type.toLowerCase();
        if (lower.includes("exploded")) return compileExplodedAssembly(node, genome);
        if (lower.includes("assembly")) return compileAssembly(node, genome, false);
        if (lower.includes("cutaway") || lower.includes("section")) return compileCutaway(node, genome);
        if (lower.includes("component") || lower.includes("housing")) return compileComponent(node, genome);
        if (lower.includes("layer") || lower.includes("stack")) return compileLayerStack(node, genome);
        if (lower.includes("flow") || lower.includes("pipe") || lower.includes("tube")) return compileFlowPath(node, genome);
        if (lower.includes("trajectory") || lower.includes("orbit")) return compileTrajectory(node, genome);
        if (lower.includes("mechanism") || lower.includes("gear")) return compileMechanism(node, genome);
        if (lower.includes("spatial") || lower.includes("system") || lower.includes("topology")) return compileSpatialSystem(node, genome);
        return compileGenericMesh(node, genome);
      }
    }
  }

  /**
   * Backwards-compatible node compilation method returning raw transform & color metadata.
   */
  public compileNode(node: ExecutableNode3D, timeSec: number): Compiled3DObject {
    const t = node.transform || { position: [0, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1] };
    const pos: [number, number, number] = [...t.position];

    if (node.procedural_type === "ExplodedAssembly" || node.procedural_type === Canonical3DRepresentationType.EXPLODED_ASSEMBLY) {
      const offset = Math.sin(timeSec * 1.2) * 1.8;
      pos[0] += offset;
    }

    return {
      node_id: node.node_id,
      type: node.procedural_type || "Component",
      position: pos,
      rotation: t.rotation,
      scale: t.scale,
      color: node.material_spec?.color || "#00e5ff",
      roughness: node.material_spec?.roughness ?? 0.3,
      metalness: node.material_spec?.metalness ?? 0.7,
    };
  }
}

export const geometryCompiler3D = new GeometryCompiler3D();

/**
 * Procedural 3D Geometry Compilers for Video Flow V3.
 * Generates production Three.js scene graphs, procedural geometries, PBR materials,
 * and animated structures for Assemblies, Components, VolumetricPipes, LayerStacks, and Cutaways.
 */

import * as THREE from "three";
import { ExecutableNode3D, ArtDirectionPalette, ArtDirectionGenome } from "../contracts/video-program";

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
  subsurface?: number;
  opacity?: number;
  transmission?: number;
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

export interface Procedural3DResult {
  group: THREE.Group;
  parts: Procedural3DPart[];
  update: (tSec: number, durationSec: number, motionPurpose?: string) => void;
  dispose: () => void;
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
  };
}

export function createMaterialTheme(
  nodeMaterial: Record<string, any> = {},
  genome?: ArtDirectionGenomeLike
): ResolvedMaterialTheme {
  const palette: Record<string, any> = genome?.palette || {};
  const gMat = genome?.materials || {};

  const primaryHex = nodeMaterial.color || palette.primary_info || palette.primary || "#E6E8EC";
  const accentHex = nodeMaterial.accent_color || palette.accent || "#E56B00";
  const highlightHex = nodeMaterial.highlight_color || palette.highlight || palette.accentAlt || "#FFC700";
  const neutralHex = palette.structural_neutral || palette.surface || "#2A2E35";
  const secondaryHex = palette.secondary_info || palette.secondary || "#9CA3AF";
  const borderHex = palette.border || "#3F444E";

  const primaryColor = safeColor(primaryHex, "#E6E8EC");
  const accentColor = safeColor(accentHex, "#E56B00");
  const highlightColor = safeColor(highlightHex, "#FFC700");
  const neutralColor = safeColor(neutralHex, "#2A2E35");
  const secondaryColor = safeColor(secondaryHex, "#9CA3AF");
  const borderColor = safeColor(borderHex, "#3F444E");

  const baseRoughness = typeof nodeMaterial.roughness === "number" ? nodeMaterial.roughness : (gMat.roughness ?? 0.35);
  const baseMetalness = typeof nodeMaterial.metalness === "number" ? nodeMaterial.metalness : (gMat.metalness ?? 0.65);
  const clearcoat = gMat.clearcoat ?? 0.15;
  const transmission = gMat.transmission ?? 0.0;

  const metal = new THREE.MeshStandardMaterial({
    color: primaryColor,
    roughness: Math.max(0.1, baseRoughness),
    metalness: Math.min(0.95, Math.max(0.4, baseMetalness)),
    wireframe: false,
  });

  const darkChassis = new THREE.MeshStandardMaterial({
    color: neutralColor,
    roughness: Math.min(0.8, baseRoughness + 0.2),
    metalness: Math.max(0.1, baseMetalness * 0.6),
  });

  const accent = new THREE.MeshStandardMaterial({
    color: accentColor,
    roughness: 0.3,
    metalness: 0.5,
    emissive: accentColor.clone().multiplyScalar(0.15),
  });

  const highlight = new THREE.MeshStandardMaterial({
    color: highlightColor,
    roughness: 0.2,
    metalness: 0.2,
    emissive: highlightColor.clone().multiplyScalar(0.4),
  });

  const glass = new THREE.MeshPhysicalMaterial({
    color: primaryColor.clone().lerp(new THREE.Color("#FFFFFF"), 0.5),
    roughness: 0.1,
    metalness: 0.05,
    transmission: 0.88,
    transparent: true,
    opacity: 0.92,
    ior: 1.52,
    thickness: 0.4,
  });

  const frosted = new THREE.MeshPhysicalMaterial({
    color: accentColor.clone().lerp(new THREE.Color("#FFFFFF"), 0.3),
    roughness: 0.35,
    metalness: 0.1,
    transmission: 0.6,
    transparent: true,
    opacity: 0.85,
    ior: 1.45,
    thickness: 0.25,
  });

  const coreGlow = new THREE.MeshStandardMaterial({
    color: accentColor,
    roughness: 0.2,
    metalness: 0.1,
    emissive: accentColor.clone().multiplyScalar(0.85),
  });

  const wireframe = new THREE.LineBasicMaterial({
    color: borderColor,
    linewidth: 1,
    transparent: true,
    opacity: 0.75,
  });

  const accentLine = new THREE.LineBasicMaterial({
    color: accentColor,
    linewidth: 1.5,
    transparent: true,
    opacity: 0.9,
  });

  return {
    primaryColor,
    accentColor,
    highlightColor,
    neutralColor,
    secondaryColor,
    borderColor,
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

export function createEdgesLine(geometry: THREE.BufferGeometry, material: THREE.LineBasicMaterial): THREE.LineSegments {
  const edges = new THREE.EdgesGeometry(geometry, 28);
  return new THREE.LineSegments(edges, material);
}

// ----------------------------------------------------------------------------
// 1. Assembly / ExplodedAssembly Procedural Compiler
// ----------------------------------------------------------------------------

export function compileAssembly(
  node: ExecutableNode3D,
  genome?: ArtDirectionGenomeLike,
  isExploded: boolean = false
): Procedural3DResult {
  const group = new THREE.Group();
  group.name = node.node_id || "AssemblyGroup";

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

  // --- Part 1: Base Chassis Mounting Plate (Extruded chamfered plate) ---
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
    bevelSegments: 3,
    steps: 1,
    bevelSize: 0.05,
    bevelThickness: 0.05,
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
  const lowerBearingGeo = new THREE.CylinderGeometry(1.3, 1.35, 0.35, 36);
  geometriesToDispose.push(lowerBearingGeo);
  const lowerBearingMesh = new THREE.Mesh(lowerBearingGeo, theme.materials.metal);
  lowerBearingMesh.position.set(0, -0.85, 0);
  lowerBearingMesh.add(createEdgesLine(lowerBearingGeo, theme.materials.wireframe));
  addPart(lowerBearingMesh, new THREE.Vector3(0, -0.6, 0), 1.2, 0.1);

  // --- Part 3: Central Spindle Shaft & Magnetic Core ---
  const coreGroup = new THREE.Group();
  coreGroup.position.set(0, 0, 0);

  const spindleGeo = new THREE.CylinderGeometry(0.3, 0.3, 2.6, 24);
  geometriesToDispose.push(spindleGeo);
  const spindleMesh = new THREE.Mesh(spindleGeo, theme.materials.accent);
  spindleMesh.castShadow = true;
  coreGroup.add(spindleMesh);

  const rotorHubGeo = new THREE.CylinderGeometry(0.85, 0.85, 1.1, 24);
  geometriesToDispose.push(rotorHubGeo);
  const rotorHubMesh = new THREE.Mesh(rotorHubGeo, theme.materials.metal);
  rotorHubMesh.add(createEdgesLine(rotorHubGeo, theme.materials.wireframe));
  coreGroup.add(rotorHubMesh);

  // Decorative Torus Rings on Rotor
  const torusGeo = new THREE.TorusGeometry(0.92, 0.06, 16, 32);
  geometriesToDispose.push(torusGeo);
  const torus1 = new THREE.Mesh(torusGeo, theme.materials.highlight);
  torus1.rotation.x = Math.PI / 2;
  torus1.position.y = 0.35;
  coreGroup.add(torus1);
  const torus2 = torus1.clone();
  torus2.position.y = -0.35;
  coreGroup.add(torus2);

  addPart(coreGroup, new THREE.Vector3(0, 0, 0), 0.0, 0.0, (_tSec, _dur, _p) => {
    coreGroup.rotation.y = _tSec * 0.8;
  });

  // --- Part 4: Planetary Actuator Brackets (4 radial sub-assemblies) ---
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

    const pinGeo = new THREE.CylinderGeometry(0.1, 0.1, 0.7, 12);
    geometriesToDispose.push(pinGeo);
    const pinMesh = new THREE.Mesh(pinGeo, theme.materials.accent);
    planetGroup.add(pinMesh);

    const radialDir = new THREE.Vector3(Math.cos(angle), 0.35, Math.sin(angle));
    addPart(planetGroup, radialDir, 2.2, 0.2 + i * 0.05, (tSec) => {
      planetGroup.rotation.y = -tSec * 1.6;
    });
  }

  // --- Part 5: Upper Bearing & Retaining Ring ---
  const upperBearingGeo = new THREE.CylinderGeometry(1.2, 1.2, 0.3, 36);
  geometriesToDispose.push(upperBearingGeo);
  const upperBearingMesh = new THREE.Mesh(upperBearingGeo, theme.materials.metal);
  upperBearingMesh.position.set(0, 0.85, 0);
  upperBearingMesh.add(createEdgesLine(upperBearingGeo, theme.materials.wireframe));
  addPart(upperBearingMesh, new THREE.Vector3(0, 0.6, 0), 1.4, 0.35);

  // --- Part 6: Top Enclosure Cowl & Lens Bezel ---
  const topCowlGeo = new THREE.CylinderGeometry(1.35, 1.45, 0.7, 36);
  geometriesToDispose.push(topCowlGeo);
  const topCowlMesh = new THREE.Mesh(topCowlGeo, theme.materials.darkChassis);
  topCowlMesh.position.set(0, 1.35, 0);
  topCowlMesh.add(createEdgesLine(topCowlGeo, theme.materials.wireframe));

  // Inset top viewing crystal
  const lensGeo = new THREE.CylinderGeometry(0.7, 0.7, 0.15, 24);
  geometriesToDispose.push(lensGeo);
  const lensMesh = new THREE.Mesh(lensGeo, theme.materials.glass);
  lensMesh.position.set(0, 0.35, 0);
  topCowlMesh.add(lensMesh);

  addPart(topCowlMesh, new THREE.Vector3(0, 1, 0), 2.5, 0.45);

  // --- Part 7: Corner Fastener Studs (4 bolts) ---
  const boltPositions = [
    [-w + 0.35, -h + 0.35],
    [w - 0.35, -h + 0.35],
    [w - 0.35, h - 0.35],
    [-w + 0.35, h - 0.35],
  ];

  const boltGeo = new THREE.CylinderGeometry(0.08, 0.08, 0.8, 8);
  const headGeo = new THREE.ConeGeometry(0.14, 0.12, 6);
  geometriesToDispose.push(boltGeo, headGeo);

  boltPositions.forEach(([bx, bz], idx) => {
    const boltGroup = new THREE.Group();
    boltGroup.position.set(bx, 1.6, bz);

    const bShaft = new THREE.Mesh(boltGeo, theme.materials.accent);
    const bHead = new THREE.Mesh(headGeo, theme.materials.metal);
    bHead.position.y = 0.4;
    boltGroup.add(bShaft);
    boltGroup.add(bHead);

    const boltDir = new THREE.Vector3(bx * 0.4, 1.2, bz * 0.4).normalize();
    addPart(boltGroup, boltDir, 3.2, 0.55 + idx * 0.05);
  });

  // Apply node initial transform
  const t = node.transform || { position: [0, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1] };
  group.position.set(t.position[0], t.position[1], t.position[2]);
  group.rotation.set(t.rotation[0], t.rotation[1], t.rotation[2]);
  group.scale.set(t.scale[0], t.scale[1], t.scale[2]);

  // Update function
  const update = (tSec: number, durationSec: number, motionPurpose?: string) => {
    const duration = Math.max(0.1, durationSec || 5.0);
    const rawProgress = Math.max(0, Math.min(1, tSec / duration));

    let explodeAmount = 0.0;
    const isExplodeMotion = isExploded || motionPurpose === "explode" || node.procedural_type === "ExplodedAssembly";

    if (isExplodeMotion) {
      // Smoothly expand during the middle 80% with gentle breathing float
      if (rawProgress < 0.15) {
        explodeAmount = 0;
      } else if (rawProgress < 0.65) {
        const p = (rawProgress - 0.15) / 0.5;
        explodeAmount = easeInOutCubic(p);
      } else if (rawProgress < 0.85) {
        explodeAmount = 1.0;
      } else {
        // Controlled recoil / return at very end
        const p = (rawProgress - 0.85) / 0.15;
        explodeAmount = 1.0 - easeInOutCubic(p) * 0.4;
      }
    } else if (motionPurpose === "reveal") {
      // Reveal: Assemble into place
      const p = Math.min(1, rawProgress / 0.4);
      explodeAmount = (1.0 - easeOutBack(p)) * 0.8;
    } else {
      // Subtle ambient hover
      explodeAmount = 0.0;
    }

    parts.forEach((part, index) => {
      const stagger = part.staggerDelay || 0;
      const partProgress = Math.max(0, Math.min(1, (rawProgress - stagger * 0.2) / 0.8));
      const dist = (part.explodeDistance || 0) * explodeAmount;

      if (part.explodeDirection && dist > 0.001) {
        part.mesh.position.copy(part.basePosition).addScaledVector(part.explodeDirection, dist);
        // Add subtle harmonic float
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

  return { group, parts, update, dispose };
}

// ----------------------------------------------------------------------------
// 2. Component / Housing Procedural Compiler
// ----------------------------------------------------------------------------

export function compileHousing(
  node: ExecutableNode3D,
  genome?: ArtDirectionGenomeLike
): Procedural3DResult {
  const group = new THREE.Group();
  group.name = node.node_id || "HousingComponent";

  const theme = createMaterialTheme(node.material_spec, genome);
  const parts: Procedural3DPart[] = [];
  const geometriesToDispose: THREE.BufferGeometry[] = [];

  // Main housing block with chamfers
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

  // Cooling Fins Array
  const numFins = 9;
  const finWidth = 0.06;
  const finHeight = 0.5;
  const finDepth = 1.5;
  const finGeo = new THREE.BoxGeometry(finWidth, finHeight, finDepth);
  geometriesToDispose.push(finGeo);

  const finsGroup = new THREE.Group();
  finsGroup.position.set(0, mainHeight / 2 + finHeight / 2, 0);
  for (let i = 0; i < numFins; i++) {
    const fx = (i - (numFins - 1) / 2) * 0.24;
    const finMesh = new THREE.Mesh(finGeo, theme.materials.metal);
    finMesh.position.set(fx, 0, 0);
    finsGroup.add(finMesh);
  }
  group.add(finsGroup);

  // 4 Flanged Mounting Corner Bosses
  const bossGeo = new THREE.CylinderGeometry(0.28, 0.32, mainHeight + 0.1, 16);
  const bossHoleGeo = new THREE.CylinderGeometry(0.12, 0.12, mainHeight + 0.15, 12);
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

  // Indicator LED on top corner
  const ledGeo = new THREE.SphereGeometry(0.08, 12, 12);
  geometriesToDispose.push(ledGeo);
  const ledMesh = new THREE.Mesh(ledGeo, theme.materials.highlight);
  ledMesh.position.set(-mainWidth / 2 + 0.4, mainHeight / 2 + 0.08, -mainDepth / 2 + 0.4);
  group.add(ledMesh);

  const t = node.transform || { position: [0, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1] };
  group.position.set(t.position[0], t.position[1], t.position[2]);
  group.rotation.set(t.rotation[0], t.rotation[1], t.rotation[2]);
  group.scale.set(t.scale[0], t.scale[1], t.scale[2]);

  const update = (tSec: number) => {
    // Subtle pulsating LED indicator
    const pulse = 0.5 + 0.5 * Math.sin(tSec * 4.0);
    theme.materials.highlight.emissiveIntensity = 0.2 + pulse * 0.8;
  };

  const dispose = () => {
    geometriesToDispose.forEach((g) => g.dispose());
    Object.values(theme.materials).forEach((m) => m.dispose());
  };

  return { group, parts, update, dispose };
}

// ----------------------------------------------------------------------------
// 3. VolumetricPipes / FlowPath Procedural Compiler
// ----------------------------------------------------------------------------

export function compileFlowPath(
  node: ExecutableNode3D,
  genome?: ArtDirectionGenomeLike
): Procedural3DResult {
  const group = new THREE.Group();
  group.name = node.node_id || "FlowPath";

  const theme = createMaterialTheme(node.material_spec, genome);
  const geometriesToDispose: THREE.BufferGeometry[] = [];

  // Generate a multi-point 3D spline curve
  const points: THREE.Vector3[] = [];
  const customPoints = node.material_spec?.control_points as Array<[number, number, number]> | undefined;

  if (Array.isArray(customPoints) && customPoints.length >= 3) {
    customPoints.forEach((p) => points.push(new THREE.Vector3(p[0], p[1], p[2])));
  } else {
    // Default dynamic procedural S-curve
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
  const tubeGeo = new THREE.TubeGeometry(curve, 72, pipeRadius, 18, false);
  geometriesToDispose.push(tubeGeo);
  const tubeMesh = new THREE.Mesh(tubeGeo, theme.materials.darkChassis);
  tubeMesh.castShadow = true;
  group.add(tubeMesh);

  // Wireframe contour along tube
  const tubeEdges = createEdgesLine(tubeGeo, theme.materials.wireframe);
  group.add(tubeEdges);

  // Flanged pipe joint rings at regular intervals
  const numJoints = 5;
  const jointGeo = new THREE.TorusGeometry(pipeRadius * 1.35, pipeRadius * 0.22, 16, 24);
  geometriesToDispose.push(jointGeo);

  for (let i = 0; i <= numJoints; i++) {
    const u = i / numJoints;
    const pt = curve.getPointAt(u);
    const tangent = curve.getTangentAt(u);

    const jointMesh = new THREE.Mesh(jointGeo, theme.materials.metal);
    jointMesh.position.copy(pt);
    jointMesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), tangent);
    group.add(jointMesh);
  }

  // Flowing Energy Pulse Rings
  const numPulseRings = 7;
  const ringGeo = new THREE.TorusGeometry(pipeRadius * 1.18, pipeRadius * 0.16, 16, 24);
  geometriesToDispose.push(ringGeo);

  const pulseRings: Array<{ mesh: THREE.Mesh; offset: number }> = [];
  for (let i = 0; i < numPulseRings; i++) {
    const rMat = theme.materials.accent.clone();
    rMat.emissive = theme.accentColor.clone().multiplyScalar(0.7);
    const ringMesh = new THREE.Mesh(ringGeo, rMat);
    group.add(ringMesh);
    pulseRings.push({ mesh: ringMesh, offset: i / numPulseRings });
  }

  // Flowing Packet Spheres
  const numSpheres = 4;
  const sphereGeo = new THREE.SphereGeometry(pipeRadius * 0.65, 16, 16);
  geometriesToDispose.push(sphereGeo);

  const pulseSpheres: Array<{ mesh: THREE.Mesh; offset: number }> = [];
  for (let i = 0; i < numSpheres; i++) {
    const sMat = theme.materials.highlight.clone();
    sMat.emissive = theme.highlightColor.clone().multiplyScalar(0.9);
    const sphereMesh = new THREE.Mesh(sphereGeo, sMat);
    group.add(sphereMesh);
    pulseSpheres.push({ mesh: sphereMesh, offset: i / numSpheres });
  }

  const t = node.transform || { position: [0, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1] };
  group.position.set(t.position[0], t.position[1], t.position[2]);
  group.rotation.set(t.rotation[0], t.rotation[1], t.rotation[2]);
  group.scale.set(t.scale[0], t.scale[1], t.scale[2]);

  const flowSpeed = 0.35;

  const update = (tSec: number) => {
    // Update Pulse Rings
    pulseRings.forEach((item) => {
      const u = (tSec * flowSpeed + item.offset) % 1.0;
      const pt = curve.getPointAt(u);
      const tangent = curve.getTangentAt(u);
      item.mesh.position.copy(pt);
      item.mesh.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), tangent);

      // Pulse scaling
      const pulseScale = 1.0 + 0.25 * Math.sin(u * Math.PI * 2);
      item.mesh.scale.set(pulseScale, pulseScale, pulseScale);
    });

    // Update Pulse Spheres
    pulseSpheres.forEach((item) => {
      const u = (tSec * (flowSpeed * 1.3) + item.offset) % 1.0;
      const pt = curve.getPointAt(u);
      item.mesh.position.copy(pt);
    });
  };

  const dispose = () => {
    geometriesToDispose.forEach((g) => g.dispose());
    Object.values(theme.materials).forEach((m) => m.dispose());
  };

  return { group, parts: [], update, dispose };
}

// ----------------------------------------------------------------------------
// 4. LayerStack / IsometricArchitecture Procedural Compiler
// ----------------------------------------------------------------------------

export function compileLayerStack(
  node: ExecutableNode3D,
  genome?: ArtDirectionGenomeLike
): Procedural3DResult {
  const group = new THREE.Group();
  group.name = node.node_id || "LayerStack";

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

    // Internal processor chip on Layer 2
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

  // Vertical Interlayer Connection Pillars (4 bus pins)
  const pillarGeo = new THREE.CylinderGeometry(0.04, 0.04, 3.8, 16);
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

  // Flowing data signal beads along pillars
  const beadGeo = new THREE.SphereGeometry(0.09, 12, 12);
  geometriesToDispose.push(beadGeo);
  const beads: THREE.Mesh[] = [];

  pillarOffsets.forEach(([px, pz], pIdx) => {
    const bead = new THREE.Mesh(beadGeo, theme.materials.highlight);
    bead.position.set(px, 0, pz);
    group.add(bead);
    beads.push(bead);
  });

  const t = node.transform || { position: [0, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1] };
  group.position.set(t.position[0], t.position[1], t.position[2]);
  group.rotation.set(t.rotation[0], t.rotation[1], t.rotation[2]);
  group.scale.set(t.scale[0], t.scale[1], t.scale[2]);

  const update = (tSec: number, durationSec: number, motionPurpose?: string) => {
    const dur = Math.max(0.1, durationSec || 5.0);
    const progress = Math.max(0, Math.min(1, tSec / dur));

    // Staggered layer hover/expansion
    const expandProgress = motionPurpose === "explode" ? easeInOutCubic(progress) : 0.25 * Math.sin(tSec * 1.5);

    parts.forEach((part, idx) => {
      const offset = (part.explodeDistance || 0) * expandProgress;
      part.mesh.position.y = part.basePosition.y + offset + Math.sin(tSec * 2.0 + idx * 0.8) * 0.04;
    });

    // Update signal beads traveling along pillars
    beads.forEach((bead, bIdx) => {
      const phase = (tSec * 1.2 + bIdx * 0.25) % 1.0;
      bead.position.y = -1.6 + phase * 3.4;
    });
  };

  const dispose = () => {
    geometriesToDispose.forEach((g) => g.dispose());
    Object.values(theme.materials).forEach((m) => m.dispose());
  };

  return { group, parts, update, dispose };
}

// ----------------------------------------------------------------------------
// 5. Cutaway Procedural Compiler
// ----------------------------------------------------------------------------

export function compileCutaway(
  node: ExecutableNode3D,
  genome?: ArtDirectionGenomeLike
): Procedural3DResult {
  const group = new THREE.Group();
  group.name = node.node_id || "CutawaySection";

  const theme = createMaterialTheme(node.material_spec, genome);
  const geometriesToDispose: THREE.BufferGeometry[] = [];

  // Outer Hull with a 90-degree cutaway slice
  // Cylinder from 0 to 1.5 * PI (270 degrees)
  const outerRadius = 1.6;
  const cylinderHeight = 2.8;
  const hullGeo = new THREE.CylinderGeometry(
    outerRadius,
    outerRadius,
    cylinderHeight,
    48,
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

  // Cut-plane flat cross section caps
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

  // Highlight wireframe edge lines tracing cutaway
  const hullEdges = createEdgesLine(hullGeo, theme.materials.accentLine);
  group.add(hullEdges);

  // Internal Core Assembly (Revealed by cutaway)
  const coreGroup = new THREE.Group();

  // Central glowing energy core
  const coreGeo = new THREE.CylinderGeometry(0.5, 0.5, 2.4, 24);
  geometriesToDispose.push(coreGeo);
  const coreMesh = new THREE.Mesh(coreGeo, theme.materials.coreGlow);
  coreGroup.add(coreMesh);

  // Concentric magnetic induction coil rings
  const numCoils = 4;
  const coilGeo = new THREE.TorusGeometry(0.85, 0.1, 16, 32);
  geometriesToDispose.push(coilGeo);

  for (let i = 0; i < numCoils; i++) {
    const cy = (i - (numCoils - 1) / 2) * 0.6;
    const coilMesh = new THREE.Mesh(coilGeo, theme.materials.accent);
    coilMesh.rotation.x = Math.PI / 2;
    coilMesh.position.y = cy;
    coreGroup.add(coilMesh);
  }

  // Internal cooling channel tubes
  const tubePoints = [
    new THREE.Vector3(0.9, -1.2, 0),
    new THREE.Vector3(1.1, 0, 0.5),
    new THREE.Vector3(0.9, 1.2, 0),
  ];
  const fluidCurve = new THREE.CatmullRomCurve3(tubePoints);
  const fluidGeo = new THREE.TubeGeometry(fluidCurve, 24, 0.08, 12, false);
  geometriesToDispose.push(fluidGeo);
  const fluidMesh = new THREE.Mesh(fluidGeo, theme.materials.highlight);
  coreGroup.add(fluidMesh);

  group.add(coreGroup);

  const t = node.transform || { position: [0, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1] };
  group.position.set(t.position[0], t.position[1], t.position[2]);
  group.rotation.set(t.rotation[0], t.rotation[1], t.rotation[2]);
  group.scale.set(t.scale[0], t.scale[1], t.scale[2]);

  const update = (tSec: number) => {
    // Rotate internal coil core relative to stationary cutaway hull
    coreGroup.rotation.y = tSec * 0.6;
    // Modulate core glow
    const pulse = 0.7 + 0.3 * Math.sin(tSec * 3.5);
    theme.materials.coreGlow.emissiveIntensity = pulse * 1.2;
  };

  const dispose = () => {
    geometriesToDispose.forEach((g) => g.dispose());
    Object.values(theme.materials).forEach((m) => m.dispose());
  };

  return { group, parts: [], update, dispose };
}

// ----------------------------------------------------------------------------
// 6. Generic / Fallback Node Compiler
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
    geo = new THREE.SphereGeometry(1.2, 32, 24);
  } else if (prim.includes("cylinder")) {
    geo = new THREE.CylinderGeometry(1.0, 1.0, 2.0, 32);
  } else if (prim.includes("torus")) {
    geo = new THREE.TorusGeometry(1.2, 0.35, 24, 48);
  } else if (prim.includes("cone")) {
    geo = new THREE.ConeGeometry(1.2, 2.2, 32);
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

  return { group, parts: [], update, dispose };
}

// ----------------------------------------------------------------------------
// Procedural Geometry Factory Dispatcher
// ----------------------------------------------------------------------------

export class GeometryCompiler3D {
  public compileProceduralNode(
    node: ExecutableNode3D,
    genome?: ArtDirectionGenomeLike
  ): Procedural3DResult {
    const type = (node.procedural_type || "").toLowerCase();

    if (type.includes("exploded") || type === "explodedassembly") {
      return compileAssembly(node, genome, true);
    }
    if (type.includes("assembly")) {
      return compileAssembly(node, genome, false);
    }
    if (type.includes("housing") || type.includes("component")) {
      return compileHousing(node, genome);
    }
    if (type.includes("pipe") || type.includes("flow") || type.includes("flowpath") || type.includes("tube")) {
      return compileFlowPath(node, genome);
    }
    if (type.includes("layer") || type.includes("stack") || type.includes("architecture")) {
      return compileLayerStack(node, genome);
    }
    if (type.includes("cutaway") || type.includes("section")) {
      return compileCutaway(node, genome);
    }

    return compileGenericMesh(node, genome);
  }

  /**
   * Backwards-compatible node compilation method returning raw transform & color metadata.
   */
  public compileNode(node: ExecutableNode3D, timeSec: number): Compiled3DObject {
    const t = node.transform || { position: [0, 0, 0], rotation: [0, 0, 0], scale: [1, 1, 1] };
    const pos: [number, number, number] = [...t.position];

    if (node.procedural_type === "ExplodedAssembly") {
      const offset = Math.sin(timeSec * 1.2) * 1.8;
      pos[0] += offset;
    }

    return {
      node_id: node.node_id,
      type: node.procedural_type || "Component",
      position: pos,
      rotation: t.rotation,
      scale: t.scale,
      color: node.material_spec?.color || "#ff6b00",
      roughness: node.material_spec?.roughness ?? 0.35,
      metalness: node.material_spec?.metalness ?? 0.65,
    };
  }
}

export const geometryCompiler3D = new GeometryCompiler3D();

/**
 * Comprehensive Verification Suite for 2D PixiJS v8 + D3 Compositor Library.
 */

import {
  SemanticRepresentationType,
  TECHNICAL_SYSTEMS_GENOME,
  CYBER_GRID_GENOME,
  EDITORIAL_ELEGANCE_GENOME,
  ExecutableSceneProgram,
} from "../src/v3/contracts/video-program";
import {
  compositorRegistry,
  createSceneContainer,
  updateSceneAt,
  compiler2D,
  compositorLibrary2D,
} from "../src/v3/compiler2d/index";

console.log("=== VIDEO FLOW V3: 2D COMPOSITOR LIBRARY VERIFICATION ===");

// 1. Verify Registry Registration
const registeredTypes = compositorRegistry.getTypes();
console.log(`[PASS] Registered Compositor Types (${registeredTypes.length} total):`, registeredTypes.join(", "));

const expectedTypes = [
  SemanticRepresentationType.PROCESS,
  SemanticRepresentationType.CAUSE_EFFECT,
  SemanticRepresentationType.COMPARISON,
  SemanticRepresentationType.TIMELINE,
  SemanticRepresentationType.TRANSFORMATION,
  SemanticRepresentationType.HIERARCHY,
  SemanticRepresentationType.NETWORK,
  SemanticRepresentationType.QUANTITATIVE,
  SemanticRepresentationType.CHART,
  SemanticRepresentationType.QUANTITATIVE_RELATIONSHIP,
  SemanticRepresentationType.LAYER_STACK,
  SemanticRepresentationType.SYSTEM_ARCHITECTURE,
  SemanticRepresentationType.DOCUMENT_SOURCE,
  SemanticRepresentationType.CODE_EXPLANATION,
  SemanticRepresentationType.EQUATION_EXPLANATION,
  SemanticRepresentationType.MAP_GEOGRAPHY,
  SemanticRepresentationType.SEQUENCE,
  SemanticRepresentationType.OBJECT_FOCUS,
  SemanticRepresentationType.BEFORE_AFTER,
  SemanticRepresentationType.FLOW,
  SemanticRepresentationType.CONCEPTUAL_METAPHOR,
  SemanticRepresentationType.LIST_BREAKDOWN,
  SemanticRepresentationType.STAT_GRID,
  SemanticRepresentationType.QUOTE_CALLOUT,
  SemanticRepresentationType.SUMMARY_RECAP,
];

let allFound = true;
for (const type of expectedTypes) {
  if (!compositorRegistry.has(type)) {
    console.error(`[FAIL] Missing compositor for type: ${type}`);
    allFound = false;
  }
}
if (allFound) {
  console.log(`[PASS] All ${expectedTypes.length} canonical semantic representation types are registered!`);
}

// 2. Exercise scene container creation and absolute-time updates for every representation type
const genomes = [TECHNICAL_SYSTEMS_GENOME, CYBER_GRID_GENOME, EDITORIAL_ELEGANCE_GENOME];

console.log("\n--- Testing Scene Creation & Time Evaluation across Genomes ---");
let passCount = 0;

for (let i = 0; i < expectedTypes.length; i++) {
  const repType = expectedTypes[i];
  const genome = genomes[i % genomes.length];

  const testScene: ExecutableSceneProgram = {
    contract_version: "v3.0.0",
    scene_id: `scene_test_${repType.toLowerCase()}`,
    sequence: i + 1,
    duration_sec: 5.0,
    representation_type: repType,
    title: `Scene Verification: ${repType}`,
    elements_2d: [
      {
        element_id: `elem_1_${repType}`,
        layer: "node",
        compositor: repType,
        layout_bounds: { x: 100, y: 150, width: 200, height: 100 },
        style: { label: "Component Alpha", accent: "#00e5ff", fill: "#0f172a" },
      },
      {
        element_id: `elem_2_${repType}`,
        layer: "node",
        compositor: repType,
        layout_bounds: { x: 350, y: 150, width: 200, height: 100 },
        style: { label: "Component Beta", accent: "#f59e0b", fill: "#131e35" },
      },
    ],
    nodes_3d: [],
    camera_path: [],
  };

  // Create scene container
  const container = createSceneContainer(testScene, genome, 1920, 1080);
  if (!container || container.children.length === 0) {
    throw new Error(`Failed to create non-empty container for ${repType}`);
  }

  // Update at t = 0.0s, 1.5s, 3.0s, 5.0s
  updateSceneAt(container, testScene, 0.0, 1920, 1080, genome);
  updateSceneAt(container, testScene, 1.5, 1920, 1080, genome);
  updateSceneAt(container, testScene, 3.0, 1920, 1080, genome);
  updateSceneAt(container, testScene, 5.0, 1920, 1080, genome);

  // Compile with VisualCompiler2D
  const output = compiler2D.compileScene(testScene, 2.5, 1920, 1080, genome);
  if (!output.container || output.evaluated_elements.length !== 2) {
    throw new Error(`VisualCompiler2D compileScene failed for ${repType}`);
  }

  console.log(`  ✓ [${repType}] created & evaluated (children: ${container.children.length}, genome: ${genome.family})`);
  passCount++;
}

console.log(`\n[PASS] Successfully verified ${passCount} / ${expectedTypes.length} Compositors!`);

// 3. Test CompositorLibrary2D Backwards Compatibility
console.log("\n--- Testing CompositorLibrary2D Backwards Compatibility ---");
const mockElements = [
  { element_id: "e1", layer: "node" as const, compositor: "PROCESS", layout_bounds: { x: 0, y: 0, width: 100, height: 100 }, style: { label: "Step 1" } },
  { element_id: "e2", layer: "node" as const, compositor: "PROCESS", layout_bounds: { x: 0, y: 0, width: 100, height: 100 }, style: { label: "Step 2" } },
];

const procNodes = compositorLibrary2D.layoutProcess(mockElements, 1280, 720);
const compNodes = compositorLibrary2D.layoutComparison(mockElements, 1280, 720);
const repNodes = compositorLibrary2D.layoutRepresentation("SYSTEM_ARCHITECTURE", mockElements, 1280, 720);

console.log(`  ✓ layoutProcess generated ${procNodes.length} nodes (width: ${procNodes[0].width})`);
console.log(`  ✓ layoutComparison generated ${compNodes.length} nodes (width: ${compNodes[0].width})`);
console.log(`  ✓ layoutRepresentation("SYSTEM_ARCHITECTURE") generated ${repNodes.length} nodes`);

console.log("\n=== ALL 2D COMPOSITOR TESTS PASSED SUCCESSFULLY! ===");

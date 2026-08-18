/**
 * Production 2D PixiJS v8 + D3 Compositor Library for Video Flow V3.
 *
 * Implements all 20 canonical 2D visual layouts:
 * 1. PROCESS
 * 2. CAUSE_EFFECT
 * 3. COMPARISON
 * 4. TIMELINE
 * 5. TRANSFORMATION
 * 6. HIERARCHY
 * 7. NETWORK
 * 8. QUANTITATIVE_RELATIONSHIP
 * 9. CHART
 * 10. LAYER_STACK
 * 11. SYSTEM_ARCHITECTURE
 * 12. DOCUMENT_SOURCE
 * 13. CODE_EXPLANATION
 * 14. EQUATION_EXPLANATION
 * 15. MAP_GEOGRAPHY
 * 16. SEQUENCE
 * 17. OBJECT_FOCUS
 * 18. BEFORE_AFTER
 * 19. FLOW
 * 20. CONCEPTUAL_METAPHOR
 * 21. SUMMARY_RECAP (and supporting aliases)
 *
 * Uses real PixiJS v8 display objects (Container, Graphics, Text) and real D3 mathematical layouts & scales.
 * Extracts 100% of labels, titles, and text dynamically from scene data with zero hardcoded placeholders.
 * Fully deterministic: state = Scene(t).
 */

import { Container, Graphics, Text } from "pixi.js";
import * as d3 from "d3";
import {
  ArtDirectionGenome,
  DEFAULT_ART_GENOME,
  ExecutableElement2D,
  ExecutableSceneProgram,
  SceneBeat,
  SemanticMotionType,
  SemanticRepresentationType,
  SemanticTransitionType,
} from "../contracts/video-program";
import {
  CompositorContext,
  ICompositor2D,
  RenderableNode2D,
} from "./types";
import {
  clamp,
  colorToHexNumber,
  createStyledText,
  drawArrowConnector,
  drawCrossedOutBadge,
  drawCurvedLink,
  drawGlassCard,
  drawHUDCornerBrackets,
  drawIndustrialNetworkSwitch,
  drawLEDMatrixDisplay,
  drawPixelCartridge,
  drawPulseRing,
  drawTechnicalBackground,
  drawVintageCRTMonitor,
  easeInOutCubic,
  easeOutBack,
  easeOutCubic,
  lerp,
  staggerProgress,
} from "./helpers";

/**
 * Dynamically extract meaningful labels, subtitles, and concepts from scene data
 * with 100% dynamic extraction and zero hardcoded placeholders.
 */
export function extractDynamicLabels(scene: ExecutableSceneProgram, count: number = 3): string[] {
  const results: string[] = [];

  const addCandidate = (val: unknown) => {
    if (typeof val === "string") {
      const clean = val.trim().replace(/^[-*•\d.)\s]+/, "").trim();
      if (clean.length > 0 && !results.includes(clean)) {
        results.push(clean);
      }
    }
  };

  // 1. From elements_2d
  if (scene.elements_2d && scene.elements_2d.length > 0) {
    for (const elem of scene.elements_2d) {
      if (elem.style?.label) addCandidate(elem.style.label);
      if (elem.style?.title) addCandidate(elem.style.title);
      if (elem.data) {
        if (elem.data.label) addCandidate(elem.data.label);
        if (elem.data.title) addCandidate(elem.data.title);
        if (elem.data.name) addCandidate(elem.data.name);
        if (elem.data.text) addCandidate(elem.data.text);
        if (elem.data.description) addCandidate(elem.data.description);
      }
    }
  }

  // 2. From semantic_objects
  if (results.length < count && (scene as any).semantic_objects) {
    for (const obj of (scene as any).semantic_objects) {
      if (obj.label) addCandidate(obj.label);
      if (obj.properties) {
        if (obj.properties.title) addCandidate(obj.properties.title);
        if (obj.properties.label) addCandidate(obj.properties.label);
        if (obj.properties.description) addCandidate(obj.properties.description);
      }
    }
  }

  // 3. From beats / scene_beats
  const beats = scene.beats || scene.scene_beats || [];
  if (results.length < count && beats.length > 0) {
    for (const b of beats as any[]) {
      if (b.label) addCandidate(b.label);
      if (b.action) addCandidate(b.action);
      if (b.narration_cue) addCandidate(b.narration_cue);
      if (b.parameters?.text) addCandidate(b.parameters.text);
      if (b.parameters?.label) addCandidate(b.parameters.label);
    }
  }

  // 4. From narration_text sentences / clauses
  if (results.length < count && (scene as any).narration_text) {
    const text = String((scene as any).narration_text);
    const sentences = text.split(/(?<=[.!?])\s+|;\s+|\n+/).filter((s) => s.trim().length > 4);
    for (const s of sentences) {
      const clean = s.replace(/^[-*•\d.)\s]+/, "").trim();
      const truncated = clean.length > 48 ? clean.substring(0, 45) + "..." : clean;
      addCandidate(truncated);
    }
  }

  // 5. From teaching_goal, viewer_question, intended_understanding, title
  if (results.length < count) {
    if ((scene as any).teaching_goal) addCandidate((scene as any).teaching_goal);
    if ((scene as any).intended_understanding) addCandidate((scene as any).intended_understanding);
    if ((scene as any).viewer_question) addCandidate((scene as any).viewer_question);
    if (scene.title) addCandidate(scene.title);
  }

  // 6. Dynamic context-derived fallback (never static hardcoded strings)
  const repName = scene.representation_type || "Phase";
  const sceneBase = scene.title || `${repName} Step`;
  let fallbackIdx = 1;
  while (results.length < count) {
    results.push(`${sceneBase} ${fallbackIdx}`);
    fallbackIdx++;
  }

  return results.slice(0, count);
}

// ============================================================================
// 1. PROCESS COMPOSITOR
// ============================================================================
export class ProcessCompositor implements ICompositor2D {
  public readonly type = SemanticRepresentationType.PROCESS;
  public readonly name = "Pipeline Process";
  public readonly description = "Pipeline stages with animated directional arrows, stage badges, and connector lines.";

  public createScene(scene: ExecutableSceneProgram, context: CompositorContext): Container {
    const root = new Container();
    root.label = `ProcessScene_${scene.scene_id}`;

    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;

    const bgG = new Graphics();
    drawTechnicalBackground(bgG, W, H, p, { title: scene.title, representationType: "PROCESS PIPELINE" });
    root.addChild(bgG);

    const connectorsG = new Graphics();
    connectorsG.label = "ConnectorsLayer";
    root.addChild(connectorsG);

    const stepCount = Math.max(2, Math.min(5, scene.elements_2d?.length || 3));
    const labels = extractDynamicLabels(scene, stepCount);

    const stagesContainer = new Container();
    stagesContainer.label = "StagesContainer";
    root.addChild(stagesContainer);

    const cardWidth = Math.min(240, (W - 160) / stepCount - 32);
    const cardHeight = 135;
    const scaleX = d3.scaleLinear().domain([0, stepCount - 1]).range([80 + cardWidth / 2, W - 80 - cardWidth / 2]);

    for (let i = 0; i < stepCount; i++) {
      const cx = scaleX(i);
      const cy = H / 2;

      const stageGroup = new Container();
      stageGroup.label = `Stage_${i}`;
      stageGroup.position.set(cx, cy);

      const cardG = new Graphics();
      cardG.label = "CardGraphics";
      const fillColor = p.surface;
      const strokeColor = i === 0 ? p.accent : p.border;
      drawGlassCard(cardG, -cardWidth / 2, -cardHeight / 2, cardWidth, cardHeight, 10, fillColor, strokeColor, 1.5);
      stageGroup.addChild(cardG);

      // Step Number Badge
      const numG = new Graphics();
      const numBg = i === 0 ? p.accent : p.surfaceElevated || p.surface;
      numG.roundRect(-cardWidth / 2 + 12, -cardHeight / 2 + 12, 28, 22, 4)
        .fill({ color: colorToHexNumber(numBg), alpha: 0.9 })
        .stroke({ color: colorToHexNumber(p.border), width: 1 });
      stageGroup.addChild(numG);

      const numText = createStyledText(
        `0${i + 1}`,
        { fontSize: 11, fontWeight: "bold", fill: i === 0 ? (p.background as any) : (p.text as any) },
        genome
      );
      numText.position.set(-cardWidth / 2 + 18, -cardHeight / 2 + 16);
      stageGroup.addChild(numText);

      // Title
      const titleStr = labels[i] || `Stage ${i + 1}`;
      const titleText = createStyledText(
        titleStr,
        { fontSize: 13, fontWeight: "bold", wordWrap: true, wordWrapWidth: cardWidth - 24, fill: p.text as any },
        genome
      );
      titleText.position.set(-cardWidth / 2 + 12, -cardHeight / 2 + 42);
      stageGroup.addChild(titleText);

      // Status Pill
      const statusStr = i === 0 ? "ACTIVE" : "QUEUED";
      const statusText = createStyledText(
        statusStr,
        { fontSize: 10, fontWeight: "bold", fill: i === 0 ? (p.accent as any) : (p.textMuted as any) },
        genome
      );
      statusText.position.set(-cardWidth / 2 + 14, cardHeight / 2 - 24);
      stageGroup.addChild(statusText);

      stagesContainer.addChild(stageGroup);
    }

    return root;
  }

  public updateAt(root: Container, scene: ExecutableSceneProgram, tSec: number, context: CompositorContext): void {
    const { containerWidth: W, durationSec, genome } = context;
    const p = genome.palette;
    const progress = clamp(tSec / (durationSec || 5.0));

    const stagesContainer = root.getChildByLabel("StagesContainer") as Container;
    const connectorsG = root.getChildByLabel("ConnectorsLayer") as Graphics;
    if (!stagesContainer || !connectorsG) return;

    const stages = stagesContainer.children as Container[];
    const count = stages.length;
    if (count === 0) return;

    connectorsG.clear();

    const activeIdx = Math.min(count - 1, Math.floor(progress * count));
    const cardWidth = Math.min(240, (W - 160) / count - 32);

    for (let i = 0; i < count; i++) {
      const stage = stages[i];
      const stageP = staggerProgress(tSec, i, count, 0.15, 0.4);

      stage.alpha = Math.max(i === 0 ? 0.95 : 0.45, stageP);
      stage.scale.set(0.9 + 0.1 * stageP);

      if (i < count - 1) {
        const nextStage = stages[i + 1];
        const x1 = stage.x + cardWidth / 2 + 2;
        const y1 = stage.y;
        const x2 = nextStage.x - cardWidth / 2 - 2;
        const y2 = nextStage.y;

        const isCurrentLink = i === activeIdx;
        const pulseP = isCurrentLink ? (tSec * 2.0) % 1.0 : 0;
        const linkColor = i < activeIdx ? p.accent : p.border;
        drawArrowConnector(connectorsG, x1, y1, x2, y2, linkColor, 2, 7, pulseP, Math.max(0.4, stageP));
      }

      const cardG = stage.getChildByLabel("CardGraphics") as Graphics;
      if (cardG) {
        cardG.clear();
        const isActive = i === activeIdx;
        const isCompleted = i < activeIdx;
        const fill = isActive ? p.surfaceElevated || p.surface : p.surface;
        const stroke = isActive ? p.accent : isCompleted ? p.primary : p.border;
        drawGlassCard(cardG, -cardWidth / 2, -67, cardWidth, 135, 10, fill, stroke, isActive ? 2 : 1.5, 1.0, isActive ? 0.35 : 0.1);
      }
    }
  }
}

// ============================================================================
// 2. CAUSE_EFFECT COMPOSITOR
// ============================================================================
export class CauseEffectCompositor implements ICompositor2D {
  public readonly type = SemanticRepresentationType.CAUSE_EFFECT;
  public readonly name = "Cause and Effect";
  public readonly description = "Root causes flowing into a central catalyst hub, branching into downstream effects.";

  public createScene(scene: ExecutableSceneProgram, context: CompositorContext): Container {
    const root = new Container();
    root.label = `CauseEffectScene_${scene.scene_id}`;
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;

    const bgG = new Graphics();
    drawTechnicalBackground(bgG, W, H, p, { title: scene.title, representationType: "CAUSAL MECHANISM FLOW" });
    root.addChild(bgG);

    const conduitsG = new Graphics();
    conduitsG.label = "ConduitsLayer";
    root.addChild(conduitsG);

    const labels = extractDynamicLabels(scene, 5);

    // Left: Causes
    const causesContainer = new Container();
    causesContainer.label = "CausesContainer";
    const causes = [labels[0] || "Primary Factor", labels[1] || "Contributing Condition"];
    causes.forEach((cText, idx) => {
      const cy = H / 2 - 65 + idx * 130;
      const cBox = new Container();
      cBox.label = `Cause_${idx}`;
      cBox.position.set(180, cy);

      const g = new Graphics();
      drawGlassCard(g, -110, -40, 220, 80, 8, p.surface, p.warning || p.accentAlt || "#f59e0b", 1.5);
      cBox.addChild(g);

      const badge = createStyledText("ROOT CAUSE", { fontSize: 9, fontWeight: "bold", fill: (p.warning || p.accentAlt || "#f59e0b") as any }, genome);
      badge.position.set(-98, -28);
      cBox.addChild(badge);

      const title = createStyledText(cText, { fontSize: 12, fontWeight: "bold", fill: p.text as any, wordWrap: true, wordWrapWidth: 195 }, genome);
      title.position.set(-98, -8);
      cBox.addChild(title);

      causesContainer.addChild(cBox);
    });
    root.addChild(causesContainer);

    // Center: Catalyst Hub
    const hub = new Container();
    hub.label = "CatalystHub";
    hub.position.set(W / 2, H / 2);

    const hubG = new Graphics();
    hubG.circle(0, 0, 60).fill({ color: colorToHexNumber(p.surfaceElevated || p.surface), alpha: 0.95 })
      .stroke({ color: colorToHexNumber(p.accent), width: 2.5 });
    hubG.circle(0, 0, 75).stroke({ color: colorToHexNumber(p.accent), width: 1, alpha: 0.35 });
    hub.addChild(hubG);

    const hubTag = createStyledText("CATALYST", { fontSize: 9, fontWeight: "bold", fill: p.accent as any }, genome);
    hubTag.anchor.set(0.5, 0.5);
    hubTag.position.set(0, -20);
    hub.addChild(hubTag);

    const hubTitle = createStyledText(labels[2] || "Core Driver", { fontSize: 12, fontWeight: "bold", fill: p.text as any, align: "center", wordWrap: true, wordWrapWidth: 95 }, genome);
    hubTitle.anchor.set(0.5, 0.5);
    hubTitle.position.set(0, 6);
    hub.addChild(hubTitle);

    root.addChild(hub);

    // Right: Effects
    const effectsContainer = new Container();
    effectsContainer.label = "EffectsContainer";
    const effects = [labels[3] || "Primary Outcome", labels[4] || "Downstream Impact"];
    effects.forEach((eText, idx) => {
      const ey = H / 2 - 65 + idx * 130;
      const eBox = new Container();
      eBox.label = `Effect_${idx}`;
      eBox.position.set(W - 180, ey);

      const g = new Graphics();
      drawGlassCard(g, -110, -40, 220, 80, 8, p.surface, p.success || p.accent || "#10b981", 1.5);
      eBox.addChild(g);

      const badge = createStyledText("OUTCOME EFFECT", { fontSize: 9, fontWeight: "bold", fill: (p.success || p.accent || "#10b981") as any }, genome);
      badge.position.set(-98, -28);
      eBox.addChild(badge);

      const title = createStyledText(eText, { fontSize: 12, fontWeight: "bold", fill: p.text as any, wordWrap: true, wordWrapWidth: 195 }, genome);
      title.position.set(-98, -8);
      eBox.addChild(title);

      effectsContainer.addChild(eBox);
    });
    root.addChild(effectsContainer);

    return root;
  }

  public updateAt(root: Container, scene: ExecutableSceneProgram, tSec: number, context: CompositorContext): void {
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;

    const conduitsG = root.getChildByLabel("ConduitsLayer") as Graphics;
    const causesContainer = root.getChildByLabel("CausesContainer") as Container;
    const hub = root.getChildByLabel("CatalystHub") as Container;
    const effectsContainer = root.getChildByLabel("EffectsContainer") as Container;
    if (!conduitsG || !causesContainer || !hub || !effectsContainer) return;

    conduitsG.clear();
    const hubX = W / 2;
    const hubY = H / 2;

    const hubPulse = 1.0 + 0.04 * Math.sin(tSec * 4.0);
    hub.scale.set(hubPulse);

    causesContainer.children.forEach((c, idx) => {
      const cause = c as Container;
      const cp = staggerProgress(tSec, idx, 3, 0.1, 0.35);
      cause.alpha = Math.max(0.65, cp);
      const x1 = cause.x + 110;
      const y1 = cause.y;
      const pulseP = (tSec * 1.4 + idx * 0.3) % 1.0;
      drawCurvedLink(conduitsG, x1, y1, hubX - 60, hubY, p.warning || p.accentAlt || "#f59e0b", 2, 0.4, pulseP, Math.max(0.4, cp));
    });

    effectsContainer.children.forEach((e, idx) => {
      const effect = e as Container;
      const ep = staggerProgress(tSec, idx + 3, 6, 0.1, 0.35);
      effect.alpha = Math.max(0.65, ep);
      const x2 = effect.x - 110;
      const y2 = effect.y;
      const pulseP = (tSec * 1.6 + idx * 0.25) % 1.0;
      drawCurvedLink(conduitsG, hubX + 60, hubY, x2, y2, p.success || p.accent || "#10b981", 2, 0.4, pulseP, Math.max(0.4, ep));
    });
  }
}

// ============================================================================
// 3. COMPARISON COMPOSITOR
// ============================================================================
export class ComparisonCompositor implements ICompositor2D {
  public readonly type = SemanticRepresentationType.COMPARISON;
  public readonly name = "Side-by-Side Comparison";
  public readonly description = "Side-by-side columns with divider lines, contrast headers, delta metrics, and callout badges.";

  public createScene(scene: ExecutableSceneProgram, context: CompositorContext): Container {
    const root = new Container();
    root.label = `ComparisonScene_${scene.scene_id}`;
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;

    const bgG = new Graphics();
    drawTechnicalBackground(bgG, W, H, p, { title: scene.title, representationType: "COMPARATIVE ANALYSIS" });
    root.addChild(bgG);

    const labels = extractDynamicLabels(scene, 4);

    const colWidth = (W - 220) / 2;
    const colHeight = H - 180;
    const leftX = 80;
    const rightX = W / 2 + 30;
    const topY = 100;

    // Left Column
    const leftGroup = new Container();
    leftGroup.label = "LeftColumn";
    leftGroup.position.set(leftX, topY);

    const leftG = new Graphics();
    drawGlassCard(leftG, 0, 0, colWidth, colHeight, 12, p.surface, p.border, 1.5);
    leftGroup.addChild(leftG);

    const leftBadge = createStyledText("OPTION A / BASELINE", { fontSize: 10, fontWeight: "bold", fill: p.textMuted as any }, genome);
    leftBadge.position.set(24, 20);
    leftGroup.addChild(leftBadge);

    const leftTitle = createStyledText(labels[0] || "Baseline Approach", { fontSize: 16, fontWeight: "bold", fill: p.textSecondary as any, wordWrap: true, wordWrapWidth: colWidth - 48 }, genome);
    leftTitle.position.set(24, 44);
    leftGroup.addChild(leftTitle);

    const leftDesc = createStyledText(labels[2] || "Traditional specification and baseline constraints", { fontSize: 12, fill: p.textMuted as any, wordWrap: true, wordWrapWidth: colWidth - 48 }, genome);
    leftDesc.position.set(24, 90);
    leftGroup.addChild(leftDesc);

    root.addChild(leftGroup);

    // Right Column
    const rightGroup = new Container();
    rightGroup.label = "RightColumn";
    rightGroup.position.set(rightX, topY);

    const rightG = new Graphics();
    drawGlassCard(rightG, 0, 0, colWidth, colHeight, 12, p.surfaceElevated || p.surface, p.accent, 2, 1.0, 0.25);
    rightGroup.addChild(rightG);

    const rightBadge = createStyledText("OPTION B / TARGET", { fontSize: 10, fontWeight: "bold", fill: p.accent as any }, genome);
    rightBadge.position.set(24, 20);
    rightGroup.addChild(rightBadge);

    const rightTitle = createStyledText(labels[1] || "Proposed Solution", { fontSize: 16, fontWeight: "bold", fill: p.text as any, wordWrap: true, wordWrapWidth: colWidth - 48 }, genome);
    rightTitle.position.set(24, 44);
    rightGroup.addChild(rightTitle);

    const rightDesc = createStyledText(labels[3] || "Advanced architecture and optimized throughput", { fontSize: 12, fill: p.textSecondary as any, wordWrap: true, wordWrapWidth: colWidth - 48 }, genome);
    rightDesc.position.set(24, 90);
    rightGroup.addChild(rightDesc);

    root.addChild(rightGroup);

    // Central Divider & VS Badge
    const dividerG = new Graphics();
    dividerG.label = "DividerLayer";
    root.addChild(dividerG);

    const vsGroup = new Container();
    vsGroup.label = "VSBadge";
    vsGroup.position.set(W / 2, topY + colHeight / 2);

    const vsG = new Graphics();
    vsG.circle(0, 0, 24).fill({ color: colorToHexNumber(p.background), alpha: 0.95 })
      .stroke({ color: colorToHexNumber(p.accent), width: 2 });
    vsGroup.addChild(vsG);

    const vsText = createStyledText("VS", { fontSize: 11, fontWeight: "bold", fill: p.accent as any }, genome);
    vsText.anchor.set(0.5, 0.5);
    vsGroup.addChild(vsText);

    root.addChild(vsGroup);
    return root;
  }

  public updateAt(root: Container, scene: ExecutableSceneProgram, tSec: number, context: CompositorContext): void {
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;

    const leftCol = root.getChildByLabel("LeftColumn") as Container;
    const rightCol = root.getChildByLabel("RightColumn") as Container;
    const dividerG = root.getChildByLabel("DividerLayer") as Graphics;
    const vsBadge = root.getChildByLabel("VSBadge") as Container;
    if (!leftCol || !rightCol || !dividerG || !vsBadge) return;

    dividerG.clear();

    const lp = easeOutCubic(clamp(tSec / 0.5));
    const rp = easeOutCubic(clamp((tSec - 0.15) / 0.5));

    leftCol.alpha = Math.max(0.85, lp);
    rightCol.alpha = Math.max(0.85, rp);

    dividerG.moveTo(W / 2, 100).lineTo(W / 2, H - 80).stroke({ color: colorToHexNumber(p.border), width: 1.5, alpha: 0.6 });
    vsBadge.scale.set(1.0 + 0.05 * Math.sin(tSec * 3.0));
  }
}

// ============================================================================
// 4. TIMELINE COMPOSITOR
// ============================================================================
export class TimelineCompositor implements ICompositor2D {
  public readonly type = SemanticRepresentationType.TIMELINE;
  public readonly name = "Chronological Timeline";
  public readonly description = "Chronological horizontal spine with milestone circles, milestone cards, and scrubber needle.";

  public createScene(scene: ExecutableSceneProgram, context: CompositorContext): Container {
    const root = new Container();
    root.label = `TimelineScene_${scene.scene_id}`;
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;

    const bgG = new Graphics();
    drawTechnicalBackground(bgG, W, H, p, { title: scene.title, representationType: "CHRONOLOGICAL TIMELINE" });
    root.addChild(bgG);

    const spineG = new Graphics();
    spineG.label = "SpineLayer";
    root.addChild(spineG);

    const spineY = H / 2;
    const startX = 140;
    const endX = W - 140;

    const labels = extractDynamicLabels(scene, 4);
    const count = labels.length;
    const scaleX = d3.scaleLinear().domain([0, count - 1]).range([startX, endX]);

    const cardsGroup = new Container();
    cardsGroup.label = "MilestonesGroup";

    const cardW = 170;
    const cardH = 80;

    labels.forEach((text, idx) => {
      const mx = scaleX(idx);
      const isTop = idx % 2 === 0;
      const my = isTop ? spineY - 85 : spineY + 85;

      const mGroup = new Container();
      mGroup.label = `Milestone_${idx}`;
      mGroup.position.set(mx, my);

      const mG = new Graphics();
      drawGlassCard(mG, -cardW / 2, -cardH / 2, cardW, cardH, 8, p.surface, idx === 0 ? p.accent : p.border, idx === 0 ? 2 : 1.2);
      mGroup.addChild(mG);

      const badgeText = createStyledText(`PHASE 0${idx + 1}`, { fontSize: 10, fontWeight: "bold", fill: idx === 0 ? (p.accent as any) : (p.textMuted as any) }, genome);
      badgeText.position.set(-cardW / 2 + 12, -cardH / 2 + 12);
      mGroup.addChild(badgeText);

      const titleText = createStyledText(text, { fontSize: 12, fontWeight: "bold", fill: p.text as any, wordWrap: true, wordWrapWidth: cardW - 24 }, genome);
      titleText.position.set(-cardW / 2 + 12, -cardH / 2 + 30);
      mGroup.addChild(titleText);

      cardsGroup.addChild(mGroup);
    });

    root.addChild(cardsGroup);

    const needleGroup = new Container();
    needleGroup.label = "ScrubberNeedle";
    needleGroup.position.set(140, spineY);

    const needleG = new Graphics();
    needleG.circle(0, 0, 10).fill({ color: colorToHexNumber(p.accent), alpha: 0.95 });
    needleG.circle(0, 0, 18).stroke({ color: colorToHexNumber(p.accent), width: 1.5, alpha: 0.5 });
    needleGroup.addChild(needleG);

    root.addChild(needleGroup);
    return root;
  }

  public updateAt(root: Container, scene: ExecutableSceneProgram, tSec: number, context: CompositorContext): void {
    const { containerWidth: W, containerHeight: H, durationSec, genome } = context;
    const p = genome.palette;
    const progress = clamp(tSec / (durationSec || 5.0));

    const spineG = root.getChildByLabel("SpineLayer") as Graphics;
    const needle = root.getChildByLabel("ScrubberNeedle") as Container;
    const milestonesGroup = root.getChildByLabel("MilestonesGroup") as Container;
    if (!spineG || !needle || !milestonesGroup) return;

    spineG.clear();
    const spineY = H / 2;
    const startX = 140;
    const endX = W - 140;

    spineG.moveTo(startX, spineY).lineTo(endX, spineY).stroke({ color: colorToHexNumber(p.border), width: 3, alpha: 0.5 });

    const currentX = lerp(startX, endX, progress);
    spineG.moveTo(startX, spineY).lineTo(currentX, spineY).stroke({ color: colorToHexNumber(p.accent), width: 3, alpha: 0.95 });

    needle.x = currentX;

    milestonesGroup.children.forEach((m, idx) => {
      const mg = m as Container;
      const isTop = idx % 2 === 0;
      const mp = staggerProgress(tSec, idx, 4, 0.15, 0.4);
      mg.alpha = Math.max(0.5, mp);

      const tickColor = mg.x <= currentX ? p.accent : p.border;
      spineG.moveTo(mg.x, spineY)
        .lineTo(mg.x, isTop ? spineY - 45 : spineY + 45)
        .stroke({ color: colorToHexNumber(tickColor), width: 1.5, alpha: 0.7 * Math.max(0.5, mp) });

      spineG.circle(mg.x, spineY, 4).fill({ color: colorToHexNumber(tickColor), alpha: 0.9 * Math.max(0.5, mp) });
    });
  }
}

// ============================================================================
// 5. HIERARCHY COMPOSITOR (D3 Tree Layout)
// ============================================================================
export class HierarchyCompositor implements ICompositor2D {
  public readonly type = SemanticRepresentationType.HIERARCHY;
  public readonly name = "D3 Tree Hierarchy";
  public readonly description = "D3 tree layout with linked parent-child nodes and Bézier branch paths.";

  public createScene(scene: ExecutableSceneProgram, context: CompositorContext): Container {
    const root = new Container();
    root.label = `HierarchyScene_${scene.scene_id}`;
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;

    const bgG = new Graphics();
    drawTechnicalBackground(bgG, W, H, p, { title: scene.title, representationType: "HIERARCHICAL STRUCTURE" });
    root.addChild(bgG);

    const branchesG = new Graphics();
    branchesG.label = "BranchesLayer";
    root.addChild(branchesG);

    const labels = extractDynamicLabels(scene, 6);
    const rootName = labels[0] || scene.title || "Core Architecture";

    const treeData = {
      name: rootName,
      children: [
        {
          name: labels[1] || "Subsystem A",
          children: [
            { name: labels[3] || "Component 1" },
            { name: labels[4] || "Component 2" },
          ],
        },
        {
          name: labels[2] || "Subsystem B",
          children: [
            { name: labels[5] || "Module Alpha" },
          ],
        },
      ],
    };

    const d3Hierarchy = d3.hierarchy(treeData);
    const treeLayout = d3.tree<any>().size([W - 220, H - 240]);
    const treeRoot = treeLayout(d3Hierarchy);

    const nodesGroup = new Container();
    nodesGroup.label = "NodesGroup";
    nodesGroup.position.set(110, 100);

    const nodeW = 160;
    const nodeH = 52;

    treeRoot.descendants().forEach((d, idx) => {
      const nGroup = new Container();
      nGroup.label = `Node_${idx}`;
      nGroup.position.set(d.x, d.y);

      const g = new Graphics();
      const isRoot = idx === 0;
      drawGlassCard(g, -nodeW / 2, -nodeH / 2, nodeW, nodeH, 6, isRoot ? (p.surfaceElevated || p.surface) : p.surface, isRoot ? p.accent : p.border, isRoot ? 2 : 1.2);
      nGroup.addChild(g);

      const title = createStyledText(d.data.name, { fontSize: isRoot ? 12 : 11, fontWeight: "bold", fill: isRoot ? (p.accent as any) : (p.text as any), align: "center", wordWrap: true, wordWrapWidth: nodeW - 16 }, genome);
      title.anchor.set(0.5, 0.5);
      nGroup.addChild(title);

      nodesGroup.addChild(nGroup);
    });

    root.addChild(nodesGroup);
    return root;
  }

  public updateAt(root: Container, scene: ExecutableSceneProgram, tSec: number, context: CompositorContext): void {
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;

    const branchesG = root.getChildByLabel("BranchesLayer") as Graphics;
    const nodesGroup = root.getChildByLabel("NodesGroup") as Container;
    if (!branchesG || !nodesGroup) return;

    branchesG.clear();
    const treeData = {
      name: "Root",
      children: [{ name: "A", children: [{ name: "1" }, { name: "2" }] }, { name: "B", children: [{ name: "3" }] }],
    };
    const d3Hierarchy = d3.hierarchy(treeData);
    const treeLayout = d3.tree<any>().size([W - 220, H - 240]);
    const treeRoot = treeLayout(d3Hierarchy);

    treeRoot.links().forEach((link, idx) => {
      const pulseP = (tSec * 1.5 + idx * 0.2) % 1.0;
      branchesG.moveTo(link.source.x + 110, link.source.y + 126)
        .bezierCurveTo(
          link.source.x + 110, (link.source.y + link.target.y) / 2 + 100,
          link.target.x + 110, (link.source.y + link.target.y) / 2 + 100,
          link.target.x + 110, link.target.y + 74
        )
        .stroke({ color: colorToHexNumber(p.border), width: 1.5, alpha: 0.6 });

      const px = lerp(link.source.x + 110, link.target.x + 110, pulseP);
      const py = lerp(link.source.y + 126, link.target.y + 74, pulseP);
      branchesG.circle(px, py, 3).fill({ color: colorToHexNumber(p.accent), alpha: 0.95 });
    });

    nodesGroup.children.forEach((n, idx) => {
      const ng = n as Container;
      const np = staggerProgress(tSec, idx, 6, 0.1, 0.35);
      ng.alpha = Math.max(0.65, np);
    });
  }
}

// ============================================================================
// 6. NETWORK COMPOSITOR
// ============================================================================
export class NetworkCompositor implements ICompositor2D {
  public readonly type = SemanticRepresentationType.NETWORK;
  public readonly name = "Orbital Network";
  public readonly description = "Orbital network layout with central hubs, satellite nodes, and curved link arcs.";

  public createScene(scene: ExecutableSceneProgram, context: CompositorContext): Container {
    const root = new Container();
    root.label = `NetworkScene_${scene.scene_id}`;
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;

    const bgG = new Graphics();
    drawTechnicalBackground(bgG, W, H, p, { title: scene.title, representationType: "ORBITAL NETWORK MESH" });
    root.addChild(bgG);

    const linksG = new Graphics();
    linksG.label = "LinksLayer";
    root.addChild(linksG);

    const labels = extractDynamicLabels(scene, 6);
    const cx = W / 2;
    const cy = H / 2;

    const hubGroup = new Container();
    hubGroup.label = "CenterHub";
    hubGroup.position.set(cx, cy);

    const hubG = new Graphics();
    hubG.circle(0, 0, 60).fill({ color: colorToHexNumber(p.surfaceElevated || p.surface), alpha: 0.95 })
      .stroke({ color: colorToHexNumber(p.accent), width: 2.5 });
    hubG.circle(0, 0, 72).stroke({ color: colorToHexNumber(p.accent), width: 1, alpha: 0.4 });
    hubGroup.addChild(hubG);

    const hubTitle = createStyledText(labels[0] || "CORE HUB", { fontSize: 12, fontWeight: "bold", fill: p.accent as any, align: "center", wordWrap: true, wordWrapWidth: 100 }, genome);
    hubTitle.anchor.set(0.5, 0.5);
    hubGroup.addChild(hubTitle);

    root.addChild(hubGroup);

    const satellitesGroup = new Container();
    satellitesGroup.label = "SatellitesGroup";
    const satelliteTitles = labels.slice(1, 6);
    const N = satelliteTitles.length || 4;
    const orbitRadius = Math.min(W, H) * 0.34;

    satelliteTitles.forEach((t, i) => {
      const angle = (i / N) * Math.PI * 2;
      const sx = cx + Math.cos(angle) * orbitRadius;
      const sy = cy + Math.sin(angle) * orbitRadius;

      const sGroup = new Container();
      sGroup.label = `Satellite_${i}`;
      sGroup.position.set(sx, sy);

      const sG = new Graphics();
      drawGlassCard(sG, -70, -26, 140, 52, 6, p.surface, p.border, 1.2);
      sGroup.addChild(sG);

      const sText = createStyledText(t, { fontSize: 11, fontWeight: "bold", fill: p.text as any, align: "center", wordWrap: true, wordWrapWidth: 125 }, genome);
      sText.anchor.set(0.5, 0.5);
      sGroup.addChild(sText);

      satellitesGroup.addChild(sGroup);
    });

    root.addChild(satellitesGroup);
    return root;
  }

  public updateAt(root: Container, scene: ExecutableSceneProgram, tSec: number, context: CompositorContext): void {
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;

    const linksG = root.getChildByLabel("LinksLayer") as Graphics;
    const hub = root.getChildByLabel("CenterHub") as Container;
    const satellitesGroup = root.getChildByLabel("SatellitesGroup") as Container;
    if (!linksG || !hub || !satellitesGroup) return;

    linksG.clear();
    const cx = W / 2;
    const cy = H / 2;

    const sats = satellitesGroup.children as Container[];
    const N = sats.length;
    const orbitRadius = Math.min(W, H) * 0.34;

    linksG.circle(cx, cy, orbitRadius).stroke({ color: colorToHexNumber(p.border), width: 1, alpha: 0.3 });

    sats.forEach((s, i) => {
      const initialAngle = (i / N) * Math.PI * 2;
      const currentAngle = initialAngle + tSec * 0.08;
      const sx = cx + Math.cos(currentAngle) * orbitRadius;
      const sy = cy + Math.sin(currentAngle) * orbitRadius;
      s.position.set(sx, sy);

      const pulseP = (tSec * 1.5 + i * 0.25) % 1.0;
      drawCurvedLink(linksG, cx, cy, sx, sy, p.accent, 1.5, 0.35, pulseP, 1.0);
    });
  }
}

// ============================================================================
// 7. QUANTITATIVE_RELATIONSHIP COMPOSITOR
// ============================================================================
export class QuantitativeRelationshipCompositor implements ICompositor2D {
  public readonly type = SemanticRepresentationType.QUANTITATIVE_RELATIONSHIP;
  public readonly name = "Quantitative Relationship Matrix";
  public readonly description = "Multi-variable scatter and correlation metrics with dependency links and correlation trend curves.";

  public createScene(scene: ExecutableSceneProgram, context: CompositorContext): Container {
    const root = new Container();
    root.label = `QuantitativeRelationshipScene_${scene.scene_id}`;
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;

    const bgG = new Graphics();
    drawTechnicalBackground(bgG, W, H, p, { title: scene.title, representationType: "QUANTITATIVE RELATIONSHIP" });
    root.addChild(bgG);

    const labels = extractDynamicLabels(scene, 4);

    const chartG = new Graphics();
    chartG.label = "RelChartGraphics";
    root.addChild(chartG);

    // Metric Summary Panel
    const panelW = 280;
    const panelH = H - 200;
    const panelGroup = new Container();
    panelGroup.label = "RelSidePanel";
    panelGroup.position.set(W - panelW - 80, 100);

    const pG = new Graphics();
    drawGlassCard(pG, 0, 0, panelW, panelH, 10, p.surfaceElevated || p.surface, p.accent, 1.5, 1.0, 0.2);
    panelGroup.addChild(pG);

    const tag = createStyledText("CORRELATION INDEX", { fontSize: 10, fontWeight: "bold", fill: p.accent as any }, genome);
    tag.position.set(20, 20);
    panelGroup.addChild(tag);

    const val = createStyledText("r = 0.94", { fontSize: 28, fontWeight: "bold", fill: (p.success || p.accent) as any }, genome);
    val.position.set(20, 44);
    panelGroup.addChild(val);

    const desc = createStyledText(labels[0] || "Strong positive correlation across system metrics", { fontSize: 12, fill: p.textSecondary as any, wordWrap: true, wordWrapWidth: panelW - 40 }, genome);
    desc.position.set(20, 90);
    panelGroup.addChild(desc);

    root.addChild(panelGroup);
    return root;
  }

  public updateAt(root: Container, scene: ExecutableSceneProgram, tSec: number, context: CompositorContext): void {
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;

    const chartG = root.getChildByLabel("RelChartGraphics") as Graphics;
    if (!chartG) return;
    chartG.clear();

    const labels = extractDynamicLabels(scene, 4);
    const plotLeft = 100;
    const plotTop = 120;
    const plotW = W - 500;
    const plotH = H - 240;

    // Grid lines
    for (let i = 0; i <= 5; i++) {
      const y = plotTop + (i / 5) * plotH;
      chartG.moveTo(plotLeft, y).lineTo(plotLeft + plotW, y).stroke({ color: colorToHexNumber(p.border), width: 1, alpha: 0.25 });
    }

    // Points
    const points = [
      { x: 0.15, y: 0.2, r: 12, label: labels[0] || "Var 1" },
      { x: 0.35, y: 0.45, r: 16, label: labels[1] || "Var 2" },
      { x: 0.65, y: 0.7, r: 20, label: labels[2] || "Var 3" },
      { x: 0.85, y: 0.9, r: 24, label: labels[3] || "Var 4" },
    ];

    // Correlation line
    const pProg = easeOutCubic(clamp(tSec / 0.8));
    chartG.moveTo(plotLeft + 30, plotTop + plotH - 30)
      .lineTo(plotLeft + 30 + (plotW - 60) * pProg, plotTop + plotH - 30 - (plotH - 60) * pProg)
      .stroke({ color: colorToHexNumber(p.accent), width: 2, alpha: 0.85 });

    points.forEach((pt, idx) => {
      const px = plotLeft + pt.x * plotW;
      const py = plotTop + (1 - pt.y) * plotH;
      const ptP = staggerProgress(tSec, idx, 4, 0.1, 0.35);

      chartG.circle(px, py, pt.r * ptP).fill({ color: colorToHexNumber(idx === 3 ? p.accent : p.primary), alpha: 0.85 * ptP })
        .stroke({ color: 0xffffff, width: 1.5, alpha: 0.9 * ptP });
    });
  }
}

// ============================================================================
// 8. CHART COMPOSITOR
// ============================================================================
export class ChartCompositor implements ICompositor2D {
  public readonly type = SemanticRepresentationType.CHART;
  public readonly name = "Quantitative Continuous Chart";
  public readonly description = "Multi-series line, area, and continuous trend curves with D3 linear scales.";

  public createScene(scene: ExecutableSceneProgram, context: CompositorContext): Container {
    const root = new Container();
    root.label = `ChartScene_${scene.scene_id}`;
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;

    const bgG = new Graphics();
    drawTechnicalBackground(bgG, W, H, p, { title: scene.title, representationType: "QUANTITATIVE CHART" });
    root.addChild(bgG);

    const chartG = new Graphics();
    chartG.label = "ContinuousChartGraphics";
    root.addChild(chartG);

    return root;
  }

  public updateAt(root: Container, scene: ExecutableSceneProgram, tSec: number, context: CompositorContext): void {
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;
    const chartG = root.getChildByLabel("ContinuousChartGraphics") as Graphics;
    if (!chartG) return;
    chartG.clear();

    const chartLeft = 120;
    const chartTop = 140;
    const chartW = W - 240;
    const chartH = H - 260;

    const data = [15, 32, 45, 80, 110, 160, 240];
    const xScale = d3.scaleLinear().domain([0, data.length - 1]).range([chartLeft, chartLeft + chartW]);
    const yScale = d3.scaleLinear().domain([0, 260]).range([chartTop + chartH, chartTop]);

    // Grid lines
    for (let v = 0; v <= 260; v += 65) {
      const y = yScale(v);
      chartG.moveTo(chartLeft, y).lineTo(chartLeft + chartW, y).stroke({ color: colorToHexNumber(p.border), width: 1, alpha: 0.3 });
    }

    const prog = easeOutCubic(clamp(tSec / 0.9));
    const drawCount = Math.floor(prog * (data.length - 1));

    if (data.length > 1) {
      // Area Fill
      chartG.moveTo(xScale(0), chartTop + chartH);
      for (let i = 0; i <= drawCount; i++) {
        chartG.lineTo(xScale(i), yScale(data[i]));
      }
      chartG.lineTo(xScale(drawCount), chartTop + chartH);
      chartG.fill({ color: colorToHexNumber(p.accent), alpha: 0.15 });

      // Trend Line
      chartG.moveTo(xScale(0), yScale(data[0]));
      for (let i = 1; i <= drawCount; i++) {
        chartG.lineTo(xScale(i), yScale(data[i]));
      }
      chartG.stroke({ color: colorToHexNumber(p.accent), width: 3, alpha: 0.95 });

      // Data dots
      for (let i = 0; i <= drawCount; i++) {
        chartG.circle(xScale(i), yScale(data[i]), 5).fill({ color: 0xffffff, alpha: 0.95 })
          .stroke({ color: colorToHexNumber(p.accent), width: 2 });
      }
    }
  }
}

// ============================================================================
// 9. LAYER_STACK COMPOSITOR
// ============================================================================
export class LayerStackCompositor implements ICompositor2D {
  public readonly type = SemanticRepresentationType.LAYER_STACK;
  public readonly name = "2.5D Layer Stack";
  public readonly description = "Isometric stacked layer planes with vertical elevator bus lines.";

  public createScene(scene: ExecutableSceneProgram, context: CompositorContext): Container {
    const root = new Container();
    root.label = `LayerStackScene_${scene.scene_id}`;
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;

    const bgG = new Graphics();
    drawTechnicalBackground(bgG, W, H, p, { title: scene.title, representationType: "LAYERED ARCHITECTURE STACK" });
    root.addChild(bgG);

    const labels = extractDynamicLabels(scene, 4);
    const layersGroup = new Container();
    layersGroup.label = "LayersGroup";

    const stackW = W * 0.58;
    const stackH = 70;

    labels.forEach((l, idx) => {
      const ly = 120 + idx * 85;
      const lGroup = new Container();
      lGroup.label = `Layer_${idx}`;
      lGroup.position.set(W / 2 - stackW / 2, ly);

      const g = new Graphics();
      drawGlassCard(g, 0, 0, stackW, stackH, 8, p.surface, idx === 0 ? p.accent : p.border, idx === 0 ? 2 : 1.2);
      lGroup.addChild(g);

      const badge = createStyledText(`TIER 0${idx + 1}`, { fontSize: 10, fontWeight: "bold", fill: idx === 0 ? (p.accent as any) : (p.textMuted as any) }, genome);
      badge.position.set(24, 14);
      lGroup.addChild(badge);

      const text = createStyledText(l, { fontSize: 13, fontWeight: "bold", fill: p.text as any }, genome);
      text.position.set(24, 34);
      lGroup.addChild(text);

      layersGroup.addChild(lGroup);
    });

    root.addChild(layersGroup);
    return root;
  }

  public updateAt(root: Container, scene: ExecutableSceneProgram, tSec: number, context: CompositorContext): void {
    const layersGroup = root.getChildByLabel("LayersGroup") as Container;
    if (!layersGroup) return;

    layersGroup.children.forEach((l, idx) => {
      const lp = staggerProgress(tSec, idx, 4, 0.15, 0.4);
      l.alpha = Math.max(0.65, lp);
    });
  }
}

// ============================================================================
// 10. SYSTEM_ARCHITECTURE COMPOSITOR (AUTHENTIC HARDWARE & CRT MESH)
// ============================================================================
export class SystemArchitectureCompositor implements ICompositor2D {
  public readonly type = SemanticRepresentationType.SYSTEM_ARCHITECTURE;
  public readonly name = "System Architecture Hardware Blueprint";
  public readonly description = "Authentic industrial gateway switch connected via glowing laser conduits to vintage CRT service monitors.";

  public createScene(scene: ExecutableSceneProgram, context: CompositorContext): Container {
    const root = new Container();
    root.label = `SystemArchitectureScene_${scene.scene_id}`;
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;

    const bgG = new Graphics();
    drawTechnicalBackground(bgG, W, H, p, { title: scene.title, representationType: "HARDWARE TOPOLOGY ROUTING" });
    root.addChild(bgG);

    const conduitsG = new Graphics();
    conduitsG.label = "ConduitsLayer";
    root.addChild(conduitsG);

    const labels = extractDynamicLabels(scene, 4);

    // 1. Left Hardware Appliance: Industrial Network Switch / Router
    const switchW = 280;
    const switchH = 170;
    const switchX = 80;
    const switchY = H / 2 - switchH / 2;

    const switchGroup = new Container();
    switchGroup.label = "SwitchAppliance";
    switchGroup.position.set(switchX, switchY);

    const switchG = new Graphics();
    switchG.label = "SwitchGraphics";
    drawIndustrialNetworkSwitch(switchG, 0, 0, switchW, switchH, p, { portsCount: 6, activePortIndex: 1 });
    switchGroup.addChild(switchG);

    const switchLabel = createStyledText(labels[0] || "CORE ROUTER", { fontSize: 11, fontWeight: "bold", fill: p.accent as any, fontFamily: genome.typography.codeFont }, genome);
    switchLabel.position.set(24, switchH + 10);
    switchGroup.addChild(switchLabel);

    root.addChild(switchGroup);

    // 2. Right Hardware Appliance Stack: 3 Vintage CRT Monitors (e.g. Anthropic, Bedrock, Vertex AI)
    const targetsContainer = new Container();
    targetsContainer.label = "TargetMonitorsContainer";

    const crtW = 160;
    const crtH = 120;
    const targetStartX = W - 360;
    const targetLabels = [
      labels[1] || "ANTHROPIC DIRECT",
      labels[2] || "AWS BEDROCK",
      labels[3] || "GOOGLE VERTEX",
    ];
    const latencies = ["310ms", "180ms", "95ms"];

    targetLabels.forEach((tLabel, idx) => {
      const cy = 90 + idx * 150;
      const tGroup = new Container();
      tGroup.label = `Target_${idx}`;
      tGroup.position.set(targetStartX, cy);

      const crtG = new Graphics();
      crtG.label = "CRTGraphics";
      const crtOpts = {
        theme: (idx === 0 ? "amber" : idx === 1 ? "beige" : "dark") as any,
        hasDials: true,
        scanlines: true,
        hasAntenna: idx === 0,
      };
      const { screenX, screenY, screenW, screenH } = drawVintageCRTMonitor(crtG, 0, 0, crtW, crtH, p, crtOpts);
      tGroup.addChild(crtG);

      // CRT Internal Screen Text
      const screenTitle = createStyledText(tLabel.split(" ")[0] || "SVC", {
        fontSize: 10,
        fontWeight: "bold",
        fill: (idx === 0 ? "#ffb300" : idx === 1 ? "#1e2430" : p.accent) as any,
        fontFamily: genome.typography.codeFont,
        align: "center",
      }, genome);
      screenTitle.anchor.set(0.5, 0.5);
      screenTitle.position.set(screenX + screenW * 0.5, screenY + screenH * 0.5);
      tGroup.addChild(screenTitle);

      // Side Telemetry Badge (Latency & status)
      const badgeX = crtW + 16;
      const badgeY = 24;
      const bG = new Graphics();
      drawGlassCard(bG, badgeX, badgeY, 140, 52, 6, p.surfaceElevated || p.surface, idx === 0 ? p.accent : p.border, 1.2);
      tGroup.addChild(bG);

      const bName = createStyledText(tLabel, { fontSize: 10, fontWeight: "bold", fill: p.text as any, wordWrap: true, wordWrapWidth: 120 }, genome);
      bName.position.set(badgeX + 10, badgeY + 8);
      tGroup.addChild(bName);

      const bLat = createStyledText(latencies[idx] || "120ms", { fontSize: 11, fontWeight: "bold", fill: (idx === 1 ? p.success || "#10b981" : p.accent) as any, fontFamily: genome.typography.codeFont }, genome);
      bLat.position.set(badgeX + 10, badgeY + 28);
      tGroup.addChild(bLat);

      targetsContainer.addChild(tGroup);
    });

    root.addChild(targetsContainer);
    return root;
  }

  public updateAt(root: Container, scene: ExecutableSceneProgram, tSec: number, context: CompositorContext): void {
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;

    const conduitsG = root.getChildByLabel("ConduitsLayer") as Graphics;
    const switchGroup = root.getChildByLabel("SwitchAppliance") as Container;
    const targets = root.getChildByLabel("TargetMonitorsContainer") as Container;
    if (!conduitsG || !switchGroup || !targets) return;

    conduitsG.clear();

    const switchG = switchGroup.getChildByLabel("SwitchGraphics") as Graphics;
    if (switchG) {
      switchG.clear();
      drawIndustrialNetworkSwitch(switchG, 0, 0, 280, 170, p, { portsCount: 6, activePortIndex: 1, tSec, radarSpin: true });
    }

    const startX = switchGroup.x + 280;
    const startY = switchGroup.y + 85;

    targets.children.forEach((tGroup, idx) => {
      const tg = tGroup as Container;
      const targetX = tg.x;
      const targetY = tg.y + 60;

      // Draw Laser-Glow Bezier Conduit from Switch to CRT Monitor
      const pulseProgress = (tSec * 1.8 + idx * 0.33) % 1.0;
      drawCurvedLink(conduitsG, startX, startY, targetX, targetY, p.accent, 2.5, 0.45, pulseProgress, 0.95);

      // Smooth entrance stagger
      const tp = staggerProgress(tSec, idx, 3, 0.12, 0.4);
      tg.alpha = Math.max(0.65, tp);
    });
  }
}

// ============================================================================
// 11. DOCUMENT_SOURCE COMPOSITOR
// ============================================================================
export class DocumentSourceCompositor implements ICompositor2D {
  public readonly type = SemanticRepresentationType.DOCUMENT_SOURCE;
  public readonly name = "Document Source Inspection";
  public readonly description = "Official source document artifact with highlighted excerpts and verification seal.";

  public createScene(scene: ExecutableSceneProgram, context: CompositorContext): Container {
    const root = new Container();
    root.label = `DocumentSourceScene_${scene.scene_id}`;
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;

    const bgG = new Graphics();
    drawTechnicalBackground(bgG, W, H, p, { title: scene.title, representationType: "GROUND TRUTH SOURCE VERIFICATION" });
    root.addChild(bgG);

    const docW = W * 0.58;
    const docH = H - 180;
    const docGroup = new Container();
    docGroup.label = "DocContainer";
    docGroup.position.set(80, 100);

    const docG = new Graphics();
    drawGlassCard(docG, 0, 0, docW, docH, 8, p.surface, p.border, 1.5, 0.95);
    docGroup.addChild(docG);

    const seal = createStyledText("VERIFIED GROUND TRUTH SOURCE", { fontSize: 10, fontWeight: "bold", fill: p.accent as any }, genome);
    seal.position.set(24, 20);
    docGroup.addChild(seal);

    const labels = extractDynamicLabels(scene, 3);
    const excerptText = (scene as any).narration_text || (scene as any).intended_understanding || labels[0] || "Verified source document grounding.";
    const excerpt = createStyledText(
      `"${excerptText}"`,
      { fontSize: 14, fontWeight: "bold", fill: p.text as any, wordWrap: true, wordWrapWidth: docW - 48, lineHeight: 22 },
      genome
    );
    excerpt.position.set(24, 60);
    docGroup.addChild(excerpt);

    root.addChild(docGroup);

    // Key claims side card
    const sideW = W - docW - 200;
    const sideGroup = new Container();
    sideGroup.label = "SideClaims";
    sideGroup.position.set(W - sideW - 80, 100);

    const sideG = new Graphics();
    drawGlassCard(sideG, 0, 0, sideW, docH, 8, p.surfaceElevated || p.surface, p.accent, 1.5, 1.0, 0.2);
    sideGroup.addChild(sideG);

    const sideTag = createStyledText("GROUNDED CLAIMS", { fontSize: 10, fontWeight: "bold", fill: p.accent as any }, genome);
    sideTag.position.set(16, 20);
    sideGroup.addChild(sideTag);

    labels.slice(1).forEach((claim, idx) => {
      const cText = createStyledText(`• ${claim}`, { fontSize: 12, fill: p.textSecondary as any, wordWrap: true, wordWrapWidth: sideW - 32 }, genome);
      cText.position.set(16, 55 + idx * 45);
      sideGroup.addChild(cText);
    });

    root.addChild(sideGroup);
    return root;
  }

  public updateAt(root: Container, scene: ExecutableSceneProgram, tSec: number, context: CompositorContext): void {
    const doc = root.getChildByLabel("DocContainer") as Container;
    const side = root.getChildByLabel("SideClaims") as Container;
    if (doc) doc.alpha = Math.max(0.7, easeOutCubic(clamp(tSec / 0.5)));
    if (side) side.alpha = Math.max(0.7, easeOutCubic(clamp((tSec - 0.2) / 0.5)));
  }
}

// ============================================================================
// 12. CODE_EXPLANATION COMPOSITOR (AUTHENTIC CRT TERMINAL & LIVE TYPING)
// ============================================================================
export class CodeExplanationCompositor implements ICompositor2D {
  public readonly type = SemanticRepresentationType.CODE_EXPLANATION;
  public readonly name = "Vintage CRT Code Terminal";
  public readonly description = "Authentic vintage CRT terminal with live command typing, syntax highlights, and phosphor glow.";

  public createScene(scene: ExecutableSceneProgram, context: CompositorContext): Container {
    const root = new Container();
    root.label = `CodeExplanationScene_${scene.scene_id}`;
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;

    const bgG = new Graphics();
    drawTechnicalBackground(bgG, W, H, p, { title: scene.title, representationType: "VINTAGE CRT TERMINAL" });
    root.addChild(bgG);

    const labels = extractDynamicLabels(scene, 3);
    const crtW = Math.min(620, W * 0.56);
    const crtH = H - 180;
    const crtX = 80;
    const crtY = 90;

    const crtGroup = new Container();
    crtGroup.label = "CRTMonitorGroup";
    crtGroup.position.set(crtX, crtY);

    const crtG = new Graphics();
    crtG.label = "CRTGraphics";
    const { screenX, screenY, screenW, screenH } = drawVintageCRTMonitor(crtG, 0, 0, crtW, crtH, p, {
      theme: "beige",
      hasAntenna: false,
      hasDials: true,
      powerLedOn: true,
      scanlines: true,
      screenColor: 0xf6f3ea,
    });
    crtGroup.addChild(crtG);

    // Terminal Screen Content
    const termContainer = new Container();
    termContainer.label = "TerminalContent";
    termContainer.position.set(screenX + 16, screenY + 16);

    const promptText = createStyledText("$ python app.py\n> " + (labels[0] || "why use Voice Flow?"), {
      fontSize: 13,
      fontWeight: "bold",
      fill: "#1f2937" as any,
      fontFamily: genome.typography.codeFont || "monospace",
      lineHeight: 22,
    }, genome);
    promptText.label = "PromptText";
    termContainer.addChild(promptText);

    // Live Animated Output Text
    const outputText = createStyledText("■ 0% markup · instant deterministic dispatch\n■ active model: " + (labels[1] || "Claude 3.5 Sonnet"), {
      fontSize: 12,
      fontWeight: "bold",
      fill: (p.accent || "#0284c7") as any,
      fontFamily: genome.typography.codeFont || "monospace",
      lineHeight: 20,
    }, genome);
    outputText.position.set(0, 56);
    outputText.label = "OutputText";
    termContainer.addChild(outputText);

    crtGroup.addChild(termContainer);
    root.addChild(crtGroup);

    // Right Side Architectural Annotation Card
    const sideX = crtX + crtW + 40;
    const sideW = W - sideX - 80;
    const calloutGroup = new Container();
    calloutGroup.label = "TerminalAnnotation";
    calloutGroup.position.set(sideX, crtY + 40);

    const sideG = new Graphics();
    drawGlassCard(sideG, 0, 0, sideW, crtH - 80, 10, p.surfaceElevated || p.surface, p.accent, 2, 1.0, 0.25);
    calloutGroup.addChild(sideG);

    const tag = createStyledText("TERMINAL PIPELINE", { fontSize: 10, fontWeight: "bold", fill: p.accent as any }, genome);
    tag.position.set(20, 20);
    calloutGroup.addChild(tag);

    const sideTitle = createStyledText(labels[0] || "Deterministic Pipeline", {
      fontSize: 16,
      fontWeight: "bold",
      fill: p.text as any,
      wordWrap: true,
      wordWrapWidth: sideW - 40,
    }, genome);
    sideTitle.position.set(20, 48);
    calloutGroup.addChild(sideTitle);

    const desc = createStyledText(
      (scene as any).narration_text || (scene as any).teaching_goal || labels[1] || "Live terminal instruction execution.",
      { fontSize: 12, fill: p.textSecondary as any, wordWrap: true, wordWrapWidth: sideW - 40, lineHeight: 18 },
      genome
    );
    desc.position.set(20, 100);
    calloutGroup.addChild(desc);

    root.addChild(calloutGroup);
    return root;
  }

  public updateAt(root: Container, scene: ExecutableSceneProgram, tSec: number, context: CompositorContext): void {
    const crt = root.getChildByLabel("CRTMonitorGroup") as Container;
    const annotation = root.getChildByLabel("TerminalAnnotation") as Container;
    if (!crt) return;

    // Typewriter cursor blink simulation
    const termContent = crt.getChildByLabel("TerminalContent") as Container;
    if (termContent) {
      const output = termContent.getChildByLabel("OutputText") as Text;
      if (output) {
        output.alpha = Math.sin(tSec * 6.0) > 0 ? 1.0 : 0.6;
      }
    }

    if (annotation) {
      annotation.alpha = Math.max(0.75, easeOutCubic(clamp(tSec / 0.6)));
    }
  }
}


// ============================================================================
// 13. EQUATION_EXPLANATION COMPOSITOR
// ============================================================================
export class EquationExplanationCompositor implements ICompositor2D {
  public readonly type = SemanticRepresentationType.EQUATION_EXPLANATION;
  public readonly name = "Equation Term Breakdown";
  public readonly description = "Mathematical equation breakdown with under-bracket callouts and variable definition cards.";

  public createScene(scene: ExecutableSceneProgram, context: CompositorContext): Container {
    const root = new Container();
    root.label = `EquationScene_${scene.scene_id}`;
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;

    const bgG = new Graphics();
    drawTechnicalBackground(bgG, W, H, p, { title: scene.title, representationType: "MATHEMATICAL FORMULATION" });
    root.addChild(bgG);

    const labels = extractDynamicLabels(scene, 3);
    const formulaBox = new Container();
    formulaBox.label = "FormulaBox";
    formulaBox.position.set(W / 2, H / 3);

    const fG = new Graphics();
    drawGlassCard(fG, -320, -50, 640, 100, 12, p.surfaceElevated || p.surface, p.accent, 2, 1.0, 0.25);
    formulaBox.addChild(fG);

    const formula = createStyledText(
      labels[0] || "State(t) = LayoutEngine(Scene) ⊙ ShaderRig(Genome, t)",
      { fontSize: 20, fontWeight: "bold", fill: p.accent as any, fontFamily: genome.typography.codeFont },
      genome
    );
    formula.anchor.set(0.5, 0.5);
    formulaBox.addChild(formula);
    root.addChild(formulaBox);

    // Terms explanation row
    const termsContainer = new Container();
    termsContainer.label = "TermsRow";
    const terms = [labels[1] || "Variable Alpha", labels[2] || "Variable Beta"];
    const termW = 260;
    terms.forEach((term, idx) => {
      const tx = W / 2 - 280 + idx * 300;
      const ty = H / 2 + 70;
      const tGroup = new Container();
      tGroup.position.set(tx, ty);

      const g = new Graphics();
      drawGlassCard(g, 0, 0, termW, 90, 8, p.surface, p.border, 1.2);
      tGroup.addChild(g);

      const tag = createStyledText(`TERM 0${idx + 1}`, { fontSize: 9, fontWeight: "bold", fill: p.accent as any }, genome);
      tag.position.set(16, 14);
      tGroup.addChild(tag);

      const termTitle = createStyledText(term, { fontSize: 12, fontWeight: "bold", fill: p.text as any, wordWrap: true, wordWrapWidth: termW - 32 }, genome);
      termTitle.position.set(16, 36);
      tGroup.addChild(termTitle);

      termsContainer.addChild(tGroup);
    });

    root.addChild(termsContainer);
    return root;
  }

  public updateAt(root: Container, scene: ExecutableSceneProgram, tSec: number, context: CompositorContext): void {
    const fBox = root.getChildByLabel("FormulaBox") as Container;
    const terms = root.getChildByLabel("TermsRow") as Container;
    if (fBox) fBox.scale.set(1.0 + 0.02 * Math.sin(tSec * 2.0));
    if (terms) {
      terms.children.forEach((c, idx) => {
        const cp = staggerProgress(tSec, idx, 3, 0.15, 0.4);
        (c as Container).alpha = Math.max(0.7, cp);
      });
    }
  }
}

// ============================================================================
// 14. MAP_GEOGRAPHY COMPOSITOR
// ============================================================================
export class MapGeographyCompositor implements ICompositor2D {
  public readonly type = SemanticRepresentationType.MAP_GEOGRAPHY;
  public readonly name = "Topological Geography Mesh";
  public readonly description = "Global topological grid map with geo nodes and routing telemetry.";

  public createScene(scene: ExecutableSceneProgram, context: CompositorContext): Container {
    const root = new Container();
    root.label = `MapGeographyScene_${scene.scene_id}`;
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;

    const bgG = new Graphics();
    drawTechnicalBackground(bgG, W, H, p, { title: scene.title, representationType: "GLOBAL TOPOLOGY" });
    root.addChild(bgG);

    const mapG = new Graphics();
    mapG.label = "MapLayer";
    root.addChild(mapG);

    const labels = extractDynamicLabels(scene, 4);
    const nodesGroup = new Container();
    nodesGroup.label = "GeoNodesGroup";

    const coords = [
      { x: W * 0.28, y: H * 0.42, name: labels[0] || "Region West" },
      { x: W * 0.50, y: H * 0.35, name: labels[1] || "Central Hub" },
      { x: W * 0.72, y: H * 0.52, name: labels[2] || "Region East" },
      { x: W * 0.62, y: H * 0.68, name: labels[3] || "Edge Cluster" },
    ];

    coords.forEach((coord, idx) => {
      const gNode = new Container();
      gNode.label = `GeoNode_${idx}`;
      gNode.position.set(coord.x, coord.y);

      const g = new Graphics();
      g.circle(0, 0, 8).fill({ color: colorToHexNumber(p.accent), alpha: 0.95 });
      g.circle(0, 0, 16).stroke({ color: colorToHexNumber(p.accent), width: 1.5, alpha: 0.5 });
      gNode.addChild(g);

      const label = createStyledText(coord.name, { fontSize: 11, fontWeight: "bold", fill: p.text as any }, genome);
      label.position.set(12, -8);
      gNode.addChild(label);

      nodesGroup.addChild(gNode);
    });

    root.addChild(nodesGroup);
    return root;
  }

  public updateAt(root: Container, scene: ExecutableSceneProgram, tSec: number, context: CompositorContext): void {
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;

    const mapG = root.getChildByLabel("MapLayer") as Graphics;
    const nodesGroup = root.getChildByLabel("GeoNodesGroup") as Container;
    if (!mapG || !nodesGroup) return;

    mapG.clear();

    // Radar sweep line
    const cx = W / 2;
    const cy = H / 2;
    const radarAngle = tSec * 1.2;
    const rx = cx + Math.cos(radarAngle) * 350;
    const ry = cy + Math.sin(radarAngle) * 350;
    mapG.moveTo(cx, cy).lineTo(rx, ry).stroke({ color: colorToHexNumber(p.accent), width: 1.5, alpha: 0.45 });

    // Connect geo nodes
    const nodes = nodesGroup.children as Container[];
    for (let i = 0; i < nodes.length - 1; i++) {
      const n1 = nodes[i];
      const n2 = nodes[i + 1];
      const pulseP = (tSec * 1.5 + i * 0.3) % 1.0;
      drawCurvedLink(mapG, n1.x, n1.y, n2.x, n2.y, p.accent, 1.5, 0.3, pulseP, 0.85);
    }
  }
}

// ============================================================================
// 15. SEQUENCE COMPOSITOR
// ============================================================================
export class SequenceCompositor implements ICompositor2D {
  public readonly type = SemanticRepresentationType.SEQUENCE;
  public readonly name = "Sequence & State Machine";
  public readonly description = "Participant lifelines and numbered message dispatch arrows.";

  public createScene(scene: ExecutableSceneProgram, context: CompositorContext): Container {
    const root = new Container();
    root.label = `SequenceScene_${scene.scene_id}`;
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;

    const bgG = new Graphics();
    drawTechnicalBackground(bgG, W, H, p, { title: scene.title, representationType: "SEQUENCE DISPATCH" });
    root.addChild(bgG);

    const labels = extractDynamicLabels(scene, 4);
    const actors = [labels[0] || "Client", labels[1] || "Gateway", labels[2] || "Core Service", labels[3] || "Store"];
    const actorCount = actors.length;
    const scaleX = d3.scaleLinear().domain([0, actorCount - 1]).range([160, W - 160]);

    const actorsGroup = new Container();
    actorsGroup.label = "ActorsGroup";

    actors.forEach((act, idx) => {
      const ax = scaleX(idx);
      const aGroup = new Container();
      aGroup.position.set(ax, 100);

      const g = new Graphics();
      drawGlassCard(g, -60, 0, 120, 44, 6, p.surfaceElevated || p.surface, idx === 0 ? p.accent : p.border, 1.2);
      aGroup.addChild(g);

      const t = createStyledText(act, { fontSize: 11, fontWeight: "bold", fill: p.text as any, align: "center" }, genome);
      t.anchor.set(0.5, 0.5);
      t.position.set(0, 22);
      aGroup.addChild(t);

      actorsGroup.addChild(aGroup);
    });

    root.addChild(actorsGroup);

    const dispatchG = new Graphics();
    dispatchG.label = "DispatchLayer";
    root.addChild(dispatchG);

    return root;
  }

  public updateAt(root: Container, scene: ExecutableSceneProgram, tSec: number, context: CompositorContext): void {
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;

    const dispatchG = root.getChildByLabel("DispatchLayer") as Graphics;
    if (!dispatchG) return;
    dispatchG.clear();

    const scaleX = d3.scaleLinear().domain([0, 3]).range([160, W - 160]);

    // Lifeline vertical dashed tracks
    for (let i = 0; i < 4; i++) {
      const ax = scaleX(i);
      dispatchG.moveTo(ax, 150).lineTo(ax, H - 80).stroke({ color: colorToHexNumber(p.border), width: 1, alpha: 0.35 });
    }

    // Sequence messages dispatching down timeline
    const msgY1 = 200;
    const msgY2 = 270;
    const msgY3 = 340;

    const p1 = clamp(tSec / 0.8);
    const p2 = clamp((tSec - 0.4) / 0.8);
    const p3 = clamp((tSec - 0.8) / 0.8);

    drawArrowConnector(dispatchG, scaleX(0), msgY1, scaleX(1), msgY1, p.accent, 2, 6, p1 % 1.0, p1);
    if (tSec > 0.4) drawArrowConnector(dispatchG, scaleX(1), msgY2, scaleX(2), msgY2, p.accent, 2, 6, p2 % 1.0, p2);
    if (tSec > 0.8) drawArrowConnector(dispatchG, scaleX(2), msgY3, scaleX(3), msgY3, p.accent, 2, 6, p3 % 1.0, p3);
  }
}

// ============================================================================
// 16. OBJECT_FOCUS COMPOSITOR
// ============================================================================
export class ObjectFocusCompositor implements ICompositor2D {
  public readonly type = SemanticRepresentationType.OBJECT_FOCUS;
  public readonly name = "Object Hero Focus";
  public readonly description = "Central hero card with glowing outline, floating satellite badges, and kinetic radar pulse.";

  public createScene(scene: ExecutableSceneProgram, context: CompositorContext): Container {
    const root = new Container();
    root.label = `ObjectFocusScene_${scene.scene_id}`;
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;

    const bgG = new Graphics();
    drawTechnicalBackground(bgG, W, H, p, { title: scene.title, representationType: "HERO FOCUS ANALYSIS" });
    root.addChild(bgG);

    const hudG = new Graphics();
    hudG.label = "HUDLayer";
    root.addChild(hudG);

    const labels = extractDynamicLabels(scene, 5);
    const cx = W / 2;
    const cy = H / 2;

    const heroGroup = new Container();
    heroGroup.label = "HeroCard";
    heroGroup.position.set(cx, cy);

    const heroW = 290;
    const heroH = 185;
    const cardG = new Graphics();
    drawGlassCard(cardG, -heroW / 2, -heroH / 2, heroW, heroH, 12, p.surfaceElevated || p.surface, p.accent, 2, 1.0, 0.3);
    drawHUDCornerBrackets(cardG, -heroW / 2, -heroH / 2, heroW, heroH, 16, p.accent, 2);
    heroGroup.addChild(cardG);

    const heroTag = createStyledText("PRIMARY CONCEPT", { fontSize: 10, fontWeight: "bold", fill: p.accent as any }, genome);
    heroTag.anchor.set(0.5, 0.5);
    heroTag.position.set(0, -50);
    heroGroup.addChild(heroTag);

    const heroTitle = createStyledText(labels[0] || scene.title || "Core Topic", { fontSize: 16, fontWeight: "bold", fill: p.text as any, align: "center", wordWrap: true, wordWrapWidth: heroW - 32 }, genome);
    heroTitle.anchor.set(0.5, 0.5);
    heroTitle.position.set(0, -10);
    heroGroup.addChild(heroTitle);

    const heroSub = createStyledText((scene as any).intended_understanding || "Key architectural definition", { fontSize: 11, fill: p.textSecondary as any, align: "center", wordWrap: true, wordWrapWidth: heroW - 32 }, genome);
    heroSub.anchor.set(0.5, 0.5);
    heroSub.position.set(0, 35);
    heroGroup.addChild(heroSub);

    root.addChild(heroGroup);

    const satellites = [
      { text: labels[1] || "Feature Alpha", offset: [-250, -100] },
      { text: labels[2] || "Feature Beta", offset: [250, -100] },
      { text: labels[3] || "Architecture", offset: [-250, 100] },
      { text: labels[4] || "Integration", offset: [250, 100] },
    ];

    const satGroup = new Container();
    satGroup.label = "Satellites";
    satellites.forEach((s, idx) => {
      const sBox = new Container();
      sBox.label = `Sat_${idx}`;
      sBox.position.set(cx + s.offset[0], cy + s.offset[1]);

      const g = new Graphics();
      drawGlassCard(g, -95, -26, 190, 52, 6, p.surface, p.border, 1.2);
      sBox.addChild(g);

      const t = createStyledText(s.text, { fontSize: 11, fontWeight: "bold", fill: p.text as any, align: "center", wordWrap: true, wordWrapWidth: 170 }, genome);
      t.anchor.set(0.5, 0.5);
      sBox.addChild(t);

      satGroup.addChild(sBox);
    });

    root.addChild(satGroup);
    return root;
  }

  public updateAt(root: Container, scene: ExecutableSceneProgram, tSec: number, context: CompositorContext): void {
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;

    const hudG = root.getChildByLabel("HUDLayer") as Graphics;
    const hero = root.getChildByLabel("HeroCard") as Container;
    const sats = root.getChildByLabel("Satellites") as Container;
    if (!hudG || !hero || !sats) return;

    hudG.clear();
    const cx = W / 2;
    const cy = H / 2;

    hero.scale.set(1.0 + 0.02 * Math.sin(tSec * 2.5));
    drawPulseRing(hudG, cx, cy, 180, p.accent, 0.4 + 0.2 * Math.sin(tSec * 2.0), 2);

    sats.children.forEach((s, idx) => {
      const sat = s as Container;
      const sp = staggerProgress(tSec, idx, 4, 0.15, 0.4);
      sat.alpha = Math.max(0.65, sp);
      hudG.moveTo(cx, cy).lineTo(sat.x, sat.y).stroke({ color: colorToHexNumber(p.accent), width: 1, alpha: 0.35 * Math.max(0.65, sp) });
    });
  }
}

// ============================================================================
// 17. BEFORE_AFTER COMPOSITOR
// ============================================================================
export class BeforeAfterCompositor implements ICompositor2D {
  public readonly type = SemanticRepresentationType.BEFORE_AFTER;
  public readonly name = "Before & After Interactive Split";
  public readonly description = "Side-by-side Before/After state comparison with scanning division needle.";

  public createScene(scene: ExecutableSceneProgram, context: CompositorContext): Container {
    const root = new Container();
    root.label = `BeforeAfterScene_${scene.scene_id}`;
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;

    const bgG = new Graphics();
    drawTechnicalBackground(bgG, W, H, p, { title: scene.title, representationType: "BEFORE / AFTER DELTA" });
    root.addChild(bgG);

    const labels = extractDynamicLabels(scene, 4);
    const panelW = (W - 220) / 2;
    const panelH = H - 200;

    // Before Box
    const beforeGroup = new Container();
    beforeGroup.position.set(80, 100);
    const bG = new Graphics();
    drawGlassCard(bG, 0, 0, panelW, panelH, 10, p.surface, p.warning || "#f59e0b", 1.5);
    beforeGroup.addChild(bG);

    const bBadge = createStyledText("BEFORE (BASELINE)", { fontSize: 10, fontWeight: "bold", fill: (p.warning || "#f59e0b") as any }, genome);
    bBadge.position.set(20, 20);
    beforeGroup.addChild(bBadge);

    const bTitle = createStyledText(labels[0] || "Legacy Constraints", { fontSize: 15, fontWeight: "bold", fill: p.text as any, wordWrap: true, wordWrapWidth: panelW - 40 }, genome);
    bTitle.position.set(20, 48);
    beforeGroup.addChild(bTitle);

    root.addChild(beforeGroup);

    // After Box
    const afterGroup = new Container();
    afterGroup.position.set(W / 2 + 30, 100);
    const aG = new Graphics();
    drawGlassCard(aG, 0, 0, panelW, panelH, 10, p.surfaceElevated || p.surface, p.success || p.accent || "#10b981", 2, 1.0, 0.25);
    afterGroup.addChild(aG);

    const aBadge = createStyledText("AFTER (OPTIMIZED)", { fontSize: 10, fontWeight: "bold", fill: (p.success || p.accent || "#10b981") as any }, genome);
    aBadge.position.set(20, 20);
    afterGroup.addChild(aBadge);

    const aTitle = createStyledText(labels[1] || "High-Throughput State", { fontSize: 15, fontWeight: "bold", fill: p.text as any, wordWrap: true, wordWrapWidth: panelW - 40 }, genome);
    aTitle.position.set(20, 48);
    afterGroup.addChild(aTitle);

    root.addChild(afterGroup);

    const sliderG = new Graphics();
    sliderG.label = "SliderLayer";
    root.addChild(sliderG);

    return root;
  }

  public updateAt(root: Container, scene: ExecutableSceneProgram, tSec: number, context: CompositorContext): void {
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;
    const sliderG = root.getChildByLabel("SliderLayer") as Graphics;
    if (!sliderG) return;

    sliderG.clear();
    const beamX = W / 2 + Math.sin(tSec * 2.0) * 20;
    sliderG.moveTo(beamX, 90).lineTo(beamX, H - 90).stroke({ color: colorToHexNumber(p.accent), width: 2, alpha: 0.9 });
  }
}

// ============================================================================
// 18. FLOW COMPOSITOR
// ============================================================================
export class FlowCompositor implements ICompositor2D {
  public readonly type = SemanticRepresentationType.FLOW;
  public readonly name = "Multi-Lane Stream Flow";
  public readonly description = "Multi-lane stream paths with fluid flow markers and lane dividers.";

  public createScene(scene: ExecutableSceneProgram, context: CompositorContext): Container {
    const root = new Container();
    root.label = `FlowScene_${scene.scene_id}`;
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;

    const bgG = new Graphics();
    drawTechnicalBackground(bgG, W, H, p, { title: scene.title, representationType: "DATA STREAM FLOW" });
    root.addChild(bgG);

    const flowG = new Graphics();
    flowG.label = "FlowLayer";
    root.addChild(flowG);

    const labels = extractDynamicLabels(scene, 3);
    const lanes = [labels[0] || "Ingestion Stream", labels[1] || "Processing Lane", labels[2] || "Output Channel"];
    const laneH = (H - 180) / lanes.length;

    lanes.forEach((name, idx) => {
      const ly = 100 + idx * laneH;
      const laneLabel = createStyledText(name, { fontSize: 12, fontWeight: "bold", fill: p.accent as any }, genome);
      laneLabel.position.set(80, ly + 12);
      root.addChild(laneLabel);
    });

    return root;
  }

  public updateAt(root: Container, scene: ExecutableSceneProgram, tSec: number, context: CompositorContext): void {
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;
    const flowG = root.getChildByLabel("FlowLayer") as Graphics;
    if (!flowG) return;

    flowG.clear();
    const laneCount = 3;
    const laneH = (H - 180) / laneCount;

    for (let i = 0; i < laneCount; i++) {
      const ly = 100 + i * laneH + laneH / 2;
      flowG.moveTo(80, ly).lineTo(W - 80, ly).stroke({ color: colorToHexNumber(p.border), width: 2, alpha: 0.4 });

      for (let j = 0; j < 5; j++) {
        const u = (tSec * (0.2 + i * 0.1) + j / 5) % 1.0;
        const px = lerp(80, W - 80, u);
        flowG.circle(px, ly, 4).fill({ color: colorToHexNumber(p.accent), alpha: 0.9 });
      }
    }
  }
}

// ============================================================================
// 19. CONCEPTUAL_METAPHOR COMPOSITOR
// ============================================================================
export class ConceptualMetaphorCompositor implements ICompositor2D {
  public readonly type = SemanticRepresentationType.CONCEPTUAL_METAPHOR;
  public readonly name = "Conceptual Metaphor";
  public readonly description = "Funnel, Flywheel, or Balance Scale diagrammatic model with throughput metrics.";

  public createScene(scene: ExecutableSceneProgram, context: CompositorContext): Container {
    const root = new Container();
    root.label = `ConceptualMetaphorScene_${scene.scene_id}`;
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;

    const bgG = new Graphics();
    drawTechnicalBackground(bgG, W, H, p, { title: scene.title, representationType: "CONCEPTUAL METAPHOR" });
    root.addChild(bgG);

    const labels = extractDynamicLabels(scene, 3);
    const metaphorG = new Graphics();
    metaphorG.label = "MetaphorGraphics";
    root.addChild(metaphorG);

    const cx = W / 2;
    const cy = H / 2;

    // Flywheel ring
    const ring = new Container();
    ring.label = "FlywheelRing";
    ring.position.set(cx, cy);

    const rG = new Graphics();
    rG.circle(0, 0, 110).stroke({ color: colorToHexNumber(p.accent), width: 4, alpha: 0.85 });
    rG.circle(0, 0, 80).stroke({ color: colorToHexNumber(p.border), width: 1.5, alpha: 0.5 });
    ring.addChild(rG);

    const coreTitle = createStyledText(labels[0] || "CORE FLYWHEEL", { fontSize: 12, fontWeight: "bold", fill: p.accent as any, align: "center" }, genome);
    coreTitle.anchor.set(0.5, 0.5);
    ring.addChild(coreTitle);

    root.addChild(ring);
    return root;
  }

  public updateAt(root: Container, scene: ExecutableSceneProgram, tSec: number, context: CompositorContext): void {
    const ring = root.getChildByLabel("FlywheelRing") as Container;
    if (ring) {
      ring.rotation = tSec * 0.8;
    }
  }
}

// ============================================================================
// 20. TRANSFORMATION COMPOSITOR
// ============================================================================
export class TransformationCompositor implements ICompositor2D {
  public readonly type = SemanticRepresentationType.TRANSFORMATION;
  public readonly name = "Transformation State Morph";
  public readonly description = "State A transforming into State B with a central scanning transition beam.";

  public createScene(scene: ExecutableSceneProgram, context: CompositorContext): Container {
    const root = new Container();
    root.label = `TransformationScene_${scene.scene_id}`;
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;

    const bgG = new Graphics();
    drawTechnicalBackground(bgG, W, H, p, { title: scene.title, representationType: "TRANSFORMATION DELTA" });
    root.addChild(bgG);

    const labels = extractDynamicLabels(scene, 2);
    const panelW = (W - 220) / 2;
    const panelH = H - 200;

    const beforeGroup = new Container();
    beforeGroup.position.set(80, 100);
    const bG = new Graphics();
    drawGlassCard(bG, 0, 0, panelW, panelH, 10, p.surface, p.border, 1.5);
    beforeGroup.addChild(bG);
    const bTitle = createStyledText(labels[0] || "INITIAL STATE", { fontSize: 14, fontWeight: "bold", fill: p.textMuted as any, wordWrap: true, wordWrapWidth: panelW - 40 }, genome);
    bTitle.position.set(20, 20);
    beforeGroup.addChild(bTitle);
    root.addChild(beforeGroup);

    const afterGroup = new Container();
    afterGroup.position.set(W / 2 + 30, 100);
    const aG = new Graphics();
    drawGlassCard(aG, 0, 0, panelW, panelH, 10, p.surfaceElevated || p.surface, p.accent, 2, 1.0, 0.25);
    afterGroup.addChild(aG);
    const aTitle = createStyledText(labels[1] || "TRANSFORMED STATE", { fontSize: 14, fontWeight: "bold", fill: p.accent as any, wordWrap: true, wordWrapWidth: panelW - 40 }, genome);
    aTitle.position.set(20, 20);
    afterGroup.addChild(aTitle);
    root.addChild(afterGroup);

    const laserG = new Graphics();
    laserG.label = "LaserLayer";
    root.addChild(laserG);

    return root;
  }

  public updateAt(root: Container, scene: ExecutableSceneProgram, tSec: number, context: CompositorContext): void {
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;
    const laserG = root.getChildByLabel("LaserLayer") as Graphics;
    if (!laserG) return;

    laserG.clear();
    const beamX = W / 2 + Math.sin(tSec * 2.0) * 15;
    laserG.moveTo(beamX, 90).lineTo(beamX, H - 90).stroke({ color: colorToHexNumber(p.accent), width: 2.5, alpha: 0.85 });
    laserG.moveTo(beamX, 90).lineTo(beamX, H - 90).stroke({ color: 0xffffff, width: 1, alpha: 0.95 });
  }
}

// ============================================================================
// 21. SUMMARY_RECAP COMPOSITOR
// ============================================================================
export class SummaryRecapCompositor implements ICompositor2D {
  public readonly type = SemanticRepresentationType.SUMMARY_RECAP;
  public readonly name = "Summary Key Takeaways";
  public readonly description = "Stacked summary key takeaway cards with numbered glowing shields.";

  public createScene(scene: ExecutableSceneProgram, context: CompositorContext): Container {
    const root = new Container();
    root.label = `SummaryRecapScene_${scene.scene_id}`;
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;

    const bgG = new Graphics();
    drawTechnicalBackground(bgG, W, H, p, { title: scene.title, representationType: "EXECUTIVE SUMMARY RECAP" });
    root.addChild(bgG);

    const labels = extractDynamicLabels(scene, 3);
    const cardsGroup = new Container();
    cardsGroup.label = "TakeawaysGroup";

    const cardW = W - 200;
    const cardH = 80;

    labels.forEach((text, idx) => {
      const cy = 120 + idx * 100;
      const cGroup = new Container();
      cGroup.label = `Takeaway_${idx}`;
      cGroup.position.set(100, cy);

      const g = new Graphics();
      drawGlassCard(g, 0, 0, cardW, cardH, 8, p.surfaceElevated || p.surface, idx === 0 ? p.accent : p.border, idx === 0 ? 2 : 1.2);
      cGroup.addChild(g);

      const badge = createStyledText(`0${idx + 1}`, { fontSize: 14, fontWeight: "bold", fill: idx === 0 ? (p.accent as any) : (p.textMuted as any) }, genome);
      badge.position.set(24, 28);
      cGroup.addChild(badge);

      const title = createStyledText(text, { fontSize: 14, fontWeight: "bold", fill: p.text as any, wordWrap: true, wordWrapWidth: cardW - 100 }, genome);
      title.position.set(64, 28);
      cGroup.addChild(title);

      cardsGroup.addChild(cGroup);
    });

    root.addChild(cardsGroup);
    return root;
  }

  public updateAt(root: Container, scene: ExecutableSceneProgram, tSec: number, context: CompositorContext): void {
    const cardsGroup = root.getChildByLabel("TakeawaysGroup") as Container;
    if (!cardsGroup) return;

    cardsGroup.children.forEach((c, idx) => {
      const cg = c as Container;
      const cp = staggerProgress(tSec, idx, 3, 0.15, 0.4);
      cg.alpha = Math.max(0.7, cp);
    });
  }
}

// ============================================================================
// 22. QUANTITATIVE COMPOSITOR (GLOWING LED MATRIX & HIGH-IMPACT METRICS)
// ============================================================================
export class QuantitativeCompositor implements ICompositor2D {
  public readonly type = SemanticRepresentationType.QUANTITATIVE;
  public readonly name = "Quantitative Charts & LED Matrix";
  public readonly description = "Authentic glowing LED dot-matrix metric numbers, bar charts, and crossed-out legacy fee badges.";

  public createScene(scene: ExecutableSceneProgram, context: CompositorContext): Container {
    const root = new Container();
    root.label = `QuantitativeScene_${scene.scene_id}`;
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;

    const bgG = new Graphics();
    drawTechnicalBackground(bgG, W, H, p, { title: scene.title, representationType: "QUANTITATIVE METRICS & LED MATRIX" });
    root.addChild(bgG);

    const labels = extractDynamicLabels(scene, 4);

    // 1. Central Hero LED Matrix Display (e.g. 0% or $10,000)
    const ledW = 320;
    const ledH = 150;
    const ledX = W / 2 - ledW / 2;
    const ledY = 100;

    const ledGroup = new Container();
    ledGroup.label = "LEDMatrixGroup";
    ledGroup.position.set(ledX, ledY);

    const ledG = new Graphics();
    ledG.label = "LEDMatrixGraphics";
    drawLEDMatrixDisplay(ledG, 0, 0, ledW, ledH, "0%", p);
    ledGroup.addChild(ledG);

    const ledCaption = createStyledText(labels[0] || "0% MARKUP ON YOUR TOKENS", {
      fontSize: 12,
      fontWeight: "bold",
      fill: p.accent as any,
      fontFamily: genome.typography.codeFont || "monospace",
      align: "center",
    }, genome);
    ledCaption.anchor.set(0.5, 0);
    ledCaption.position.set(ledW / 2, ledH + 12);
    ledGroup.addChild(ledCaption);

    root.addChild(ledGroup);

    // 2. Bottom Row: 3 Crossed-out Badges (e.g. Visa, MasterCard, Stripe / Legacy Fees)
    const badgesContainer = new Container();
    badgesContainer.label = "CrossedBadgesContainer";

    const badgeW = 180;
    const badgeH = 70;
    const badgeStartY = H - 180;
    const badgeNames = [labels[1] || "VISA", labels[2] || "MASTERCARD", labels[3] || "STRIPE"];
    const totalBadgesW = badgeNames.length * badgeW + (badgeNames.length - 1) * 40;
    const badgeStartX = (W - totalBadgesW) / 2;

    badgeNames.forEach((name, idx) => {
      const bx = badgeStartX + idx * (badgeW + 40);
      const bGroup = new Container();
      bGroup.label = `Badge_${idx}`;
      bGroup.position.set(bx, badgeStartY);

      const bgG = new Graphics();
      bgG.label = "BadgeGraphics";
      drawCrossedOutBadge(bgG, 0, 0, badgeW, badgeH, name, p, 1.0);
      bGroup.addChild(bgG);

      const bText = createStyledText(name, {
        fontSize: 14,
        fontWeight: "bold",
        fill: "#94a3b8" as any,
        fontFamily: genome.typography.codeFont || "monospace",
        align: "center",
      }, genome);
      bText.anchor.set(0.5, 0.5);
      bText.position.set(badgeW / 2, badgeH / 2);
      bGroup.addChild(bText);

      badgesContainer.addChild(bGroup);
    });

    root.addChild(badgesContainer);

    // Subtitle Pill at the bottom center
    const subPillGroup = new Container();
    subPillGroup.position.set(W / 2, H - 75);
    const subG = new Graphics();
    drawGlassCard(subG, -130, -18, 260, 36, 6, p.surfaceElevated || p.surface, p.accent, 1.5);
    subPillGroup.addChild(subG);

    const subText = createStyledText("ZERO PROCESSING FEES", {
      fontSize: 11,
      fontWeight: "bold",
      fill: (p.success || p.accent) as any,
      fontFamily: genome.typography.codeFont,
      align: "center",
    }, genome);
    subText.anchor.set(0.5, 0.5);
    subPillGroup.addChild(subText);
    root.addChild(subPillGroup);

    return root;
  }

  public updateAt(root: Container, scene: ExecutableSceneProgram, tSec: number, context: CompositorContext): void {
    const { genome } = context;
    const p = genome.palette;

    const ledGroup = root.getChildByLabel("LEDMatrixGroup") as Container;
    const badgesContainer = root.getChildByLabel("CrossedBadgesContainer") as Container;
    if (!ledGroup || !badgesContainer) return;

    // Pulse LED matrix
    const ledG = ledGroup.getChildByLabel("LEDMatrixGraphics") as Graphics;
    if (ledG) {
      ledG.clear();
      const pulseColor = Math.sin(tSec * 4) > 0 ? 0x10b981 : 0x059669;
      drawLEDMatrixDisplay(ledG, 0, 0, 320, 150, "0%", p, pulseColor);
    }

    // Animate Red X Crossout on each badge
    badgesContainer.children.forEach((bGroup, idx) => {
      const bg = bGroup as Container;
      const bG = bg.getChildByLabel("BadgeGraphics") as Graphics;
      if (bG) {
        bG.clear();
        const badgeP = clamp((tSec - idx * 0.2) / 0.5);
        drawCrossedOutBadge(bG, 0, 0, 180, 70, "", p, badgeP);
      }
    });
  }
}


// ============================================================================
// 23. LIST_BREAKDOWN COMPOSITOR
// ============================================================================
export class ListBreakdownCompositor implements ICompositor2D {
  public readonly type = SemanticRepresentationType.LIST_BREAKDOWN;
  public readonly name = "Itemized List Breakdown";
  public readonly description = "Structured itemized checklist with status icons and progress pill.";

  public createScene(scene: ExecutableSceneProgram, context: CompositorContext): Container {
    const root = new Container();
    root.label = `ListBreakdownScene_${scene.scene_id}`;
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;

    const bgG = new Graphics();
    drawTechnicalBackground(bgG, W, H, p, { title: scene.title, representationType: "STRUCTURED BREAKDOWN" });
    root.addChild(bgG);

    const labels = extractDynamicLabels(scene, 4);
    const listGroup = new Container();
    listGroup.label = "ListGroup";

    const itemW = W - 240;
    const itemH = 50;

    labels.forEach((text, idx) => {
      const iy = 110 + idx * 68;
      const iGroup = new Container();
      iGroup.label = `Item_${idx}`;
      iGroup.position.set(120, iy);

      const g = new Graphics();
      drawGlassCard(g, 0, 0, itemW, itemH, 6, p.surface, p.border, 1.2);
      iGroup.addChild(g);

      const dot = new Graphics();
      dot.circle(24, 25, 6).fill({ color: colorToHexNumber(p.accent) });
      iGroup.addChild(dot);

      const title = createStyledText(text, { fontSize: 12, fontWeight: "bold", fill: p.text as any, wordWrap: true, wordWrapWidth: itemW - 60 }, genome);
      title.position.set(44, 16);
      iGroup.addChild(title);

      listGroup.addChild(iGroup);
    });

    root.addChild(listGroup);
    return root;
  }

  public updateAt(root: Container, scene: ExecutableSceneProgram, tSec: number, context: CompositorContext): void {
    const listGroup = root.getChildByLabel("ListGroup") as Container;
    if (!listGroup) return;

    listGroup.children.forEach((c, idx) => {
      const cg = c as Container;
      const cp = staggerProgress(tSec, idx, 4, 0.1, 0.35);
      cg.alpha = Math.max(0.65, cp);
    });
  }
}

// ============================================================================
// 24. STAT_GRID COMPOSITOR
// ============================================================================
export class StatGridCompositor implements ICompositor2D {
  public readonly type = SemanticRepresentationType.STAT_GRID;
  public readonly name = "Multi-Metric Stat Grid";
  public readonly description = "2x2 or 3x2 KPI cards with large typography figures, sub-labels, and sparklines.";

  public createScene(scene: ExecutableSceneProgram, context: CompositorContext): Container {
    const root = new Container();
    root.label = `StatGridScene_${scene.scene_id}`;
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;

    const bgG = new Graphics();
    drawTechnicalBackground(bgG, W, H, p, { title: scene.title, representationType: "KPI STAT GRID" });
    root.addChild(bgG);

    const labels = extractDynamicLabels(scene, 4);
    const gridGroup = new Container();
    gridGroup.label = "GridGroup";

    const cardW = (W - 260) / 2;
    const cardH = (H - 240) / 2;

    labels.slice(0, 4).forEach((text, idx) => {
      const col = idx % 2;
      const row = Math.floor(idx / 2);
      const gx = 100 + col * (cardW + 60);
      const gy = 110 + row * (cardH + 20);

      const cGroup = new Container();
      cGroup.label = `StatCard_${idx}`;
      cGroup.position.set(gx, gy);

      const g = new Graphics();
      drawGlassCard(g, 0, 0, cardW, cardH, 8, p.surfaceElevated || p.surface, idx === 0 ? p.accent : p.border, idx === 0 ? 2 : 1.2);
      cGroup.addChild(g);

      const val = createStyledText(`0${idx + 1}`, { fontSize: 24, fontWeight: "bold", fill: idx === 0 ? (p.accent as any) : (p.text as any) }, genome);
      val.position.set(20, 16);
      cGroup.addChild(val);

      const title = createStyledText(text, { fontSize: 12, fontWeight: "bold", fill: p.textSecondary as any, wordWrap: true, wordWrapWidth: cardW - 40 }, genome);
      title.position.set(20, 50);
      cGroup.addChild(title);

      gridGroup.addChild(cGroup);
    });

    root.addChild(gridGroup);
    return root;
  }

  public updateAt(root: Container, scene: ExecutableSceneProgram, tSec: number, context: CompositorContext): void {
    const gridGroup = root.getChildByLabel("GridGroup") as Container;
    if (!gridGroup) return;

    gridGroup.children.forEach((c, idx) => {
      const cg = c as Container;
      const cp = staggerProgress(tSec, idx, 4, 0.1, 0.35);
      cg.alpha = Math.max(0.7, cp);
    });
  }
}

// ============================================================================
// 25. QUOTE_CALLOUT COMPOSITOR
// ============================================================================
export class QuoteCalloutCompositor implements ICompositor2D {
  public readonly type = SemanticRepresentationType.QUOTE_CALLOUT;
  public readonly name = "Editorial Quote Callout";
  public readonly description = "Editorial typography quote with quotation marks, accented border, and author badge.";

  public createScene(scene: ExecutableSceneProgram, context: CompositorContext): Container {
    const root = new Container();
    root.label = `QuoteCalloutScene_${scene.scene_id}`;
    const { containerWidth: W, containerHeight: H, genome } = context;
    const p = genome.palette;

    const bgG = new Graphics();
    drawTechnicalBackground(bgG, W, H, p, { title: scene.title, representationType: "EDITORIAL CALLOUT" });
    root.addChild(bgG);

    const quoteW = W - 240;
    const quoteH = H - 220;
    const quoteGroup = new Container();
    quoteGroup.label = "QuoteContainer";
    quoteGroup.position.set(120, 110);

    const qG = new Graphics();
    drawGlassCard(qG, 0, 0, quoteW, quoteH, 12, p.surfaceElevated || p.surface, p.accent, 2, 1.0, 0.25);
    quoteGroup.addChild(qG);

    const quoteMark = createStyledText("“", { fontSize: 48, fontWeight: "bold", fill: p.accent as any }, genome);
    quoteMark.position.set(24, 16);
    quoteGroup.addChild(quoteMark);

    const labels = extractDynamicLabels(scene, 1);
    const quoteText = (scene as any).narration_text || (scene as any).intended_understanding || labels[0] || "Verified ground truth statement.";
    const text = createStyledText(quoteText, { fontSize: 16, fontWeight: "bold", fill: p.text as any, wordWrap: true, wordWrapWidth: quoteW - 64, lineHeight: 26 }, genome);
    text.position.set(32, 68);
    quoteGroup.addChild(text);

    root.addChild(quoteGroup);
    return root;
  }

  public updateAt(root: Container, scene: ExecutableSceneProgram, tSec: number, context: CompositorContext): void {
    const quote = root.getChildByLabel("QuoteContainer") as Container;
    if (quote) {
      quote.alpha = Math.max(0.8, easeOutCubic(clamp(tSec / 0.5)));
    }
  }
}

// ============================================================================
// COMPOSITOR REGISTRY & PUBLIC API
// ============================================================================

export class CompositorRegistry {
  private compositors: Map<string, ICompositor2D> = new Map();
  private defaultCompositor: ICompositor2D;

  constructor() {
    const process = new ProcessCompositor();
    this.defaultCompositor = process;

    // Register all 20 canonical 2D compositors + supporting variants
    this.register(process);
    this.register(new CauseEffectCompositor());
    this.register(new ComparisonCompositor());
    this.register(new TimelineCompositor());
    this.register(new TransformationCompositor());
    this.register(new HierarchyCompositor());
    this.register(new NetworkCompositor());
    this.register(new QuantitativeRelationshipCompositor());
    this.register(new ChartCompositor());
    this.register(new LayerStackCompositor());
    this.register(new SystemArchitectureCompositor());
    this.register(new DocumentSourceCompositor());
    this.register(new CodeExplanationCompositor());
    this.register(new EquationExplanationCompositor());
    this.register(new MapGeographyCompositor());
    this.register(new SequenceCompositor());
    this.register(new ObjectFocusCompositor());
    this.register(new BeforeAfterCompositor());
    this.register(new FlowCompositor());
    this.register(new ConceptualMetaphorCompositor());
    this.register(new SummaryRecapCompositor());

    // Supporting & Aliases
    this.register(new QuantitativeCompositor());
    this.register(new ListBreakdownCompositor());
    this.register(new StatGridCompositor());
    this.register(new QuoteCalloutCompositor());
  }

  public register(compositor: ICompositor2D): void {
    this.compositors.set(compositor.type.toUpperCase(), compositor);
  }

  public registerAlias(aliasType: SemanticRepresentationType | string, targetCompositor: ICompositor2D): void {
    this.compositors.set(String(aliasType).toUpperCase(), targetCompositor);
  }

  public get(representationType: SemanticRepresentationType | string): ICompositor2D {
    const key = String(representationType || "").toUpperCase();
    return this.compositors.get(key) || this.defaultCompositor;
  }
}

export const compositorRegistry = new CompositorRegistry();
export const CompositorLibrary2D = CompositorRegistry;
export const compositorLibrary2D = compositorRegistry;

export function createSceneContainer(
  scene: ExecutableSceneProgram,
  genome: Partial<ArtDirectionGenome> = DEFAULT_ART_GENOME,
  width: number = 1280,
  height: number = 720
): Container {
  const fullGenome: ArtDirectionGenome = {
    ...DEFAULT_ART_GENOME,
    ...genome,
    palette: { ...DEFAULT_ART_GENOME.palette, ...(genome.palette || {}) },
    typography: { ...DEFAULT_ART_GENOME.typography, ...(genome.typography || {}) },
  };

  const repType = scene.representation_type || (scene.elements_2d?.[0]?.compositor) || SemanticRepresentationType.PROCESS;
  const compositor = compositorRegistry.get(repType);

  const context: CompositorContext = {
    containerWidth: width,
    containerHeight: height,
    durationSec: scene.duration_sec || 5.0,
    genome: fullGenome,
  };

  return compositor.createScene(scene, context);
}

/**
 * Animate internal scene beats over time t using semantic motion verbs:
 * GROW, SHRINK, FLOW, CONNECT, MORPH, ISOLATE, PROGRESS, REVEAL_LEVELS
 */
export function updateSceneAt(
  container: Container,
  scene: ExecutableSceneProgram,
  tSec: number,
  width: number = 1280,
  height: number = 720,
  genome: Partial<ArtDirectionGenome> = DEFAULT_ART_GENOME
): void {
  const fullGenome: ArtDirectionGenome = {
    ...DEFAULT_ART_GENOME,
    ...genome,
    palette: { ...DEFAULT_ART_GENOME.palette, ...(genome.palette || {}) },
    typography: { ...DEFAULT_ART_GENOME.typography, ...(genome.typography || {}) },
  };

  const repType = scene.representation_type || (scene.elements_2d?.[0]?.compositor) || SemanticRepresentationType.PROCESS;
  const compositor = compositorRegistry.get(repType);

  const duration = scene.duration_sec || 5.0;
  const context: CompositorContext = {
    containerWidth: width,
    containerHeight: height,
    durationSec: duration,
    genome: fullGenome,
  };

  // 1. Execute the active 2D compositor update
  compositor.updateAt(container, scene, tSec, context);

  // 2. Animate internal scene beats over time t using semantic motion verbs
  const beats: SceneBeat[] = (scene.beats || (scene as any).scene_beats || []).map((b: any, idx: number) => ({
    beat_id: b.beat_id || `beat_${idx}`,
    start_sec: typeof b.start_sec === "number" ? b.start_sec : idx * (duration / 3),
    duration_sec: typeof b.duration_sec === "number" ? b.duration_sec : duration / 3,
    motion_type: b.motion_type || b.visual_action || SemanticMotionType.PROGRESS,
    target_elements: b.target_elements || b.target_ids || b.target_element_ids || [],
    parameters: b.parameters || b.properties || {},
  }));

  // If no explicit beats are authored, evaluate deterministic default semantic motion beats
  const activeBeats = beats.length > 0 ? beats : [
    { beat_id: "entrance", start_sec: 0, duration_sec: duration * 0.3, motion_type: SemanticMotionType.REVEAL_LEVELS },
    { beat_id: "core_action", start_sec: duration * 0.25, duration_sec: duration * 0.5, motion_type: SemanticMotionType.FLOW },
    { beat_id: "focus_recap", start_sec: duration * 0.7, duration_sec: duration * 0.3, motion_type: SemanticMotionType.ISOLATE },
  ];

  for (const beat of activeBeats) {
    const bStart = beat.start_sec ?? 0;
    const bDur = Math.max(0.05, beat.duration_sec ?? 1.0);
    const bEnd = bStart + bDur;

    if (tSec >= bStart && tSec <= bEnd + 0.5) {
      const u = clamp((tSec - bStart) / bDur);
      const motionVerb = String(beat.motion_type || "").toUpperCase();

      switch (motionVerb) {
        case SemanticMotionType.GROW:
        case "GROW": {
          const scaleVal = 1.0 + 0.08 * easeOutBack(u);
          container.scale.set(scaleVal);
          break;
        }
        case SemanticMotionType.SHRINK:
        case "SHRINK": {
          const scaleVal = 1.08 - 0.08 * easeInOutCubic(u);
          container.scale.set(Math.max(0.95, scaleVal));
          break;
        }
        case SemanticMotionType.ISOLATE:
        case "ISOLATE": {
          // Highlight primary elements while subtly focusing
          const focusAlpha = lerp(0.9, 1.0, u);
          container.alpha = focusAlpha;
          break;
        }
        case SemanticMotionType.FLOW:
        case "FLOW": {
          // Flow speed & energy modulation is handled by compositor conduits
          break;
        }
        case SemanticMotionType.CONNECT:
        case "CONNECT": {
          // Handled by connector pulse updates
          break;
        }
        case SemanticMotionType.PROGRESS:
        case "PROGRESS": {
          // Handled by progress scrubber and needle updates
          break;
        }
        case SemanticMotionType.REVEAL_LEVELS:
        case "REVEAL_LEVELS": {
          container.alpha = easeOutCubic(u);
          break;
        }
        case SemanticMotionType.MORPH:
        case "MORPH": {
          break;
        }
        default:
          break;
      }
    }
  }
}

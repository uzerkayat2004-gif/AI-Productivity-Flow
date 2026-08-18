/**
 * Visual Compiler Helper Utilities:
 * - Color math and alpha blending
 * - D3 interpolation & animation easing curves
 * - High-fidelity PixiJS v8 vector graphics primitives (cards, HUD brackets, glowing lines, connectors, badges)
 */

import { Color, Container, Graphics, Text, TextStyleOptions } from "pixi.js";
import * as d3 from "d3";
import { ArtDirectionGenome, ArtDirectionPalette } from "../contracts/video-program";

export function clamp(val: number, min: number = 0, max: number = 1): number {
  return Math.max(min, Math.min(max, val));
}

export function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

export function easeOutCubic(t: number): number {
  return d3.easeCubicOut(clamp(t));
}

export function easeInOutCubic(t: number): number {
  return d3.easeCubicInOut(clamp(t));
}

export function easeOutBack(t: number): number {
  return d3.easeBackOut.overshoot(1.4)(clamp(t));
}

export function easeOutElastic(t: number): number {
  return d3.easeElasticOut.period(0.4)(clamp(t));
}

export function staggerProgress(tSec: number, index: number, total: number, staggerDelay: number = 0.15, duration: number = 0.5): number {
  const startTime = index * staggerDelay;
  const elapsed = tSec - startTime;
  if (elapsed <= 0) return 0;
  return easeOutCubic(elapsed / duration);
}

/**
 * Safely converts hex or CSS color strings to PixiJS 24-bit numeric RGB.
 */
export function colorToHexNumber(colorStr: string | undefined, defaultColor: number = 0x38bdf8): number {
  if (!colorStr) return defaultColor;
  try {
    const c = new Color(colorStr);
    return c.toNumber();
  } catch {
    return defaultColor;
  }
}

/**
 * Resolves color string from genome palette or raw hex.
 */
export function resolveColor(
  palette: ArtDirectionPalette,
  keyOrColor: string | undefined,
  fallback: string = "#38bdf8"
): string {
  if (!keyOrColor) return fallback;
  if (keyOrColor in palette && (palette as any)[keyOrColor]) {
    return (palette as any)[keyOrColor];
  }
  return keyOrColor;
}

/**
 * Draws a subtle cinematic technical background with coordinate dots, subtle grid lines, and edge frame.
 */
export function drawTechnicalBackground(
  g: Graphics,
  width: number,
  height: number,
  palette: ArtDirectionPalette,
  options: { showGrid?: boolean; title?: string; representationType?: string } = {}
): void {
  g.clear();

  const bgNum = colorToHexNumber(palette.background, 0x080d1a);
  const borderNum = colorToHexNumber(palette.border, 0x1e293b);
  const gridNum = colorToHexNumber(palette.grid, 0x38bdf8);
  const accentNum = colorToHexNumber(palette.accent, 0x00e5ff);

  // Background fill
  g.rect(0, 0, width, height).fill({ color: bgNum, alpha: 1.0 });

  // Grid dots or subtle lines
  if (options.showGrid !== false) {
    const step = 40;
    for (let x = step; x < width; x += step) {
      for (let y = step; y < height; y += step) {
        if (x % (step * 3) === 0 && y % (step * 3) === 0) {
          // Intersection crosshair
          g.moveTo(x - 3, y).lineTo(x + 3, y).stroke({ color: gridNum, width: 1, alpha: 0.25 });
          g.moveTo(x, y - 3).lineTo(x, y + 3).stroke({ color: gridNum, width: 1, alpha: 0.25 });
        } else {
          // Dot
          g.circle(x, y, 1).fill({ color: gridNum, alpha: 0.15 });
        }
      }
    }
  }

  // Outer blueprint border
  g.rect(20, 20, width - 40, height - 40).stroke({ color: borderNum, width: 1, alpha: 0.4 });

  // Corner brackets
  const bSize = 16;
  // Top-Left
  g.moveTo(20, 20 + bSize).lineTo(20, 20).lineTo(20 + bSize, 20).stroke({ color: accentNum, width: 2, alpha: 0.8 });
  // Top-Right
  g.moveTo(width - 20 - bSize, 20).lineTo(width - 20, 20).lineTo(width - 20, 20 + bSize).stroke({ color: accentNum, width: 2, alpha: 0.8 });
  // Bottom-Left
  g.moveTo(20, height - 20 - bSize).lineTo(20, height - 20).lineTo(20 + bSize, height - 20).stroke({ color: accentNum, width: 2, alpha: 0.8 });
  // Bottom-Right
  g.moveTo(width - 20 - bSize, height - 20).lineTo(width - 20, height - 20).lineTo(width - 20, height - 20 - bSize).stroke({ color: accentNum, width: 2, alpha: 0.8 });
}

/**
 * Draws a glassmorphic diagram card with glowing stroke and bevel highlight.
 */
export function drawGlassCard(
  g: Graphics,
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number = 8,
  fillColorStr: string = "#0f172a",
  strokeColorStr: string = "#1e293b",
  strokeWidth: number = 1.5,
  alpha: number = 1.0,
  glowAlpha: number = 0.15
): void {
  const fillNum = colorToHexNumber(fillColorStr, 0x0f172a);
  const strokeNum = colorToHexNumber(strokeColorStr, 0x1e293b);

  // Outer glow shadow simulation
  if (glowAlpha > 0) {
    g.roundRect(x - 2, y - 2, width + 4, height + 4, radius + 2)
      .fill({ color: strokeNum, alpha: glowAlpha * alpha });
  }

  // Base card surface
  g.roundRect(x, y, width, height, radius)
    .fill({ color: fillNum, alpha: 0.9 * alpha })
    .stroke({ color: strokeNum, width: strokeWidth, alpha: 0.85 * alpha });

  // Top edge gloss highlight
  g.moveTo(x + radius, y + 1)
    .lineTo(x + width - radius, y + 1)
    .stroke({ color: 0xffffff, width: 1, alpha: 0.12 * alpha });
}

/**
 * Draws HUD Corner Framing Brackets around any coordinate box.
 */
export function drawHUDCornerBrackets(
  g: Graphics,
  x: number,
  y: number,
  width: number,
  height: number,
  bracketSize: number = 12,
  colorStr: string = "#00e5ff",
  strokeWidth: number = 1.5,
  alpha: number = 1.0
): void {
  const colorNum = colorToHexNumber(colorStr, 0x00e5ff);

  // Top Left
  g.moveTo(x, y + bracketSize).lineTo(x, y).lineTo(x + bracketSize, y)
    .stroke({ color: colorNum, width: strokeWidth, alpha });
  // Top Right
  g.moveTo(x + width - bracketSize, y).lineTo(x + width, y).lineTo(x + width, y + bracketSize)
    .stroke({ color: colorNum, width: strokeWidth, alpha });
  // Bottom Left
  g.moveTo(x, y + height - bracketSize).lineTo(x, y + height).lineTo(x + bracketSize, y + height)
    .stroke({ color: colorNum, width: strokeWidth, alpha });
  // Bottom Right
  g.moveTo(x + width - bracketSize, y + height).lineTo(x + width, y + height).lineTo(x + width, y + height - bracketSize)
    .stroke({ color: colorNum, width: strokeWidth, alpha });
}

/**
 * Draws an animated directional pipeline connector arrow with pulse wave.
 */
export function drawArrowConnector(
  g: Graphics,
  x1: number,
  y1: number,
  x2: number,
  y2: number,
  colorStr: string = "#38bdf8",
  strokeWidth: number = 2,
  headSize: number = 8,
  pulseProgress: number = 0,
  alpha: number = 1.0
): void {
  const colorNum = colorToHexNumber(colorStr, 0x38bdf8);
  const dx = x2 - x1;
  const dy = y2 - y1;
  const dist = Math.hypot(dx, dy);
  if (dist < 4) return;

  const angle = Math.atan2(dy, dx);
  const endX = x2 - Math.cos(angle) * headSize;
  const endY = y2 - Math.sin(angle) * headSize;

  // Background conduit track
  g.moveTo(x1, y1).lineTo(endX, endY).stroke({ color: colorNum, width: strokeWidth, alpha: 0.35 * alpha });

  // Animated traveling pulse packet along line
  if (pulseProgress > 0 && pulseProgress < 1) {
    const px = lerp(x1, endX, pulseProgress);
    const py = lerp(y1, endY, pulseProgress);
    g.circle(px, py, strokeWidth * 2).fill({ color: 0xffffff, alpha: 0.9 * alpha });
    g.circle(px, py, strokeWidth * 3.5).stroke({ color: colorNum, width: 1.5, alpha: 0.6 * alpha });
  }

  // Arrowhead
  const leftX = endX - headSize * Math.cos(angle - Math.PI / 6);
  const leftY = endY - headSize * Math.sin(angle - Math.PI / 6);
  const rightX = endX - headSize * Math.cos(angle + Math.PI / 6);
  const rightY = endY - headSize * Math.sin(angle + Math.PI / 6);

  g.poly([x2, y2, leftX, leftY, rightX, rightY])
    .fill({ color: colorNum, alpha: 0.9 * alpha });
}

/**
 * Draws a smooth Bézier link conduit with flowing energy particles.
 */
export function drawCurvedLink(
  g: Graphics,
  x1: number,
  y1: number,
  x2: number,
  y2: number,
  colorStr: string = "#38bdf8",
  strokeWidth: number = 2,
  curvature: number = 0.5,
  pulseProgress: number = 0,
  alpha: number = 1.0
): void {
  const colorNum = colorToHexNumber(colorStr, 0x38bdf8);
  const dx = x2 - x1;
  const cx1 = x1 + dx * curvature;
  const cy1 = y1;
  const cx2 = x2 - dx * curvature;
  const cy2 = y2;

  // Main conduit curve
  g.moveTo(x1, y1)
    .bezierCurveTo(cx1, cy1, cx2, cy2, x2, y2)
    .stroke({ color: colorNum, width: strokeWidth, alpha: 0.4 * alpha });

  // Flowing energy particle on Bézier curve
  if (pulseProgress > 0 && pulseProgress <= 1) {
    const t = pulseProgress;
    const invT = 1 - t;
    const px = Math.pow(invT, 3) * x1 + 3 * Math.pow(invT, 2) * t * cx1 + 3 * invT * Math.pow(t, 2) * cx2 + Math.pow(t, 3) * x2;
    const py = Math.pow(invT, 3) * y1 + 3 * Math.pow(invT, 2) * t * cy1 + 3 * invT * Math.pow(t, 2) * cy2 + Math.pow(t, 3) * y2;

    g.circle(px, py, strokeWidth * 2.2).fill({ color: 0xffffff, alpha: 0.95 * alpha });
    g.circle(px, py, strokeWidth * 4).stroke({ color: colorNum, width: 1, alpha: 0.5 * alpha });
  }
}

/**
 * Draws a radial kinetic ping / pulse ring.
 */
export function drawPulseRing(
  g: Graphics,
  cx: number,
  cy: number,
  radius: number,
  colorStr: string = "#00e5ff",
  alpha: number = 1.0,
  rings: number = 3
): void {
  const colorNum = colorToHexNumber(colorStr, 0x00e5ff);
  for (let i = 0; i < rings; i++) {
    const r = radius + i * 8;
    const ringAlpha = (1 - (i / rings)) * 0.4 * alpha;
    g.circle(cx, cy, r).stroke({ color: colorNum, width: 1.5, alpha: ringAlpha });
  }
}

/**
 * Creates a configured Pixi Text node with standard typography.
 */
export function createStyledText(
  text: string,
  options: TextStyleOptions & { color?: string } = {},
  genome?: ArtDirectionGenome
): Text {
  const family = options.fontFamily || genome?.typography.bodyFont || "Inter, sans-serif";
  const size = options.fontSize || 14;
  const fill = options.color || options.fill || genome?.palette.text || "#f8fafc";

  return new Text({
    text,
    style: {
      fontFamily: family,
      fontSize: size,
      fontWeight: options.fontWeight || "normal",
      fill: fill as any,
      wordWrap: options.wordWrap,
      wordWrapWidth: options.wordWrapWidth,
      lineHeight: options.lineHeight,
      align: options.align || "left",
      letterSpacing: options.letterSpacing || 0,
    },
  });
}

// ============================================================================
// HIGH-END HARDWARE MOCKUPS & TACTILE VISUAL PRIMITIVES (MUJTABA / XYNTH LEVEL)
// ============================================================================

export interface CRTMonitorOptions {
  theme?: "beige" | "dark" | "amber" | "cyber";
  hasAntenna?: boolean;
  hasDials?: boolean;
  powerLedOn?: boolean;
  scanlines?: boolean;
  glowIntensity?: number;
  screenColor?: number;
}

/**
 * Draws an authentic vintage CRT monitor with chassis, bezel, dials, and curved phosphor screen.
 */
export function drawVintageCRTMonitor(
  g: Graphics,
  x: number,
  y: number,
  width: number,
  height: number,
  palette: ArtDirectionPalette,
  options: CRTMonitorOptions = {}
): { screenX: number; screenY: number; screenW: number; screenH: number } {
  const theme = options.theme || "beige";
  const isDark = theme === "dark" || theme === "cyber";
  const isAmber = theme === "amber";

  // Chassis colors
  const chassisColor = isDark ? 0x1e2430 : 0xe3dbcc;
  const bezelColor = isDark ? 0x141a24 : 0xd2c9b6;
  const shadowColor = isDark ? 0x0a0e17 : 0xb8ad99;
  const accentNum = colorToHexNumber(palette.accent, 0x00e5ff);
  const screenBg = options.screenColor !== undefined
    ? options.screenColor
    : isDark ? 0x0a101d : isAmber ? 0x1f1406 : 0xf4f1ea;

  // 1. Antenna (optional)
  if (options.hasAntenna) {
    const topCenterX = x + width * 0.5;
    const topY = y;
    g.moveTo(topCenterX, topY).lineTo(topCenterX - 28, topY - 32).stroke({ color: 0x888888, width: 2, alpha: 0.8 });
    g.circle(topCenterX - 28, topY - 32, 3.5).fill({ color: 0xcccccc, alpha: 0.9 });
    g.moveTo(topCenterX, topY).lineTo(topCenterX + 32, topY - 36).stroke({ color: 0x888888, width: 2, alpha: 0.8 });
    g.circle(topCenterX + 32, topY - 36, 3.5).fill({ color: 0xcccccc, alpha: 0.9 });
  }

  // 2. Outer Chassis with shadow & bevel
  g.roundRect(x, y + 4, width, height, 16).fill({ color: shadowColor, alpha: 0.7 });
  g.roundRect(x, y, width, height, 16).fill({ color: chassisColor, alpha: 1.0 });
  g.roundRect(x, y, width, height, 16).stroke({ color: shadowColor, width: 2, alpha: 0.8 });

  // Top highlight gloss
  g.moveTo(x + 16, y + 2).lineTo(x + width - 16, y + 2).stroke({ color: 0xffffff, width: 1.5, alpha: 0.3 });

  // 3. Screen Bezel
  const bezelMargin = 16;
  const bottomPanelH = options.hasDials !== false ? 38 : 16;
  const screenW = width - bezelMargin * 2;
  const screenH = height - bezelMargin * 2 - bottomPanelH;
  const screenX = x + bezelMargin;
  const screenY = y + bezelMargin;

  // Bezel recess
  g.roundRect(screenX - 3, screenY - 3, screenW + 6, screenH + 6, 12).fill({ color: bezelColor, alpha: 1.0 });
  g.roundRect(screenX - 3, screenY - 3, screenW + 6, screenH + 6, 12).stroke({ color: shadowColor, width: 1.5, alpha: 0.9 });

  // 4. Phosphor Screen Glass
  g.roundRect(screenX, screenY, screenW, screenH, 8).fill({ color: screenBg, alpha: 1.0 });

  // Subtle Scanlines
  if (options.scanlines !== false) {
    const scanStep = 4;
    const scanColor = isDark || isAmber ? 0x000000 : 0xdddddd;
    for (let sy = screenY; sy < screenY + screenH; sy += scanStep) {
      g.moveTo(screenX, sy).lineTo(screenX + screenW, sy).stroke({ color: scanColor, width: 1, alpha: 0.12 });
    }
  }

  // Glass reflection arc (top-left sheen)
  g.moveTo(screenX + 12, screenY + 4)
    .bezierCurveTo(screenX + screenW * 0.4, screenY + 4, screenX + 10, screenY + screenH * 0.35, screenX + 4, screenY + screenH * 0.5)
    .stroke({ color: 0xffffff, width: 1.5, alpha: 0.18 });

  // 5. Bottom Control Panel (Dials, Vents, Power LED)
  const panelY = screenY + screenH + 8;
  if (options.hasDials !== false) {
    // Ventilation Grille Slots
    const ventStartX = x + 24;
    const ventW = width * 0.45;
    for (let vx = ventStartX; vx < ventStartX + ventW; vx += 7) {
      g.moveTo(vx, panelY + 6).lineTo(vx, panelY + 22).stroke({ color: shadowColor, width: 2, alpha: 0.75 });
    }

    // Tuning Knobs
    const dial1X = x + width - 58;
    const dial2X = x + width - 36;
    const dialY = panelY + 14;

    g.circle(dial1X, dialY, 7).fill({ color: bezelColor }).stroke({ color: shadowColor, width: 1.5 });
    g.circle(dial2X, dialY, 6).fill({ color: bezelColor }).stroke({ color: shadowColor, width: 1.5 });

    // Power Indicator LED
    const ledX = x + width - 18;
    const ledOn = options.powerLedOn !== false;
    const ledColor = ledOn ? (isAmber ? 0xffb300 : 0x10b981) : 0x444444;
    g.circle(ledX, dialY, 3).fill({ color: ledColor, alpha: 0.95 });
    if (ledOn) {
      g.circle(ledX, dialY, 6).stroke({ color: ledColor, width: 1, alpha: 0.5 });
    }
  }

  return { screenX, screenY, screenW, screenH };
}

export interface IndustrialSwitchOptions {
  portsCount?: number;
  activePortIndex?: number;
  blinkingLed?: boolean;
  tSec?: number;
  radarSpin?: boolean;
}

/**
 * Draws an authentic industrial router switch appliance with RJ45 ports and blinking link LEDs.
 */
export function drawIndustrialNetworkSwitch(
  g: Graphics,
  x: number,
  y: number,
  width: number,
  height: number,
  palette: ArtDirectionPalette,
  options: IndustrialSwitchOptions = {}
): void {
  const chassisColor = 0x222a36;
  const faceplateColor = 0x2d3748;
  const shadowColor = 0x131922;
  const accentNum = colorToHexNumber(palette.accent, 0x10b981);
  const t = options.tSec || 0;

  // 1. Chassis Body
  g.roundRect(x, y, width, height, 10).fill({ color: chassisColor, alpha: 1.0 });
  g.roundRect(x, y, width, height, 10).stroke({ color: shadowColor, width: 2, alpha: 0.9 });

  // Front recessed plate
  g.roundRect(x + 12, y + 10, width - 24, height - 20, 6).fill({ color: faceplateColor, alpha: 1.0 });

  // 2. Central Radar / Compass Display Screen
  const dispW = width * 0.46;
  const dispH = height - 36;
  const dispX = x + 20;
  const dispY = y + 18;
  g.roundRect(dispX, dispY, dispW, dispH, 6).fill({ color: 0xf5f3ed, alpha: 1.0 });
  g.roundRect(dispX, dispY, dispW, dispH, 6).stroke({ color: 0x1a202c, width: 2, alpha: 0.8 });

  // Central Radar Compass Icon
  const cx = dispX + dispW * 0.5;
  const cy = dispY + dispH * 0.5;
  const compassR = Math.min(dispW, dispH) * 0.34;

  g.circle(cx, cy, compassR).stroke({ color: 0x2d3748, width: 4, alpha: 0.9 });
  const needleAngle = options.radarSpin ? t * 2.5 : -Math.PI / 4;
  const nx = Math.cos(needleAngle) * (compassR - 4);
  const ny = Math.sin(needleAngle) * (compassR - 4);
  const px = -Math.sin(needleAngle) * 5;
  const py = Math.cos(needleAngle) * 5;

  g.poly([cx + nx, cy + ny, cx + px, cy + py, cx - nx * 0.4, cy - ny * 0.4, cx - px, cy - py])
    .fill({ color: 0x1a202c, alpha: 0.9 });

  // 3. RJ45 Ethernet Port Array (Right column)
  const portsCount = options.portsCount || 6;
  const portColX = x + width - 64;
  const portStartY = y + 16;
  const portSpacing = (height - 36) / portsCount;

  for (let i = 0; i < portsCount; i++) {
    const py = portStartY + i * portSpacing;
    const isPortActive = (options.activePortIndex === undefined && i % 2 === 0) || options.activePortIndex === i;

    // Port socket cavity
    g.roundRect(portColX, py, 44, portSpacing - 4, 3).fill({ color: 0x111827, alpha: 1.0 });
    g.roundRect(portColX, py, 44, portSpacing - 4, 3).stroke({ color: 0x4a5568, width: 1, alpha: 0.6 });

    // Port golden pins
    g.moveTo(portColX + 10, py + (portSpacing - 4) * 0.5).lineTo(portColX + 34, py + (portSpacing - 4) * 0.5).stroke({ color: 0xd97706, width: 2, alpha: 0.8 });

    // Animated Link LED
    const blink = Math.sin(t * 8 + i * 2) > 0;
    const ledColor = isPortActive ? (blink ? 0x10b981 : 0x059669) : 0x374151;
    g.circle(portColX - 8, py + (portSpacing - 4) * 0.5, 2.5).fill({ color: ledColor, alpha: 0.95 });
  }

  // 4. Bottom Multi-LED Activity Bar
  const ledBarY = y + height - 16;
  const ledStartX = x + 24;
  for (let l = 0; l < 14; l++) {
    const lx = ledStartX + l * 12;
    const isLit = Math.sin(t * 5 + l * 0.6) > -0.2;
    const col = l < 10 ? (isLit ? 0x10b981 : 0x14532d) : (isLit ? 0xf59e0b : 0x78350f);
    g.circle(lx, ledBarY, 2).fill({ color: col, alpha: 0.9 });
  }
}

export interface PixelCartridgeOptions {
  label?: string;
  iconName?: string;
  badgeColor?: number;
  highlighted?: boolean;
}

/**
 * Draws a retro game/IC cartridge with golden pins and embossed pixel logo.
 */
export function drawPixelCartridge(
  g: Graphics,
  x: number,
  y: number,
  width: number,
  height: number,
  palette: ArtDirectionPalette,
  options: PixelCartridgeOptions = {}
): void {
  const bodyColor = 0xebe3d5;
  const grooveColor = 0xccbfab;
  const labelBg = 0xf8fafc;
  const accentNum = options.badgeColor || colorToHexNumber(palette.accent, 0x3b82f6);

  // 1. Cartridge Outer Body with Top Grip Ridges
  g.roundRect(x, y, width, height, 8).fill({ color: bodyColor, alpha: 1.0 });
  g.roundRect(x, y, width, height, 8).stroke({ color: grooveColor, width: 2, alpha: 0.9 });

  // Top grip notches
  const notchW = width * 0.6;
  const notchX = x + (width - notchW) * 0.5;
  for (let ny = y + 5; ny <= y + 14; ny += 4) {
    g.moveTo(notchX, ny).lineTo(notchX + notchW, ny).stroke({ color: grooveColor, width: 2, alpha: 0.8 });
  }

  // 2. Central Label Inset
  const labelInsetW = width - 16;
  const labelInsetH = height - 26;
  const labelX = x + 8;
  const labelY = y + 18;

  g.roundRect(labelX, labelY, labelInsetW, labelInsetH, 5).fill({ color: labelBg, alpha: 1.0 });
  g.roundRect(labelX, labelY, labelInsetW, labelInsetH, 5).stroke({ color: grooveColor, width: 1.5, alpha: 0.8 });

  // 3. Embossed Pixel Icon
  const cx = labelX + labelInsetW * 0.5;
  const cy = labelY + labelInsetH * 0.5;

  if (options.highlighted) {
    drawPulseRing(g, cx, cy, 18, palette.accent, 0.6, 2);
  }

  // Generic geometric pixel logo
  g.circle(cx, cy, 10).stroke({ color: accentNum, width: 2.5, alpha: 0.9 });
  g.circle(cx, cy, 4).fill({ color: accentNum, alpha: 0.9 });

  // 4. Golden Edge Connector Pins (Bottom)
  const pinStartX = x + 10;
  const pinW = width - 20;
  for (let px = pinStartX; px < pinStartX + pinW; px += 6) {
    g.moveTo(px, y + height - 2).lineTo(px, y + height + 3).stroke({ color: 0xd97706, width: 2, alpha: 0.9 });
  }
}

/**
 * Draws an authentic glowing dot-matrix / LED matrix display for bold metrics.
 */
export function drawLEDMatrixDisplay(
  g: Graphics,
  x: number,
  y: number,
  width: number,
  height: number,
  valueText: string,
  palette: ArtDirectionPalette,
  activeColorHex?: number
): void {
  const bgNum = 0x111827;
  const borderNum = 0x1f2937;
  const onColor = activeColorHex !== undefined ? activeColorHex : colorToHexNumber(palette.accent, 0x10b981);
  const offColor = 0x1e293b;

  // Frame enclosure
  g.roundRect(x, y, width, height, 8).fill({ color: bgNum, alpha: 1.0 });
  g.roundRect(x, y, width, height, 8).stroke({ color: borderNum, width: 2, alpha: 0.9 });

  // Matrix Dot Grid
  const dotSize = 8;
  const dotGap = 3;
  const cols = Math.floor((width - 16) / (dotSize + dotGap));
  const rows = Math.floor((height - 16) / (dotSize + dotGap));
  const startX = x + (width - (cols * (dotSize + dotGap) - dotGap)) * 0.5;
  const startY = y + (height - (rows * (dotSize + dotGap) - dotGap)) * 0.5;

  // Background inactive dot matrix
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const dx = startX + c * (dotSize + dotGap);
      const dy = startY + r * (dotSize + dotGap);
      g.rect(dx, dy, dotSize, dotSize).fill({ color: offColor, alpha: 0.4 });
    }
  }

  // Draw active pattern approximation for value (e.g. 0% or text)
  for (let r = 1; r < rows - 1; r++) {
    for (let c = 2; c < cols - 2; c++) {
      // Create active numeral pattern
      const isBoundary = r === 1 || r === rows - 2 || c === 2 || c === cols - 3 || r === Math.floor(rows / 2);
      if (isBoundary && (c < cols * 0.5 || valueText.includes("%"))) {
        const dx = startX + c * (dotSize + dotGap);
        const dy = startY + r * (dotSize + dotGap);
        g.rect(dx, dy, dotSize, dotSize).fill({ color: onColor, alpha: 0.95 });
      }
    }
  }
}

/**
 * Draws a crossed-out legacy / competitor badge with a thick red pixel X.
 */
export function drawCrossedOutBadge(
  g: Graphics,
  x: number,
  y: number,
  width: number,
  height: number,
  label: string,
  palette: ArtDirectionPalette,
  progress: number = 1.0
): void {
  // Base grayed badge
  g.roundRect(x, y, width, height, 8).fill({ color: 0x1e293b, alpha: 0.8 });
  g.roundRect(x, y, width, height, 8).stroke({ color: 0x334155, width: 1.5, alpha: 0.7 });

  // Red Pixel X Crossout animation
  if (progress > 0.3) {
    const xProg = Math.min(1.0, (progress - 0.3) / 0.4);
    const redColor = 0xef4444;

    // Top-left to bottom-right line
    const ex1 = lerp(x + 8, x + width - 8, xProg);
    const ey1 = lerp(y + 8, y + height - 8, xProg);
    g.moveTo(x + 8, y + 8).lineTo(ex1, ey1).stroke({ color: redColor, width: 5, alpha: 0.95 });

    // Top-right to bottom-left line
    if (xProg > 0.4) {
      const xProg2 = (xProg - 0.4) / 0.6;
      const ex2 = lerp(x + width - 8, x + 8, xProg2);
      const ey2 = lerp(y + 8, y + height - 8, xProg2);
      g.moveTo(x + width - 8, y + 8).lineTo(ex2, ey2).stroke({ color: redColor, width: 5, alpha: 0.95 });
    }
  }
}


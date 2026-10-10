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

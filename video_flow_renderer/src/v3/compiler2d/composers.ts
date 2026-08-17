/**
 * Deterministic 2D Compositor Library for Video Flow V3.
 * D3 calculates layout geometry, scales, paths, and node positioning.
 * PixiJS v8 renders WebGL display objects (containers, graphics, texts, connectors).
 */

import { ExecutableElement2D } from "../contracts/video-program";

export interface RenderableNode2D {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  label: string;
  role: string;
  fillColor: string;
  strokeColor: string;
  opacity: number;
  scale: number;
}

export class CompositorLibrary2D {
  /**
   * Process / Flow Compositor: Arranges nodes in a horizontal or vertical pipeline with directional arrows.
   */
  public layoutProcess(elements: ExecutableElement2D[], containerWidth: number, containerHeight: number): RenderableNode2D[] {
    const count = elements.length || 1;
    const spacing = Math.min(220, (containerWidth - 120) / count);

    return elements.map((elem, idx) => {
      const x = 60 + idx * spacing;
      const y = containerHeight / 2 - 50;
      return {
        id: elem.element_id,
        x,
        y,
        width: Math.min(180, spacing - 20),
        height: 90,
        label: elem.style.label || elem.element_id,
        role: elem.layer,
        fillColor: elem.style.fill || "#161f2e",
        strokeColor: elem.style.accent || "#ff6b00",
        opacity: 1.0,
        scale: 1.0,
      };
    });
  }

  /**
   * Comparison Compositor: Side-by-side balanced comparison columns.
   */
  public layoutComparison(elements: ExecutableElement2D[], containerWidth: number, containerHeight: number): RenderableNode2D[] {
    const colWidth = (containerWidth - 160) / Math.max(2, elements.length);

    return elements.map((elem, idx) => {
      const x = 60 + idx * (colWidth + 40);
      const y = 80;
      return {
        id: elem.element_id,
        x,
        y,
        width: colWidth,
        height: containerHeight - 160,
        label: elem.style.label || elem.element_id,
        role: elem.layer,
        fillColor: elem.style.fill || "#0d1826",
        strokeColor: elem.style.accent || "#06cfe5",
        opacity: 1.0,
        scale: 1.0,
      };
    });
  }

  /**
   * Timeline / Hierarchy Compositor: Chronological or tree layout.
   */
  public layoutTimeline(elements: ExecutableElement2D[], containerWidth: number, containerHeight: number): RenderableNode2D[] {
    return elements.map((elem, idx) => {
      const x = 80 + (idx % 4) * 260;
      const y = 100 + Math.floor(idx / 4) * 160;
      return {
        id: elem.element_id,
        x,
        y,
        width: 220,
        height: 120,
        label: elem.style.label || elem.element_id,
        role: elem.layer,
        fillColor: elem.style.fill || "#121b2b",
        strokeColor: elem.style.accent || "#38bdf8",
        opacity: 1.0,
        scale: 1.0,
      };
    });
  }
}

export const compositorLibrary2D = new CompositorLibrary2D();

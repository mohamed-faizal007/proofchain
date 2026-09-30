/** PDF-points → CSS-pixel math for the highlight overlay (07 "Highlight overlay").
 * Backend bboxes are `[x0, y0, x1, y1]` in PDF points with a TOP-LEFT origin (PyMuPDF),
 * so no Y flip is needed. Page rotation and CropBox offsets are NOT handled; the viewer
 * refuses to draw boxes on rotated pages instead. */

export type Bbox = [number, number, number, number];
export type HighlightType = "MODIFIED" | "INSERTED" | "DELETED";

export interface PageHighlight {
  id: string;
  type: HighlightType;
  /** 0-based page index (same as the backend's `page`). */
  page: number;
  bbox: Bbox;
}

export interface Rect {
  left: number;
  top: number;
  width: number;
  height: number;
}

/** CSS px per PDF point when a page of `pageWidthPts` is rendered `renderedWidth` px wide. */
export function fitScale(renderedWidth: number, pageWidthPts: number): number {
  if (!Number.isFinite(renderedWidth) || !Number.isFinite(pageWidthPts) || pageWidthPts <= 0) {
    return 0;
  }
  return renderedWidth / pageWidthPts;
}

/** Converts a bbox to a CSS rect at `scale`, or null when it can't be drawn sensibly. */
export function bboxToRect(bbox: Bbox, scale: number): Rect | null {
  if (!Number.isFinite(scale) || scale <= 0 || !bbox.every(Number.isFinite)) return null;
  const [ax, ay, bx, by] = bbox;
  const width = Math.abs(bx - ax) * scale;
  const height = Math.abs(by - ay) * scale;
  if (width === 0 || height === 0) return null;
  return { left: Math.min(ax, bx) * scale, top: Math.min(ay, by) * scale, width, height };
}

export function highlightsForPage(highlights: PageHighlight[], pageIndex: number): PageHighlight[] {
  return highlights.filter((h) => h.page === pageIndex);
}

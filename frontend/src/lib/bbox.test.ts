import { bboxToRect, fitScale, highlightsForPage, type Bbox, type PageHighlight } from "./bbox";

describe("fitScale", () => {
  it("is renderedWidth / pageWidthPts", () => {
    expect(fitScale(1200, 600)).toBe(2);
    expect(fitScale(300, 600)).toBe(0.5);
  });

  it("returns 0 for a non-positive or non-finite page width instead of Infinity/NaN", () => {
    expect(fitScale(800, 0)).toBe(0);
    expect(fitScale(800, -5)).toBe(0);
    expect(fitScale(800, Number.NaN)).toBe(0);
    expect(fitScale(Number.NaN, 600)).toBe(0);
  });
});

describe("bboxToRect", () => {
  const bbox: Bbox = [72, 100, 172, 130];

  it("maps top-left-origin PDF points to CSS px unchanged at scale 1 (no Y flip)", () => {
    expect(bboxToRect(bbox, 1)).toEqual({ left: 72, top: 100, width: 100, height: 30 });
  });

  it("scales every field by the same factor (zoom / resize)", () => {
    expect(bboxToRect(bbox, 2)).toEqual({ left: 144, top: 200, width: 200, height: 60 });
    expect(bboxToRect(bbox, 0.5)).toEqual({ left: 36, top: 50, width: 50, height: 15 });
  });

  it("normalises an inverted box (x1 < x0 / y1 < y0) to a positive width/height", () => {
    expect(bboxToRect([172, 130, 72, 100], 1)).toEqual({
      left: 72,
      top: 100,
      width: 100,
      height: 30,
    });
  });

  it("returns null for NaN/Infinity coordinates, a zero scale, or a zero-area box", () => {
    expect(bboxToRect([Number.NaN, 0, 10, 10], 1)).toBeNull();
    expect(bboxToRect([0, 0, Number.POSITIVE_INFINITY, 10], 1)).toBeNull();
    expect(bboxToRect(bbox, 0)).toBeNull();
    expect(bboxToRect([10, 10, 10, 40], 1)).toBeNull();
  });
});

describe("highlightsForPage", () => {
  const h = (id: string, page: number): PageHighlight => ({
    id,
    type: "MODIFIED",
    page,
    bbox: [0, 0, 1, 1],
  });

  it("filters by 0-based page index", () => {
    const all = [h("a", 0), h("b", 1), h("c", 1)];
    expect(highlightsForPage(all, 1).map((x) => x.id)).toEqual(["b", "c"]);
    expect(highlightsForPage(all, 2)).toEqual([]);
  });
});

import type { ChangeRegion } from "../api/types";
import { candidateHighlights, referenceHighlights } from "./regions";

const region = (over: Partial<ChangeRegion>): ChangeRegion => ({
  id: "r1",
  type: "MODIFIED",
  ref_chunk_id: null,
  cand_chunk_id: null,
  ref_page: null,
  cand_page: null,
  ref_text: null,
  cand_text: null,
  ref_bbox: null,
  cand_bbox: null,
  section_id: null,
  section_title: null,
  ...over,
});

describe("region -> highlight mapping", () => {
  const modified = region({
    ref_page: 1,
    cand_page: 2,
    ref_bbox: [1, 2, 3, 4],
    cand_bbox: [10, 20, 30, 40],
  });

  it("reference side uses ref_page/ref_bbox only", () => {
    expect(referenceHighlights([modified])).toEqual([
      { id: "r1", type: "MODIFIED", page: 1, bbox: [1, 2, 3, 4] },
    ]);
  });

  it("candidate side uses cand_page/cand_bbox only", () => {
    expect(candidateHighlights([modified])).toEqual([
      { id: "r1", type: "MODIFIED", page: 2, bbox: [10, 20, 30, 40] },
    ]);
  });

  it("INSERTED shows on the candidate side only, DELETED on the reference side only", () => {
    const inserted = region({ id: "i", type: "INSERTED", cand_page: 0, cand_bbox: [1, 1, 5, 5] });
    const deleted = region({ id: "d", type: "DELETED", ref_page: 0, ref_bbox: [2, 2, 6, 6] });
    expect(referenceHighlights([inserted, deleted]).map((h) => h.id)).toEqual(["d"]);
    expect(candidateHighlights([inserted, deleted]).map((h) => h.id)).toEqual(["i"]);
  });

  it("a redacted (anonymous) region with pages but no bbox yields no highlight", () => {
    const redacted = region({ ref_page: 0, cand_page: 0 });
    expect(referenceHighlights([redacted])).toEqual([]);
    expect(candidateHighlights([redacted])).toEqual([]);
  });

  it("page 0 is a valid page (not treated as missing)", () => {
    const r = region({ ref_page: 0, ref_bbox: [1, 1, 2, 2] });
    expect(referenceHighlights([r])[0]?.page).toBe(0);
  });
});

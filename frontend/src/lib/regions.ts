import type { ChangeRegion } from "../api/types";
import type { PageHighlight } from "./bbox";

/** Reference-side highlights: `ref_page` / `ref_bbox` ONLY. The reference and candidate PDFs can
 * have different page counts, so the two sides must never share a page index. Regions without a
 * reference location (INSERTED) or with a redacted bbox (anonymous report) yield nothing. */
export function referenceHighlights(regions: ChangeRegion[]): PageHighlight[] {
  return regions.flatMap((r) =>
    r.ref_page != null && r.ref_bbox
      ? [{ id: r.id, type: r.type, page: r.ref_page, bbox: r.ref_bbox }]
      : [],
  );
}

/** Candidate-side highlights: `cand_page` / `cand_bbox` ONLY. */
export function candidateHighlights(regions: ChangeRegion[]): PageHighlight[] {
  return regions.flatMap((r) =>
    r.cand_page != null && r.cand_bbox
      ? [{ id: r.id, type: r.type, page: r.cand_page, bbox: r.cand_bbox }]
      : [],
  );
}

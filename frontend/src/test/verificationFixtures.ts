import type {
  AnalysisItem,
  ChainCheck,
  LocalizationResult,
  ChangeRegion,
  RevisionSnapshot,
  VerificationReport,
} from "../api/types";

export const region = (over: Partial<ChangeRegion> & { id: string }): ChangeRegion => ({
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

export const REFERENCE: RevisionSnapshot = {
  id: "rev-ref",
  revision_no: 5,
  version_no: 3,
  status: "APPROVED",
  anchored_tx: `0x${"ab".repeat(32)}`,
  revocation: null,
};

export const CHAIN_OK: ChainCheck = {
  performed: true,
  ok: true,
  reason: null,
  mismatches: [],
  tx_hash: REFERENCE.anchored_tx,
  explorer_url: null,
};

export function localizationWith(regions: ChangeRegion[]): LocalizationResult {
  return {
    status: "CHANGED",
    regions,
    changed_pages_ref: [0],
    changed_pages_cand: [0],
    method: "ALIGNMENT",
    hash_comparisons: 12,
    stats: {},
  };
}

export function makeReport(over: Partial<VerificationReport> = {}): VerificationReport {
  return {
    id: "ver-1",
    at: "2026-09-30T10:00:00Z",
    verdict: "TAMPERED",
    summary: "3 changes on pages 2 and 3 vs approved revision 5 (v3)",
    document: { id: "doc-1", title: "Lease Agreement" },
    matched_revision: null,
    reference_revision: REFERENCE,
    no_reference_reason: null,
    steps: [
      { name: "FILE_HASH", status: "FAIL" },
      { name: "TEXT_ROOT", status: "FAIL" },
      { name: "LOCALIZATION", status: "DONE", detail: "ALIGNMENT, 12 comparisons" },
      { name: "AUTHORIZATION", status: "FAIL", detail: "No approved revision matches" },
      { name: "CHAIN_CHECK", status: "PASS" },
      { name: "SEMANTIC_ANALYSIS", status: "DONE" },
    ],
    candidate: {
      filename: "lease-copy.pdf",
      file_hash: "a".repeat(64),
      text_root: "b".repeat(64),
      page_count: 3,
    },
    localization: localizationWith([
      region({
        id: "r1",
        ref_page: 0,
        cand_page: 0,
        ref_bbox: [1, 1, 2, 2],
        cand_bbox: [1, 1, 2, 2],
      }),
    ]),
    analysis: null,
    chain_check: CHAIN_OK,
    timings_ms: { total: 800 },
    ...over,
  };
}

export const ANALYSIS_R1: AnalysisItem = {
  region_id: "r1",
  primary_category: "AMOUNT_CHANGE",
  categories: ["AMOUNT_CHANGE"],
  severity: "HIGH",
  similarity: 0.94,
  entity_changes: [{ type: "MONEY", before: "₹50,000", after: "₹80,000" }],
  token_diff: [
    { op: "equal", before: ["Rent", "is"], after: ["Rent", "is"] },
    { op: "replace", before: ["₹50,000"], after: ["₹80,000"] },
  ],
  explanation: "The amount changed from ₹50,000 to ₹80,000 in Section 4 (Payment Terms).",
  method: "RULES",
};

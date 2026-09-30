/** API types mirroring docs/04_API_SPEC.md. Extended as endpoints are consumed. */

export interface ErrorEnvelope {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

export type Role = "ISSUER" | "APPROVER" | "VERIFIER" | "ADMIN";

export interface User {
  id: string;
  email: string;
  full_name: string;
  roles: Role[];
  is_active: boolean;
  created_at: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  full_name: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  user: User;
}

export type DocType = "CONTRACT" | "CERTIFICATE" | "INVOICE" | "LEGAL" | "OTHER";

export type RevisionStatus = "PENDING" | "APPROVED" | "REJECTED" | "REVOKED";

export type AnchorStatus = "NOT_REQUESTED" | "ANCHORING" | "ANCHORED" | "FAILED";

export interface Anchor {
  status: AnchorStatus;
  tx_hash: string | null;
  block_number: number | null;
  chain_id: number | null;
  contract: string | null;
  anchored_at: string | null;
  error: string | null;
  attempts: number;
  attempted_at: string | null;
}

export interface Revocation {
  by: string;
  at: string;
  reason: string;
  tx_hash: string | null;
  block_number: number | null;
}

export interface Document {
  id: string;
  title: string;
  doc_type: DocType;
  owner_id: string;
  chain_doc_id: string;
  latest_approved_revision_id: string | null;
  latest_approved_version_no: number | null;
  revision_count: number;
  created_at: string;
  updated_at: string;
}

export interface Revision {
  id: string;
  document_id: string;
  revision_no: number;
  parent_revision_id: string | null;
  change_note: string | null;
  status: RevisionStatus;
  version_no: number | null;
  submitted_by: string;
  submitted_at: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_comment: string | null;
  original_filename: string;
  size_bytes: number;
  file_hash: string;
  text_root: string;
  canon_version: number;
  page_count: number;
  chunk_count: number;
  anchor: Anchor;
  revocation: Revocation | null;
}

export interface PendingRevision extends Revision {
  document_title: string | null;
}

export interface Paginated<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
}

export interface DocumentCreateResponse {
  document: Document;
  revision: Revision;
}

export interface DocumentRef {
  id: string;
  title: string | null;
}

export interface DocumentDetailResponse {
  document: Document;
  latest_approved_revision: Revision | null;
}

export interface FileUrlResponse {
  url: string;
  expires_in: number;
}

export type EventType =
  | "DOCUMENT_CREATED"
  | "REVISION_SUBMITTED"
  | "REVISION_APPROVED"
  | "REVISION_REJECTED"
  | "VERSION_ANCHORED"
  | "ANCHOR_FAILED"
  | "VERSION_REVOKED"
  | "VERIFIED";

export interface ProvenanceEvent {
  id: string;
  document_id: string;
  revision_id: string | null;
  type: EventType;
  actor_id: string | null;
  at: string;
  data: Record<string, unknown>;
  prev_event_hash: string | null;
  event_hash: string;
}

export interface Provenance {
  document_id: string;
  chain_valid: boolean;
  events: ProvenanceEvent[];
}

export interface VerificationSummary {
  id: string;
  at: string;
  verdict: Verdict;
  summary: string;
  document: DocumentRef | null;
  filename: string;
  file_hash: string;
}

export type Verdict =
  | "AUTHENTIC_LATEST"
  | "AUTHENTIC_SUPERSEDED"
  | "CONTENT_EQUIVALENT"
  | "UNAUTHORIZED_VERSION"
  | "TAMPERED"
  | "RECORD_MISMATCH"
  | "UNKNOWN_DOCUMENT";

export type StepStatus = "PASS" | "FAIL" | "WARN" | "DONE" | "SKIPPED";

export interface VerificationStep {
  name: string;
  status: StepStatus;
  detail?: string;
}

export interface RevisionSnapshot {
  id: string;
  revision_no: number;
  version_no: number | null;
  status: RevisionStatus;
  anchored_tx: string | null;
  revocation: { at: string; reason?: string } | null;
}

export type RegionType = "MODIFIED" | "INSERTED" | "DELETED";

/** PDF points `[x0, y0, x1, y1]`, top-left origin. */
export type BboxTuple = [number, number, number, number];

/** Pages are 0-based. `ref_*` index the reference PDF, `cand_*` the candidate PDF, and the
 * two documents may have different page counts. Anonymous reports null the text/bbox fields. */
export interface ChangeRegion {
  id: string;
  type: RegionType;
  ref_chunk_id: string | null;
  cand_chunk_id: string | null;
  ref_page: number | null;
  cand_page: number | null;
  ref_text: string | null;
  cand_text: string | null;
  ref_bbox: BboxTuple | null;
  cand_bbox: BboxTuple | null;
  section_id: string | null;
  section_title: string | null;
}

export interface LocalizationResult {
  status: "IDENTICAL" | "CONTENT_EQUIVALENT" | "CHANGED";
  regions: ChangeRegion[];
  changed_pages_ref: number[];
  changed_pages_cand: number[];
  method: string | null;
  hash_comparisons: number;
  stats: Record<string, number>;
}

export interface EntityChange {
  type: string;
  before: string | null;
  after: string | null;
}

export interface DiffOp {
  op: "equal" | "insert" | "delete" | "replace";
  before: string[];
  after: string[];
}

export type Severity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export interface AnalysisItem {
  region_id: string;
  primary_category: string;
  categories: string[];
  severity: Severity;
  similarity: number | null;
  entity_changes: EntityChange[];
  token_diff?: DiffOp[];
  explanation: string;
  method?: string;
}

export interface ChainCheck {
  performed: boolean;
  ok: boolean | null;
  reason: string | null;
  mismatches: string[];
  tx_hash: string | null;
  explorer_url: string | null;
}

export interface VerificationReport {
  id: string;
  at: string;
  verdict: Verdict;
  summary: string;
  document: DocumentRef | null;
  matched_revision: RevisionSnapshot | null;
  reference_revision: RevisionSnapshot | null;
  no_reference_reason: string | null;
  steps: VerificationStep[];
  candidate: { filename?: string; file_hash: string; text_root: string; page_count: number };
  localization: LocalizationResult | null;
  /** null when NLP was skipped, disabled or not requested. */
  analysis: AnalysisItem[] | null;
  chain_check: ChainCheck | null;
  timings_ms: Record<string, number>;
}

/** GET /revisions/{id}/diff (04_API_SPEC, RevisionDiffOut): no verdict, steps or chain check. */
export interface RevisionDiff {
  revision_id: string;
  against_revision_id: string;
  localization: LocalizationResult;
  /** null until NLP has run for the comparison. */
  analysis: AnalysisItem[] | null;
}

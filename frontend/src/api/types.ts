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
  verdict: string;
  summary: string;
  document: DocumentRef | null;
  filename: string;
  file_hash: string;
}

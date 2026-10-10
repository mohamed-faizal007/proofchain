import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../client";
import type { Paginated, PendingRevision, Revision, RevisionDiff } from "../types";

/** GET /revisions/{id}/diff?against=: `against` omitted means the candidate's parent. */
export function useRevisionDiff(
  revisionId: string | undefined,
  againstId: string | undefined,
  options?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: ["revisions", revisionId, "diff", againstId ?? null],
    queryFn: async () => {
      const { data } = await api.get<RevisionDiff>(`/revisions/${revisionId}/diff`, {
        params: againstId ? { against: againstId } : undefined,
      });
      return data;
    },
    enabled: revisionId != null && (options?.enabled ?? true),
    retry: false,
  });
}

export interface DownloadRevisionFileInput {
  revisionId: string;
  filename: string;
}

export interface PendingRevisionsFilters {
  page: number;
  page_size: number;
}

/** GET /revisions?status=PENDING (04_API_SPEC, P8-04): the approvals queue, oldest first. */
export function usePendingRevisions(
  filters: PendingRevisionsFilters,
  options?: { enabled?: boolean },
) {
  return useQuery({
    queryKey: ["revisions", "pending", filters],
    queryFn: async () => {
      const { data } = await api.get<Paginated<PendingRevision>>("/revisions", {
        params: { status: "PENDING", ...filters },
      });
      return data;
    },
    enabled: options?.enabled ?? true,
  });
}

export interface ReviewRevisionInput {
  revisionId: string;
  comment?: string;
}

function useInvalidateAfterChange() {
  const queryClient = useQueryClient();
  return (revision: Revision): void => {
    void queryClient.invalidateQueries({ queryKey: ["revisions", "pending"] });
    void queryClient.invalidateQueries({ queryKey: ["documents"] });
    void queryClient.invalidateQueries({
      queryKey: ["documents", revision.document_id, "revisions"],
    });
    void queryClient.invalidateQueries({
      queryKey: ["documents", revision.document_id, "provenance"],
    });
  };
}

function useReviewMutation(action: "approve" | "reject") {
  const invalidate = useInvalidateAfterChange();
  return useMutation({
    mutationFn: async ({ revisionId, comment }: ReviewRevisionInput) => {
      const body = comment !== undefined ? { comment } : undefined;
      const { data } = await api.post<Revision>(`/revisions/${revisionId}/${action}`, body);
      return data;
    },
    onSuccess: invalidate,
  });
}

export interface RevokeRevisionInput {
  revisionId: string;
  reason: string;
}

/** POST /revisions/{id}/revoke (04_API_SPEC): APPROVER; `reason` required (stored on-chain, so
 * public); synchronous, 200 with the REVOKED revision once the on-chain revoke is confirmed. */
export function useRevokeRevision() {
  const invalidate = useInvalidateAfterChange();
  return useMutation({
    mutationFn: async ({ revisionId, reason }: RevokeRevisionInput) => {
      const { data } = await api.post<Revision>(`/revisions/${revisionId}/revoke`, { reason });
      return data;
    },
    onSuccess: invalidate,
  });
}

/** POST /revisions/{id}/retry-anchor (04_API_SPEC): ADMIN; FAILED -> 202 and a new attempt in
 * the background; already ANCHORED -> 200 no-op. */
export function useRetryAnchor() {
  const invalidate = useInvalidateAfterChange();
  return useMutation({
    mutationFn: async (revisionId: string) => {
      const { data } = await api.post<Revision>(`/revisions/${revisionId}/retry-anchor`);
      return data;
    },
    onSuccess: invalidate,
  });
}

/** POST /revisions/{id}/approve (04_API_SPEC): `comment` optional; 202, anchoring runs after. */
export function useApproveRevision() {
  return useReviewMutation("approve");
}

/** POST /revisions/{id}/reject (04_API_SPEC): `comment` required by the backend (blank = 422). */
export function useRejectRevision() {
  return useReviewMutation("reject");
}

/** GET /revisions/{id}/download (04_API_SPEC): streams the stored PDF through the backend
 * (no presigned S3 URL, see PROGRESS.md "Presigned URL host"). Saves it via a temporary
 * object URL, which is always revoked afterwards. */
export function useDownloadRevisionFile() {
  return useMutation({
    mutationFn: async ({ revisionId, filename }: DownloadRevisionFileInput) => {
      const { data } = await api.get<Blob>(`/revisions/${revisionId}/download`, {
        responseType: "blob",
      });
      const objectUrl = URL.createObjectURL(data);
      try {
        const link = document.createElement("a");
        link.href = objectUrl;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
      } finally {
        URL.revokeObjectURL(objectUrl);
      }
    },
  });
}

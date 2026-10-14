import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../client";
import type { Paginated, VerificationReport, VerificationSummary } from "../types";

/** GET /verifications (04_API_SPEC): the current user's own history only, newest first. */
export function useRecentVerifications(pageSize: number) {
  return useQuery({
    queryKey: ["verifications", "recent", pageSize],
    queryFn: async () => {
      const { data } = await api.get<Paginated<VerificationSummary>>("/verifications", {
        params: { page: 1, page_size: pageSize },
      });
      return data;
    },
  });
}

/** GET /verifications: one page of the history (VerificationHistory). */
export function useVerificationsPage(page: number, pageSize: number) {
  return useQuery({
    queryKey: ["verifications", "page", page, pageSize],
    queryFn: async () => {
      const { data } = await api.get<Paginated<VerificationSummary>>("/verifications", {
        params: { page, page_size: pageSize },
      });
      return data;
    },
    placeholderData: keepPreviousData,
  });
}

/** GET /verifications/{id}: the stored report (owner or ADMIN). */
export function useVerification(id: string | undefined) {
  return useQuery({
    queryKey: ["verifications", "detail", id],
    queryFn: async () => {
      const { data } = await api.get<VerificationReport>(`/verifications/${id}`);
      return data;
    },
    enabled: id != null,
    retry: false,
  });
}

export interface VerifyInput {
  file: File;
  documentId?: string;
  includeNlp: boolean;
  /** Called with 0..1 as the file uploads; the server's processing time comes after 1. */
  onUploadProgress?: (fraction: number) => void;
}

/** POST /verify (multipart). Public when PUBLIC_VERIFY=true. */
export function useVerify() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ file, documentId, includeNlp, onUploadProgress }: VerifyInput) => {
      const form = new FormData();
      form.append("file", file);
      if (documentId) form.append("document_id", documentId);
      form.append("include_nlp", String(includeNlp));
      const { data } = await api.post<VerificationReport>("/verify", form, {
        onUploadProgress: onUploadProgress
          ? (e) => onUploadProgress(e.total ? Math.min(1, e.loaded / e.total) : 0)
          : undefined,
      });
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["verifications"] });
    },
  });
}

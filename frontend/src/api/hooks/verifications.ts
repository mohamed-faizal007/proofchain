import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
}

/** POST /verify (multipart). Public when PUBLIC_VERIFY=true. */
export function useVerify() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ file, documentId, includeNlp }: VerifyInput) => {
      const form = new FormData();
      form.append("file", file);
      if (documentId) form.append("document_id", documentId);
      form.append("include_nlp", String(includeNlp));
      const { data } = await api.post<VerificationReport>("/verify", form);
      return data;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["verifications"] });
    },
  });
}

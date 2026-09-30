import { useQuery } from "@tanstack/react-query";
import { api } from "../client";

/** GET /revisions/{id}/download as a blob through the shared axios client (so the
 * Authorization header is attached), returned as an ArrayBuffer for pdf.js. */
export function useRevisionPdf(revisionId: string | undefined) {
  return useQuery({
    queryKey: ["revision-pdf", revisionId],
    queryFn: async () => {
      const { data } = await api.get<Blob>(`/revisions/${revisionId}/download`, {
        responseType: "blob",
      });
      return data.arrayBuffer();
    },
    enabled: revisionId != null,
    staleTime: Infinity,
    gcTime: 5 * 60_000,
    retry: false,
  });
}

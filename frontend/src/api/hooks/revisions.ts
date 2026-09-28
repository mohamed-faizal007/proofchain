import { useMutation } from "@tanstack/react-query";
import { api } from "../client";

export interface DownloadRevisionFileInput {
  revisionId: string;
  filename: string;
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

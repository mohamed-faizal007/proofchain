import { useQuery } from "@tanstack/react-query";
import { api } from "../client";
import type { Paginated, VerificationSummary } from "../types";

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

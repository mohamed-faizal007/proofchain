import { useQuery } from "@tanstack/react-query";
import { api } from "../client";
import type { ChainStatus } from "../types";

const REFRESH_MS = 30_000;

/** GET /chain/status: authenticated, any role. Polled slowly so the card stays honest. */
export function useChainStatus() {
  return useQuery({
    queryKey: ["chain", "status"],
    queryFn: async () => {
      const { data } = await api.get<ChainStatus>("/chain/status");
      return data;
    },
    refetchInterval: REFRESH_MS,
    retry: false,
  });
}

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import type { ReactNode } from "react";
import { api } from "../client";
import { useRecentVerifications } from "./verifications";

function makeWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

describe("useRecentVerifications", () => {
  it("requests the given page size and returns the current user's own history", async () => {
    let sentUrl: string | undefined;
    let sentParams: unknown;
    api.defaults.adapter = ((config: InternalAxiosRequestConfig) => {
      sentUrl = config.url;
      sentParams = config.params;
      return Promise.resolve({
        data: {
          items: [{ id: "v1", verdict: "AUTHENTIC", at: "2026-01-01T00:00:00Z" }],
          page: 1,
          page_size: 5,
          total: 1,
        },
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      } as AxiosResponse);
    }) as AxiosAdapter;

    const { result } = renderHook(() => useRecentVerifications(5), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(sentUrl).toBe("/verifications");
    expect(sentParams).toEqual({ page: 1, page_size: 5 });
    expect(result.current.data?.items[0]?.id).toBe("v1");
  });
});

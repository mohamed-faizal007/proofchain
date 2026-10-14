import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { AxiosAdapter, InternalAxiosRequestConfig } from "axios";
import type { ReactNode } from "react";
import { api } from "../client";
import { useVerify } from "./verifications";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("useVerify upload progress", () => {
  it("reports upload progress as a 0..1 fraction while the request is in flight", async () => {
    api.defaults.adapter = ((config: InternalAxiosRequestConfig) => {
      const onProgress = config.onUploadProgress as ((e: unknown) => void) | undefined;
      onProgress?.({ loaded: 25, total: 100 });
      onProgress?.({ loaded: 100, total: 100 });
      return Promise.resolve({ data: {}, status: 200, statusText: "OK", headers: {}, config });
    }) as AxiosAdapter;
    const seen: number[] = [];
    const { result } = renderHook(() => useVerify(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({
        file: new File(["x"], "a.pdf", { type: "application/pdf" }),
        includeNlp: false,
        onUploadProgress: (f) => seen.push(f),
      });
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(seen).toEqual([0.25, 1]);
  });
});

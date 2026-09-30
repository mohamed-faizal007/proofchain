import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import type { ReactNode } from "react";
import { api, setAuthToken } from "../client";
import { useRevisionPdf } from "./useRevisionPdf";

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient();
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe("useRevisionPdf", () => {
  it("fetches /revisions/{id}/download as a blob with the Authorization header", async () => {
    setAuthToken("tok-123");
    let seen: InternalAxiosRequestConfig | undefined;
    api.defaults.adapter = ((config: InternalAxiosRequestConfig) => {
      seen = config;
      return Promise.resolve({
        data: new Blob(["%PDF-1.4"], { type: "application/pdf" }),
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      } as AxiosResponse);
    }) as AxiosAdapter;

    const { result } = renderHook(() => useRevisionPdf("r1"), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(seen?.url).toBe("/revisions/r1/download");
    expect(seen?.responseType).toBe("blob");
    expect(seen?.headers.get("Authorization")).toBe("Bearer tok-123");
    expect(result.current.data).toBeInstanceOf(ArrayBuffer);
    expect(result.current.data?.byteLength).toBe(8);
  });

  it("surfaces a failed download as an error (no retry)", async () => {
    api.defaults.adapter = (() => Promise.reject(new Error("boom"))) as AxiosAdapter;
    const { result } = renderHook(() => useRevisionPdf("r2"), { wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import type { ReactNode } from "react";
import { api } from "../client";
import { useRecentVerifications, useVerification, useVerify } from "./verifications";

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

describe("useVerify / useVerification", () => {
  it("useVerify posts multipart with file, include_nlp and an optional document_id", async () => {
    const sent: { url?: string; form?: FormData }[] = [];
    api.defaults.adapter = ((config: InternalAxiosRequestConfig) => {
      sent.push({ url: config.url, form: config.data as FormData });
      return Promise.resolve({
        data: { id: "v9" },
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      } as AxiosResponse);
    }) as AxiosAdapter;
    const { result } = renderHook(() => useVerify(), { wrapper: makeWrapper() });
    const file = new File(["%PDF"], "a.pdf", { type: "application/pdf" });
    await act(() => result.current.mutateAsync({ file, includeNlp: false }));
    await act(() => result.current.mutateAsync({ file, documentId: "d1", includeNlp: true }));
    expect(sent[0]?.url).toBe("/verify");
    expect(sent[0]?.form?.get("include_nlp")).toBe("false");
    expect(sent[0]?.form?.has("document_id")).toBe(false);
    expect((sent[0]?.form?.get("file") as File).name).toBe("a.pdf");
    expect(sent[1]?.form?.get("document_id")).toBe("d1");
    expect(sent[1]?.form?.get("include_nlp")).toBe("true");
  });

  it("useVerification GETs /verifications/{id}, and is disabled without an id", async () => {
    const urls: string[] = [];
    api.defaults.adapter = ((config: InternalAxiosRequestConfig) => {
      urls.push(String(config.url));
      return Promise.resolve({
        data: { id: "v1" },
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      } as AxiosResponse);
    }) as AxiosAdapter;
    const { result } = renderHook(() => useVerification("v1"), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(urls).toEqual(["/verifications/v1"]);
    const idle = renderHook(() => useVerification(undefined), { wrapper: makeWrapper() });
    expect(idle.result.current.fetchStatus).toBe("idle");
  });
});

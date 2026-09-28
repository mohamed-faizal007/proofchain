import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import { AxiosError } from "axios";
import type { ReactNode } from "react";
import { beforeEach, vi } from "vitest";
import { api } from "../client";
import { useDownloadRevisionFile } from "./revisions";

function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:mock-url");
  URL.revokeObjectURL = vi.fn();
});

describe("useDownloadRevisionFile", () => {
  it("requests the blob and triggers a save through a revoked object URL", async () => {
    let requestedUrl: string | undefined;
    let requestedResponseType: string | undefined;
    const blob = new Blob(["%PDF-1.4"], { type: "application/pdf" });
    api.defaults.adapter = ((config: InternalAxiosRequestConfig) => {
      requestedUrl = config.url;
      requestedResponseType = config.responseType;
      return Promise.resolve({
        data: blob,
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      } as AxiosResponse);
    }) as AxiosAdapter;

    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    const { result } = renderHook(() => useDownloadRevisionFile(), { wrapper: makeWrapper() });
    await result.current.mutateAsync({ revisionId: "r1", filename: "lease.pdf" });

    expect(requestedUrl).toBe("/revisions/r1/download");
    expect(requestedResponseType).toBe("blob");
    expect(URL.createObjectURL).toHaveBeenCalledWith(blob);
    expect(clickSpy).toHaveBeenCalled();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:mock-url");

    clickSpy.mockRestore();
  });

  it("revokes the object URL even when the click throws", async () => {
    const blob = new Blob(["%PDF-1.4"], { type: "application/pdf" });
    api.defaults.adapter = ((config: InternalAxiosRequestConfig) =>
      Promise.resolve({
        data: blob,
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      } as AxiosResponse)) as AxiosAdapter;
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {
      throw new Error("boom");
    });

    const { result } = renderHook(() => useDownloadRevisionFile(), { wrapper: makeWrapper() });
    await expect(
      result.current.mutateAsync({ revisionId: "r1", filename: "lease.pdf" }),
    ).rejects.toThrow("boom");

    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:mock-url");
    clickSpy.mockRestore();
  });

  it("surfaces a request failure to the caller", async () => {
    api.defaults.adapter = ((config: InternalAxiosRequestConfig) => {
      const response = {
        data: new Blob([JSON.stringify({ error: { code: "NOT_FOUND", message: "gone" } })]),
        status: 404,
        statusText: "",
        headers: {},
        config,
      } as AxiosResponse;
      return Promise.reject(new AxiosError("failed", "ERR_BAD_REQUEST", config, null, response));
    }) as AxiosAdapter;

    const { result } = renderHook(() => useDownloadRevisionFile(), { wrapper: makeWrapper() });
    await expect(
      result.current.mutateAsync({ revisionId: "r1", filename: "lease.pdf" }),
    ).rejects.toThrow();
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

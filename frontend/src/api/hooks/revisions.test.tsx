import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import { AxiosError } from "axios";
import type { ReactNode } from "react";
import { beforeEach, vi } from "vitest";
import { api } from "../client";
import {
  useApproveRevision,
  useDownloadRevisionFile,
  usePendingRevisions,
  useRejectRevision,
} from "./revisions";

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

describe("usePendingRevisions", () => {
  it("requests the PENDING queue with pagination params", async () => {
    let sentParams: unknown;
    api.defaults.adapter = ((config: InternalAxiosRequestConfig) => {
      sentParams = config.params;
      return Promise.resolve({
        data: { items: [], page: 1, page_size: 20, total: 0 },
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      } as AxiosResponse);
    }) as AxiosAdapter;

    const { result } = renderHook(() => usePendingRevisions({ page: 1, page_size: 20 }), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(sentParams).toEqual({ status: "PENDING", page: 1, page_size: 20 });
  });

  it("does not fetch when disabled", async () => {
    let called = false;
    api.defaults.adapter = (() => {
      called = true;
      return Promise.reject(new Error("should not be called"));
    }) as AxiosAdapter;

    renderHook(() => usePendingRevisions({ page: 1, page_size: 20 }, { enabled: false }), {
      wrapper: makeWrapper(),
    });
    await new Promise((resolve) => setTimeout(resolve, 10));
    expect(called).toBe(false);
  });
});

describe("useApproveRevision / useRejectRevision", () => {
  it("posts a comment to approve and invalidates related queries", async () => {
    let requestedUrl: string | undefined;
    let requestedBody: unknown;
    api.defaults.adapter = ((config: InternalAxiosRequestConfig) => {
      requestedUrl = config.url;
      requestedBody = config.data ? JSON.parse(config.data as string) : undefined;
      return Promise.resolve({
        data: { id: "r1", document_id: "d1", status: "APPROVED" },
        status: 202,
        statusText: "Accepted",
        headers: {},
        config,
      } as AxiosResponse);
    }) as AxiosAdapter;

    const { result } = renderHook(() => useApproveRevision(), { wrapper: makeWrapper() });
    const revision = await result.current.mutateAsync({ revisionId: "r1", comment: "ok" });

    expect(requestedUrl).toBe("/revisions/r1/approve");
    expect(requestedBody).toEqual({ comment: "ok" });
    expect(revision.status).toBe("APPROVED");
  });

  it("sends no body when approving without a comment", async () => {
    let requestedBody: unknown;
    api.defaults.adapter = ((config: InternalAxiosRequestConfig) => {
      requestedBody = config.data;
      return Promise.resolve({
        data: { id: "r1", document_id: "d1", status: "APPROVED" },
        status: 202,
        statusText: "Accepted",
        headers: {},
        config,
      } as AxiosResponse);
    }) as AxiosAdapter;

    const { result } = renderHook(() => useApproveRevision(), { wrapper: makeWrapper() });
    await result.current.mutateAsync({ revisionId: "r1" });

    expect(requestedBody).toBeUndefined();
  });

  it("posts a required comment to reject", async () => {
    let requestedUrl: string | undefined;
    let requestedBody: unknown;
    api.defaults.adapter = ((config: InternalAxiosRequestConfig) => {
      requestedUrl = config.url;
      requestedBody = config.data ? JSON.parse(config.data as string) : undefined;
      return Promise.resolve({
        data: { id: "r1", document_id: "d1", status: "REJECTED" },
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      } as AxiosResponse);
    }) as AxiosAdapter;

    const { result } = renderHook(() => useRejectRevision(), { wrapper: makeWrapper() });
    await result.current.mutateAsync({ revisionId: "r1", comment: "no" });

    expect(requestedUrl).toBe("/revisions/r1/reject");
    expect(requestedBody).toEqual({ comment: "no" });
  });
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import type { ReactNode } from "react";
import { api } from "../client";
import { useCreateDocument, useDocuments } from "./documents";

function ok(data: unknown): AxiosAdapter {
  return (config: InternalAxiosRequestConfig) =>
    Promise.resolve({ data, status: 200, statusText: "OK", headers: {}, config } as AxiosResponse);
}

function makeWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

describe("useDocuments", () => {
  it("fetches the documents page and exposes items/total", async () => {
    api.defaults.adapter = ok({
      items: [{ id: "d1", title: "Lease" }],
      page: 1,
      page_size: 20,
      total: 1,
    });
    const { result } = renderHook(() => useDocuments({ page: 1, page_size: 20 }), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.total).toBe(1);
    expect(result.current.data?.items[0]?.id).toBe("d1");
  });

  it("omits undefined filters from the query params", async () => {
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

    const { result } = renderHook(
      () => useDocuments({ page: 1, page_size: 20, q: undefined, status: "PENDING" }),
      { wrapper: makeWrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(sentParams).toEqual({ page: 1, page_size: 20, status: "PENDING" });
  });
});

describe("useCreateDocument", () => {
  it("posts multipart form data and returns the created document/revision", async () => {
    let sentBody: FormData | undefined;
    api.defaults.adapter = ((config: InternalAxiosRequestConfig) => {
      sentBody = config.data as FormData;
      return Promise.resolve({
        data: {
          document: { id: "d1", title: "Lease" },
          revision: { id: "r1", revision_no: 1 },
        },
        status: 201,
        statusText: "Created",
        headers: {},
        config,
      } as AxiosResponse);
    }) as AxiosAdapter;

    const { result } = renderHook(() => useCreateDocument(), { wrapper: makeWrapper() });
    const file = new File(["%PDF-1.4"], "lease.pdf", { type: "application/pdf" });
    const response = await result.current.mutateAsync({
      file,
      title: "Lease",
      doc_type: "CONTRACT",
    });

    expect(response.document.id).toBe("d1");
    expect(sentBody).toBeInstanceOf(FormData);
    expect(sentBody?.get("title")).toBe("Lease");
    expect(sentBody?.get("doc_type")).toBe("CONTRACT");
    expect(sentBody?.get("file")).toBe(file);
    expect(sentBody?.get("change_note")).toBeNull();
  });

  it("omits change_note from the form when not provided", async () => {
    let sentBody: FormData | undefined;
    api.defaults.adapter = ((config: InternalAxiosRequestConfig) => {
      sentBody = config.data as FormData;
      return Promise.resolve({
        data: { document: { id: "d1" }, revision: { id: "r1" } },
        status: 201,
        statusText: "Created",
        headers: {},
        config,
      } as AxiosResponse);
    }) as AxiosAdapter;

    const { result } = renderHook(() => useCreateDocument(), { wrapper: makeWrapper() });
    const file = new File(["%PDF-1.4"], "lease.pdf", { type: "application/pdf" });
    await result.current.mutateAsync({
      file,
      title: "Lease",
      doc_type: "CONTRACT",
      change_note: "Updated clause",
    });

    expect(sentBody?.get("change_note")).toBe("Updated clause");
  });
});

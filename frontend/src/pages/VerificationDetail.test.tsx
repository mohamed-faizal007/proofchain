import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import { AxiosError } from "axios";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, vi } from "vitest";
import { api } from "../api/client";
import { routerFuture } from "../routerFuture";
import { makeReport } from "../test/verificationFixtures";
import { VerificationDetail } from "./VerificationDetail";

const openPdf = vi.hoisted(() => vi.fn());
vi.mock("../lib/pdfjs", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../lib/pdfjs")>()),
  openPdf,
}));

let urls: string[] = [];

function install(
  handler: (url: string, config: InternalAxiosRequestConfig) => Promise<AxiosResponse>,
) {
  urls = [];
  api.defaults.adapter = ((config: InternalAxiosRequestConfig) => {
    urls.push(String(config.url));
    return handler(String(config.url), config);
  }) as AxiosAdapter;
}

const ok = (config: InternalAxiosRequestConfig, data: unknown): AxiosResponse => ({
  data,
  status: 200,
  statusText: "OK",
  headers: {},
  config,
});

function fail(config: InternalAxiosRequestConfig, status: number, code: string) {
  const response = {
    data: { error: { code, message: "server" } },
    status,
    statusText: "",
    headers: {},
    config,
  };
  return Promise.reject(
    new AxiosError("failed", "ERR_BAD_REQUEST", config, null, response as never),
  );
}

function renderDetail() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter future={routerFuture} initialEntries={["/verifications/ver-1"]}>
        <Routes>
          <Route path="/verifications/:id" element={<VerificationDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  openPdf.mockReset();
  openPdf.mockImplementation(async () => ({
    numPages: 2,
    getPage: () =>
      Promise.resolve({
        rotate: 0,
        getViewport: ({ scale }: { scale: number }) => ({
          width: 600 * scale,
          height: 800 * scale,
        }),
        render: () => ({ promise: new Promise(() => {}), cancel: vi.fn() }),
      }),
    destroy: () => Promise.resolve(),
  }));
  vi.stubGlobal("IntersectionObserver", undefined);
});
afterEach(() => vi.unstubAllGlobals());

describe("VerificationDetail: a stored report (opened from history or after a refresh)", () => {
  it("shows the verdict, the 'not stored' banner and the reference-only view", async () => {
    install((url, config) =>
      url.endsWith("/download")
        ? Promise.resolve(ok(config, new Blob(["REF"], { type: "application/pdf" })))
        : Promise.resolve(ok(config, makeReport())),
    );
    renderDetail();
    expect(await screen.findByRole("region", { name: "Verdict" })).toHaveAttribute(
      "data-verdict",
      "TAMPERED",
    );
    expect(screen.getByTestId("candidate-not-stored")).toHaveTextContent(/isn't stored/i);
    expect(
      await within(screen.getByTestId("viewer-reference")).findByTestId("pdf-page-1"),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("viewer-candidate")).not.toBeInTheDocument();
    expect(urls).toEqual(["/verifications/ver-1", "/revisions/rev-ref/download"]);
  });

  it("shows a loading status while fetching", () => {
    install(() => new Promise(() => {}));
    renderDetail();
    expect(screen.getByRole("status")).toHaveTextContent(/loading verification/i);
  });

  it.each([
    [403, /don't have access/i],
    [404, /not found/i],
  ])("%s shows a specific message, not a blank page", async (status, pattern) => {
    install((_url, config) => fail(config, status, "X"));
    renderDetail();
    expect(await screen.findByRole("alert")).toHaveTextContent(pattern);
    expect(screen.getByRole("heading", { level: 1, name: "Verification" })).toBeInTheDocument();
  });
});

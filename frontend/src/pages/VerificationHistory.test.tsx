import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import { AxiosError } from "axios";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { api } from "../api/client";
import type { VerificationSummary } from "../api/types";
import { routerFuture } from "../routerFuture";
import { VerificationHistory } from "./VerificationHistory";

function summary(over: Partial<VerificationSummary> = {}): VerificationSummary {
  return {
    id: "ver-1",
    at: "2026-09-30T10:00:00Z",
    verdict: "TAMPERED",
    summary: "2 changes on page(s) 1, 2",
    document: { id: "doc-1", title: "Lease Agreement" },
    filename: "lease-copy.pdf",
    file_hash: "a".repeat(64),
    ...over,
  };
}

const json = (config: InternalAxiosRequestConfig, data: unknown, status = 200): AxiosResponse =>
  ({ data, status, statusText: "", headers: {}, config }) as AxiosResponse;

interface Setup {
  pages: Record<number, { items: VerificationSummary[]; total: number }>;
  calls: { page: number; page_size: number }[];
  fail?: boolean;
}

function install(setup: Setup) {
  const adapter: AxiosAdapter = (config) => {
    if (setup.fail) {
      const response = json(config, { error: { code: "INTERNAL_ERROR", message: "boom" } }, 500);
      return Promise.reject(new AxiosError("failed", "ERR_BAD_REQUEST", config, null, response));
    }
    const params = config.params as { page: number; page_size: number };
    setup.calls.push(params);
    const p = setup.pages[params.page] ?? { items: [], total: 0 };
    return Promise.resolve(json(config, { ...p, page: params.page, page_size: params.page_size }));
  };
  api.defaults.adapter = adapter;
}

function renderHistory(setup: Setup, entry = "/verifications") {
  install(setup);
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter future={routerFuture} initialEntries={[entry]}>
        <Routes>
          <Route path="/verifications" element={<VerificationHistory />} />
          <Route path="/verifications/:id" element={<div>Detail page</div>} />
          <Route path="/verify" element={<div>Verify page</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("VerificationHistory", () => {
  it("lists rows with verdict, filename, document, summary and a link to the report", async () => {
    renderHistory({ pages: { 1: { items: [summary()], total: 1 } }, calls: [] });
    const link = await screen.findByRole("link", { name: /lease-copy\.pdf/ });
    expect(link).toHaveAttribute("href", "/verifications/ver-1");
    const row = link.closest("li") as HTMLElement;
    expect(within(row).getByText("Tampered")).toHaveAttribute("data-tone", "red");
    expect(within(row).getByText(/Lease Agreement/)).toBeInTheDocument();
    expect(within(row).getByText(/2 changes on page/)).toBeInTheDocument();
  });

  it("paginates: Next requests page 2, Previous returns, and bounds disable the buttons", async () => {
    const setup: Setup = {
      pages: {
        1: { items: [summary({ id: "a", filename: "first.pdf" })], total: 25 },
        2: { items: [summary({ id: "b", filename: "second.pdf" })], total: 25 },
      },
      calls: [],
    };
    renderHistory(setup);
    expect(await screen.findByText("first.pdf")).toBeInTheDocument();
    expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("second.pdf")).toBeInTheDocument();
    expect(setup.calls.map((c) => c.page)).toEqual([1, 2]);
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: "Previous" }));
    expect(await screen.findByText("first.pdf")).toBeInTheDocument();
  });

  it("reads the page from the URL", async () => {
    const setup: Setup = { pages: { 2: { items: [summary()], total: 25 } }, calls: [] };
    renderHistory(setup, "/verifications?page=2");
    await screen.findByText("lease-copy.pdf");
    expect(setup.calls[0].page).toBe(2);
  });

  it("shows an empty state that links to /verify", async () => {
    renderHistory({ pages: {}, calls: [] });
    expect(await screen.findByText(/no verifications yet/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /verify a document/i })).toHaveAttribute(
      "href",
      "/verify",
    );
  });

  it("shows an error state and keeps the heading", async () => {
    renderHistory({ pages: {}, calls: [], fail: true });
    expect(await screen.findByRole("alert")).toHaveTextContent("boom");
    expect(screen.getByRole("heading", { level: 1, name: "Verification history" })).toBeVisible();
  });

  it("falls back to a grey pill for a verdict string the frontend does not know", async () => {
    const odd = summary({ verdict: "SOMETHING_NEW" as unknown as VerificationSummary["verdict"] });
    renderHistory({ pages: { 1: { items: [odd], total: 1 } }, calls: [] });
    const pill = await screen.findByText("SOMETHING_NEW");
    expect(pill).toHaveAttribute("data-tone", "grey");
  });

  it("shows a loading state first", async () => {
    renderHistory({ pages: { 1: { items: [summary()], total: 1 } }, calls: [] });
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText(/loading/i)).toBeNull());
  });
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import { AxiosError } from "axios";
import { beforeEach, vi } from "vitest";
import { api, createClient } from "../api/client";
import { MemoryRouter } from "react-router-dom";
import { routerFuture } from "../routerFuture";
import { AuthProvider } from "../auth/AuthContext";
import { setStoredToken } from "../auth/storage";
import type { Revision } from "../api/types";
import { VersionTimeline } from "./VersionTimeline";

function revision(overrides: Partial<Revision> = {}): Revision {
  return {
    id: "r1",
    document_id: "d1",
    revision_no: 1,
    parent_revision_id: null,
    change_note: null,
    status: "APPROVED",
    version_no: 3,
    submitted_by: "u1",
    submitted_at: "2026-01-01T00:00:00Z",
    reviewed_by: "u2",
    reviewed_at: "2026-01-02T00:00:00Z",
    review_comment: null,
    original_filename: "lease.pdf",
    size_bytes: 100,
    file_hash: "a".repeat(64),
    text_root: "b".repeat(64),
    canon_version: 1,
    page_count: 3,
    chunk_count: 10,
    anchor: {
      status: "ANCHORED",
      tx_hash: `0x${"c".repeat(64)}`,
      block_number: 5,
      chain_id: 31337,
      contract: "0xabc",
      anchored_at: "2026-01-02T00:00:00Z",
      error: null,
      attempts: 1,
      attempted_at: "2026-01-02T00:00:00Z",
    },
    revocation: null,
    ...overrides,
  };
}

function renderTimeline(revisions: Revision[]) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  // RevisionActions reads the signed-in user; a VERIFIER sees no revoke / retry buttons.
  setStoredToken("test-token");
  const authClient = createClient({
    adapter: (config: InternalAxiosRequestConfig) =>
      Promise.resolve({
        data: {
          id: "u9",
          email: "v@example.com",
          full_name: "V",
          is_active: true,
          created_at: "2024-01-01T00:00:00Z",
          roles: ["VERIFIER"],
        },
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      } as AxiosResponse),
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter future={routerFuture}>
        <AuthProvider client={authClient}>
          <VersionTimeline revisions={revisions} />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:mock-url");
  URL.revokeObjectURL = vi.fn();
});

describe("VersionTimeline", () => {
  it("shows an empty state with no revisions", () => {
    renderTimeline([]);
    expect(screen.getByText(/no revisions yet/i)).toBeInTheDocument();
  });

  it("lists revisions newest first with status, on-chain number and anchor state", () => {
    renderTimeline([
      revision({ id: "r1", revision_no: 1 }),
      revision({ id: "r2", revision_no: 2 }),
    ]);
    const items = screen.getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("v2");
    expect(items[1]).toHaveTextContent("v1");
    expect(screen.getAllByText("APPROVED")).toHaveLength(2);
  });

  it("shows a revocation notice when a revision was revoked", () => {
    renderTimeline([
      revision({
        status: "REVOKED",
        revocation: {
          by: "u3",
          at: "2026-02-01T00:00:00Z",
          reason: "wrong file",
          tx_hash: null,
          block_number: null,
        },
      }),
    ]);
    expect(screen.getByText(/wrong file/)).toBeInTheDocument();
  });

  it("downloads the revision file on click", async () => {
    let requestedUrl: string | undefined;
    api.defaults.adapter = ((config: InternalAxiosRequestConfig) => {
      requestedUrl = config.url;
      return Promise.resolve({
        data: new Blob(["%PDF-1.4"]),
        status: 200,
        statusText: "OK",
        headers: {},
        config,
      } as AxiosResponse);
    }) as AxiosAdapter;
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    renderTimeline([revision()]);
    await userEvent.click(screen.getByRole("button", { name: /download file/i }));

    await waitFor(() => expect(requestedUrl).toBe("/revisions/r1/download"));
  });

  it("shows an error message when the download fails, without hiding the rest of the row", async () => {
    api.defaults.adapter = ((config: InternalAxiosRequestConfig) => {
      const response = {
        data: { error: { code: "NOT_FOUND", message: "Revision file not found" } },
        status: 404,
        statusText: "",
        headers: {},
        config,
      } as AxiosResponse;
      return Promise.reject(new AxiosError("failed", "ERR_BAD_REQUEST", config, null, response));
    }) as AxiosAdapter;

    renderTimeline([revision()]);
    await userEvent.click(screen.getByRole("button", { name: /download file/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/revision file not found/i);
    expect(screen.getByText(/v1/)).toBeInTheDocument();
  });
});

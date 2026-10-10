import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import { AxiosError } from "axios";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { api, createClient } from "../api/client";
import type { Role } from "../api/types";
import { AuthProvider } from "../auth/AuthContext";
import { ProtectedRoute } from "../auth/ProtectedRoute";
import { setStoredToken } from "../auth/storage";
import { routerFuture } from "../routerFuture";
import { DocumentDetail } from "./DocumentDetail";

const ME = {
  id: "u1",
  email: "issuer@proofchain.local",
  full_name: "Issuer",
  is_active: true,
  created_at: "2024-01-01T00:00:00Z",
};

const DOCUMENT = {
  document: {
    id: "doc-1",
    title: "Lease Agreement",
    doc_type: "CONTRACT",
    owner_id: "u1",
    chain_doc_id: "d".repeat(64),
    latest_approved_revision_id: "r1",
    latest_approved_version_no: 1,
    revision_count: 1,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-02T00:00:00Z",
  },
  latest_approved_revision: {
    id: "r1",
    document_id: "doc-1",
    revision_no: 1,
    parent_revision_id: null,
    change_note: null,
    status: "APPROVED",
    version_no: 1,
    submitted_by: "u1",
    submitted_at: "2026-01-01T00:00:00Z",
    reviewed_by: "u2",
    reviewed_at: "2026-01-01T01:00:00Z",
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
      anchored_at: "2026-01-01T01:00:00Z",
      error: null,
      attempts: 1,
      attempted_at: "2026-01-01T01:00:00Z",
    },
    revocation: null,
  },
};

const REVISIONS = [DOCUMENT.latest_approved_revision];

const PROVENANCE = {
  document_id: "doc-1",
  chain_valid: true,
  events: [
    {
      id: "e1",
      document_id: "doc-1",
      revision_id: "r1",
      type: "DOCUMENT_CREATED",
      actor_id: "u1",
      at: "2026-01-01T00:00:00Z",
      data: {},
      prev_event_hash: null,
      event_hash: "e".repeat(64),
    },
  ],
};

function ok(data: unknown): AxiosAdapter {
  return (config: InternalAxiosRequestConfig) =>
    Promise.resolve({ data, status: 200, statusText: "OK", headers: {}, config } as AxiosResponse);
}

function fail(status: number, code: string, message: string): AxiosAdapter {
  return (config: InternalAxiosRequestConfig) => {
    const response = {
      data: { error: { code, message } },
      status,
      statusText: "",
      headers: {},
      config,
    } as AxiosResponse;
    return Promise.reject(new AxiosError("failed", "ERR_BAD_REQUEST", config, null, response));
  };
}

function routedAdapter(
  routes: Record<string, AxiosAdapter>,
  fallback: AxiosAdapter = ok(null),
): AxiosAdapter {
  return (config: InternalAxiosRequestConfig) => {
    const url = config.url ?? "";
    for (const [suffix, adapter] of Object.entries(routes)) {
      if (url.endsWith(suffix)) return adapter(config);
    }
    return fallback(config);
  };
}

function renderDetail(roles: Role[], routes: Record<string, AxiosAdapter>) {
  setStoredToken("test-token");
  api.defaults.adapter = routedAdapter(routes);
  const authClient = createClient({ adapter: ok({ ...ME, roles }) });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter future={routerFuture} initialEntries={["/documents/doc-1"]}>
        <AuthProvider client={authClient}>
          <Routes>
            <Route
              path="/documents/:id"
              element={
                <ProtectedRoute>
                  <DocumentDetail />
                </ProtectedRoute>
              }
            />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("DocumentDetail page", () => {
  it("renders the header, version timeline and provenance timeline", async () => {
    renderDetail(["VERIFIER"], {
      "/documents/doc-1": ok(DOCUMENT),
      "/revisions": ok(REVISIONS),
      "/provenance": ok(PROVENANCE),
    });

    expect(await screen.findByRole("heading", { name: "Lease Agreement" })).toBeInTheDocument();
    expect(await screen.findByText(/v1/)).toBeInTheDocument();
    expect(await screen.findByText("DOCUMENT_CREATED")).toBeInTheDocument();
  });

  it("shows 'Submit new revision' only for an ISSUER", async () => {
    renderDetail(["ISSUER"], {
      "/documents/doc-1": ok(DOCUMENT),
      "/revisions": ok(REVISIONS),
      "/provenance": ok(PROVENANCE),
    });
    expect(await screen.findByRole("link", { name: /submit new revision/i })).toHaveAttribute(
      "href",
      "/documents/doc-1/revisions/new",
    );
  });

  it("hides 'Submit new revision' from an ISSUER who does not own the document", async () => {
    renderDetail(["ISSUER"], {
      "/documents/doc-1": ok({ ...DOCUMENT, document: { ...DOCUMENT.document, owner_id: "u9" } }),
      "/revisions": ok(REVISIONS),
      "/provenance": ok(PROVENANCE),
    });
    await screen.findByRole("heading", { name: "Lease Agreement" });
    expect(screen.queryByRole("link", { name: /submit new revision/i })).not.toBeInTheDocument();
  });

  it("hides 'Submit new revision' for a non-ISSUER", async () => {
    renderDetail(["VERIFIER"], {
      "/documents/doc-1": ok(DOCUMENT),
      "/revisions": ok(REVISIONS),
      "/provenance": ok(PROVENANCE),
    });
    await screen.findByRole("heading", { name: "Lease Agreement" });
    expect(screen.queryByRole("link", { name: /submit new revision/i })).not.toBeInTheDocument();
  });

  it("shows an error for the header without hiding the other sections", async () => {
    renderDetail(["VERIFIER"], {
      "/documents/doc-1": fail(404, "NOT_FOUND", "Document not found"),
      "/revisions": ok(REVISIONS),
      "/provenance": ok(PROVENANCE),
    });

    expect(await screen.findByRole("alert")).toHaveTextContent(/document not found/i);
    expect(await screen.findByText("DOCUMENT_CREATED")).toBeInTheDocument();
  });

  it("shows an error for the revisions section without hiding the header or provenance", async () => {
    renderDetail(["VERIFIER"], {
      "/documents/doc-1": ok(DOCUMENT),
      "/revisions": fail(500, "INTERNAL_ERROR", "boom"),
      "/provenance": ok(PROVENANCE),
    });

    expect(await screen.findByRole("heading", { name: "Lease Agreement" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByRole("alert").length).toBeGreaterThan(0));
    expect(await screen.findByText("DOCUMENT_CREATED")).toBeInTheDocument();
  });

  it("shows an error for the provenance section without hiding the header or revisions", async () => {
    renderDetail(["VERIFIER"], {
      "/documents/doc-1": ok(DOCUMENT),
      "/revisions": ok(REVISIONS),
      "/provenance": fail(500, "INTERNAL_ERROR", "boom"),
    });

    expect(await screen.findByRole("heading", { name: "Lease Agreement" })).toBeInTheDocument();
    expect(await screen.findByText(/v1/)).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });

  it("shows empty states when there are no revisions or provenance events", async () => {
    renderDetail(["VERIFIER"], {
      "/documents/doc-1": ok({ ...DOCUMENT, latest_approved_revision: null }),
      "/revisions": ok([]),
      "/provenance": ok({ document_id: "doc-1", chain_valid: true, events: [] }),
    });

    expect(await screen.findByText(/no revisions yet/i)).toBeInTheDocument();
    expect(await screen.findByText(/no provenance events yet/i)).toBeInTheDocument();
  });
});

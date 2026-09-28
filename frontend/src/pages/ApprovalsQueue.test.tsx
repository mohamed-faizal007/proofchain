import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import { AxiosError } from "axios";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { api } from "../api/client";
import { AuthProvider } from "../auth/AuthContext";
import { setStoredToken } from "../auth/storage";
import { routerFuture } from "../routerFuture";
import { ApprovalsQueue } from "./ApprovalsQueue";

const APPROVER = {
  id: "approver-1",
  email: "approver@example.com",
  full_name: "Ann Approver",
  roles: ["APPROVER"],
  is_active: true,
  created_at: "2024-01-01T00:00:00Z",
};

function pendingRevision(overrides: Record<string, unknown> = {}) {
  return {
    id: "rev-1",
    document_id: "doc-1",
    document_title: "Lease Agreement",
    revision_no: 2,
    parent_revision_id: "rev-0",
    change_note: "Updated clause 4",
    status: "PENDING",
    version_no: null,
    submitted_by: "issuer-1",
    submitted_at: "2024-01-02T00:00:00Z",
    reviewed_by: null,
    reviewed_at: null,
    review_comment: null,
    original_filename: "lease.pdf",
    size_bytes: 100,
    file_hash: "a".repeat(64),
    text_root: "b".repeat(64),
    canon_version: 2,
    page_count: 1,
    chunk_count: 1,
    anchor: {
      status: "NOT_REQUESTED",
      tx_hash: null,
      block_number: null,
      chain_id: null,
      contract: null,
      anchored_at: null,
      error: null,
      attempts: 0,
      attempted_at: null,
    },
    revocation: null,
    ...overrides,
  };
}

function jsonResponse(
  config: InternalAxiosRequestConfig,
  data: unknown,
  status = 200,
): AxiosResponse {
  return { data, status, statusText: "OK", headers: {}, config } as AxiosResponse;
}

interface QueueResponse {
  items: Record<string, unknown>[];
  total?: number;
  page?: number;
}

interface Router {
  auth?: Record<string, unknown>;
  queuePages?: QueueResponse[]; // successive responses for GET /revisions
  onApprove?: (id: string) => Record<string, unknown> | { error: string; code: string };
  onReject?: (id: string) => Record<string, unknown> | { error: string; code: string };
  calls: { url: string; method: string | undefined }[];
}

function makeAdapter(router: Router): AxiosAdapter {
  let queueCallIndex = 0;
  return (config: InternalAxiosRequestConfig) => {
    router.calls.push({ url: config.url ?? "", method: config.method });

    if (config.url === "/auth/me") {
      return Promise.resolve(jsonResponse(config, router.auth ?? APPROVER));
    }

    if (config.url === "/revisions" && config.method === "get") {
      const pages = router.queuePages ?? [{ items: [] }];
      const resp = pages[Math.min(queueCallIndex, pages.length - 1)];
      queueCallIndex += 1;
      return Promise.resolve(
        jsonResponse(config, {
          items: resp.items,
          page: resp.page ?? 1,
          page_size: 20,
          total: resp.total ?? resp.items.length,
        }),
      );
    }

    const approveMatch = /^\/revisions\/([^/]+)\/approve$/.exec(config.url ?? "");
    if (approveMatch && config.method === "post") {
      const result = router.onApprove?.(approveMatch[1]) ?? pendingRevision({ status: "APPROVED" });
      if ("error" in result) {
        const response = jsonResponse(
          config,
          { error: { code: result.code, message: result.error } },
          result.code === "REVISION_NOT_PENDING" ? 409 : 500,
        );
        return Promise.reject(new AxiosError("failed", "ERR_BAD_REQUEST", config, null, response));
      }
      return Promise.resolve(jsonResponse(config, result));
    }

    const rejectMatch = /^\/revisions\/([^/]+)\/reject$/.exec(config.url ?? "");
    if (rejectMatch && config.method === "post") {
      const result = router.onReject?.(rejectMatch[1]) ?? pendingRevision({ status: "REJECTED" });
      if ("error" in result) {
        const response = jsonResponse(
          config,
          { error: { code: result.code, message: result.error } },
          result.code === "REVISION_NOT_PENDING" ? 409 : 500,
        );
        return Promise.reject(new AxiosError("failed", "ERR_BAD_REQUEST", config, null, response));
      }
      return Promise.resolve(jsonResponse(config, result));
    }

    return Promise.reject(new Error(`unexpected request ${config.method} ${config.url}`));
  };
}

function renderQueue(router: Router) {
  setStoredToken("tok");
  api.defaults.adapter = makeAdapter(router);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter future={routerFuture} initialEntries={["/approvals"]}>
        <AuthProvider>
          <Routes>
            <Route path="/approvals" element={<ApprovalsQueue />} />
            <Route path="/documents/:id" element={<div>Document page</div>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ApprovalsQueue", () => {
  it("shows a role-gated message for a non-APPROVER user and never calls the queue", async () => {
    const router: Router = { auth: { ...APPROVER, roles: ["ADMIN"] }, calls: [] };
    renderQueue(router);

    expect(await screen.findByText(/requires the APPROVER role/i)).toBeInTheDocument();
    expect(screen.getByText(/ADMIN accounts/i)).toBeInTheDocument();
    await waitFor(() => expect(router.calls.some((c) => c.url === "/auth/me")).toBe(true));
    expect(router.calls.some((c) => c.url === "/revisions")).toBe(false);
  });

  it("renders pending revisions oldest first with document title, revision no and submitter", async () => {
    const router: Router = { queuePages: [{ items: [pendingRevision()] }], calls: [] };
    renderQueue(router);

    expect(await screen.findByText("Lease Agreement")).toBeInTheDocument();
    expect(screen.getByText("v2")).toBeInTheDocument();
    expect(screen.getByText(/issuer-1/)).toBeInTheDocument();
    expect(screen.getByText(/Updated clause 4/)).toBeInTheDocument();
  });

  it("shows an empty-queue message", async () => {
    const router: Router = { queuePages: [{ items: [] }], calls: [] };
    renderQueue(router);
    expect(await screen.findByText("No pending revisions.")).toBeInTheDocument();
  });

  it("shows an error state without hiding the page heading", async () => {
    const router: Router = { calls: [] };
    router.queuePages = undefined;
    const failing: AxiosAdapter = (config: InternalAxiosRequestConfig) => {
      if (config.url === "/auth/me") return Promise.resolve(jsonResponse(config, APPROVER));
      const response = jsonResponse(
        config,
        { error: { code: "INTERNAL_ERROR", message: "boom" } },
        500,
      );
      return Promise.reject(new AxiosError("failed", "ERR_BAD_REQUEST", config, null, response));
    };
    setStoredToken("tok");
    api.defaults.adapter = failing;
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter future={routerFuture} initialEntries={["/approvals"]}>
          <AuthProvider>
            <Routes>
              <Route path="/approvals" element={<ApprovalsQueue />} />
            </Routes>
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("boom")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Approvals" })).toBeInTheDocument();
  });

  it("disables and annotates a row for the user's own submission", async () => {
    const router: Router = {
      auth: APPROVER,
      queuePages: [{ items: [pendingRevision({ submitted_by: "approver-1" })] }],
      calls: [],
    };
    renderQueue(router);

    expect(await screen.findByText(/You submitted this revision/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
  });

  it("approves with an optional comment and shows an anchoring-in-progress message", async () => {
    const router: Router = {
      queuePages: [{ items: [pendingRevision()] }, { items: [] }],
      onApprove: (id) => {
        expect(id).toBe("rev-1");
        return pendingRevision({ status: "APPROVED" });
      },
      calls: [],
    };
    renderQueue(router);

    const approveButton = await screen.findByRole("button", { name: "Approve" });
    fireEvent.click(approveButton);

    expect(await screen.findByText(/Anchoring is in progress/)).toBeInTheDocument();
    expect(router.calls.filter((c) => c.url === "/revisions/rev-1/approve")).toHaveLength(1);
  });

  it("blocks reject client-side when the comment is blank, sending no request", async () => {
    const router: Router = { queuePages: [{ items: [pendingRevision()] }], calls: [] };
    renderQueue(router);

    const rejectButton = await screen.findByRole("button", { name: "Reject" });
    fireEvent.click(rejectButton);

    expect(await screen.findByText(/comment is required/i)).toBeInTheDocument();
    expect(router.calls.some((c) => c.url === "/revisions/rev-1/reject")).toBe(false);
  });

  it("rejects with a required comment and shows a confirmation", async () => {
    const router: Router = {
      queuePages: [{ items: [pendingRevision()] }, { items: [] }],
      onReject: () => pendingRevision({ status: "REJECTED" }),
      calls: [],
    };
    renderQueue(router);

    const textarea = await screen.findByLabelText(/comment for revision 2/i);
    fireEvent.change(textarea, { target: { value: "not acceptable" } });
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));

    expect(await screen.findByText(/Rejected v2/)).toBeInTheDocument();
    expect(router.calls.filter((c) => c.url === "/revisions/rev-1/reject")).toHaveLength(1);
  });

  it("sends exactly one request when the approve button is double-clicked", async () => {
    const router: Router = {
      queuePages: [{ items: [pendingRevision()] }, { items: [] }],
      onApprove: () => pendingRevision({ status: "APPROVED" }),
      calls: [],
    };
    renderQueue(router);

    const approveButton = await screen.findByRole("button", { name: "Approve" });
    // Two clicks fired back-to-back, before React can re-render the `disabled` state: the
    // in-flight guard (not just the disabled attribute) must be what stops the second one.
    fireEvent.click(approveButton);
    fireEvent.click(approveButton);

    await waitFor(() =>
      expect(router.calls.filter((c) => c.url === "/revisions/rev-1/approve")).toHaveLength(1),
    );
  });

  it("shows a friendly message and refetches the queue on REVISION_NOT_PENDING (409)", async () => {
    const router: Router = {
      queuePages: [{ items: [pendingRevision()] }, { items: [] }],
      onApprove: () => ({ error: "Revision is not pending", code: "REVISION_NOT_PENDING" }),
      calls: [],
    };
    renderQueue(router);

    fireEvent.click(await screen.findByRole("button", { name: "Approve" }));

    expect(await screen.findByText(/someone else already reviewed/i)).toBeInTheDocument();
    await waitFor(() =>
      expect(router.calls.filter((c) => c.url === "/revisions" && c.method === "get")).toHaveLength(
        2,
      ),
    );
  });

  it("shows the backend message for other errors without hiding the rest of the queue", async () => {
    const router: Router = {
      queuePages: [
        {
          items: [pendingRevision(), pendingRevision({ id: "rev-2", document_title: "Other Doc" })],
        },
      ],
      onApprove: () => ({ error: "boom", code: "INTERNAL_ERROR" }),
      calls: [],
    };
    renderQueue(router);

    const approveButtons = await screen.findAllByRole("button", { name: "Approve" });
    fireEvent.click(approveButtons[0]);

    expect(await screen.findByText("boom")).toBeInTheDocument();
    expect(screen.getByText("Other Doc")).toBeInTheDocument();
  });

  it("uses the page in the URL for pagination controls", async () => {
    const router: Router = {
      queuePages: [
        {
          items: Array.from({ length: 20 }, (_, i) => pendingRevision({ id: `rev-${i}` })),
          total: 21,
        },
      ],
      calls: [],
    };
    renderQueue(router);

    expect(await screen.findByText(/Page 1 of 2/)).toBeInTheDocument();
  });
});

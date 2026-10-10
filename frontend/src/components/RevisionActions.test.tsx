import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import { AxiosError } from "axios";
import { api, createClient } from "../api/client";
import type { Revision, Role } from "../api/types";
import { MemoryRouter } from "react-router-dom";
import { routerFuture } from "../routerFuture";
import { AuthProvider } from "../auth/AuthContext";
import { setStoredToken } from "../auth/storage";
import { RevisionActions } from "./RevisionActions";

const ME = {
  id: "u2",
  email: "approver@proofchain.local",
  full_name: "Approver",
  is_active: true,
  created_at: "2024-01-01T00:00:00Z",
};

function revision(overrides: Partial<Revision> = {}, anchor: Partial<Revision["anchor"]> = {}) {
  return {
    id: "r1",
    document_id: "d1",
    revision_no: 2,
    status: "APPROVED",
    version_no: 2,
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
      ...anchor,
    },
    revocation: null,
    ...overrides,
  } as Revision;
}

function response(config: InternalAxiosRequestConfig, data: unknown, status = 200) {
  return { data, status, statusText: "", headers: {}, config } as AxiosResponse;
}

function ok(data: unknown, status = 200): AxiosAdapter {
  return (config) => Promise.resolve(response(config, data, status));
}

function fail(status: number, code: string, message: string): AxiosAdapter {
  return (config) =>
    Promise.reject(
      new AxiosError(
        "failed",
        "ERR_BAD_REQUEST",
        config,
        null,
        response(config, { error: { code, message } }, status),
      ),
    );
}

function renderActions(roles: Role[], rev: Revision, post?: AxiosAdapter) {
  setStoredToken("test-token");
  api.defaults.adapter = post ?? ok({});
  const authClient = createClient({ adapter: ok({ ...ME, roles }) });
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter future={routerFuture}>
        <AuthProvider client={authClient}>
          <RevisionActions revision={rev} />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const revokeButton = () => screen.findByRole("button", { name: /^revoke$/i });

describe("RevisionActions: revoke", () => {
  it("shows Revoke to an APPROVER for an approved, anchored revision", async () => {
    renderActions(["APPROVER"], revision());
    expect(await revokeButton()).toBeInTheDocument();
  });

  it.each([
    ["a VERIFIER", ["VERIFIER"] as Role[], revision()],
    ["an ADMIN only", ["ADMIN"] as Role[], revision()],
    ["a PENDING revision", ["APPROVER"] as Role[], revision({ status: "PENDING" })],
    ["a REVOKED revision", ["APPROVER"] as Role[], revision({ status: "REVOKED" })],
    ["an unanchored revision", ["APPROVER"] as Role[], revision({}, { status: "ANCHORING" })],
  ])("hides Revoke for %s", async (_label, roles, rev) => {
    renderActions(roles, rev);
    // Let the AuthProvider resolve the user before asserting absence.
    await waitFor(() => expect(screen.queryByRole("button", { name: /^revoke$/i })).toBeNull());
    expect(screen.queryByRole("button", { name: /retry anchor/i })).toBeNull();
  });

  it("asks for a confirmation with a required reason before sending anything", async () => {
    let calls = 0;
    renderActions(["APPROVER"], revision(), (config) => {
      calls += 1;
      return ok({})(config);
    });
    await userEvent.click(await revokeButton());
    expect(screen.getByText(/cannot be undone/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /confirm revoke/i }));
    expect(await screen.findByText(/a reason is required/i)).toBeInTheDocument();
    expect(calls).toBe(0);
  });

  it("Cancel closes the confirmation without sending", async () => {
    let calls = 0;
    renderActions(["APPROVER"], revision(), (config) => {
      calls += 1;
      return ok({})(config);
    });
    await userEvent.click(await revokeButton());
    await userEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(screen.queryByText(/cannot be undone/i)).not.toBeInTheDocument();
    expect(calls).toBe(0);
  });

  it("sends the trimmed reason to POST /revisions/{id}/revoke", async () => {
    let url = "";
    let body = "";
    renderActions(["APPROVER"], revision(), (config) => {
      url = config.url ?? "";
      body = String(config.data);
      return ok(revision({ status: "REVOKED" }))(config);
    });
    await userEvent.click(await revokeButton());
    await userEvent.type(screen.getByLabelText(/reason/i), "  Signed by mistake  ");
    await userEvent.click(screen.getByRole("button", { name: /confirm revoke/i }));
    await waitFor(() => expect(url).toBe("/revisions/r1/revoke"));
    expect(JSON.parse(body)).toEqual({ reason: "Signed by mistake" });
    await waitFor(() => expect(screen.queryByText(/cannot be undone/i)).not.toBeInTheDocument());
  });

  it.each([
    [409, "REVISION_NOT_APPROVED", /only an approved revision/i],
    [409, "CONFLICT", /not anchored on-chain yet/i],
    [503, "CHAIN_UNAVAILABLE", /blockchain is unreachable/i],
    [403, "FORBIDDEN", /requires the approver role/i],
  ])("shows %s %s as an error and keeps the form open", async (status, code, expected) => {
    renderActions(["APPROVER"], revision(), fail(status, code, "raw server message"));
    await userEvent.click(await revokeButton());
    await userEvent.type(screen.getByLabelText(/reason/i), "Wrong version");
    await userEvent.click(screen.getByRole("button", { name: /confirm revoke/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(expected);
    expect(screen.getByLabelText(/reason/i)).toHaveValue("Wrong version");
  });
});

describe("RevisionActions: retry anchor", () => {
  const failed = () =>
    revision({}, { status: "FAILED", tx_hash: null, error: "Contract rejected the transaction" });

  it("shows Retry anchor to an ADMIN for a failed anchor, with the failure reason", async () => {
    renderActions(["ADMIN"], failed());
    expect(await screen.findByRole("button", { name: /retry anchor/i })).toBeInTheDocument();
    expect(screen.getByText(/contract rejected the transaction/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^revoke$/i })).toBeNull();
  });

  it.each([
    ["an APPROVER", ["APPROVER"] as Role[], failed()],
    ["an ADMIN on an anchored revision", ["ADMIN"] as Role[], revision()],
    [
      "an ADMIN on an anchoring revision",
      ["ADMIN"] as Role[],
      revision({}, { status: "ANCHORING" }),
    ],
  ])("hides Retry anchor for %s", async (_label, roles, rev) => {
    renderActions(roles, rev);
    await waitFor(() => expect(screen.queryByRole("button", { name: /retry anchor/i })).toBeNull());
  });

  it("calls POST /revisions/{id}/retry-anchor and reports it was queued", async () => {
    let url = "";
    let method = "";
    renderActions(["ADMIN"], failed(), (config) => {
      url = config.url ?? "";
      method = config.method ?? "";
      return ok(revision({}, { status: "ANCHORING" }), 202)(config);
    });
    await userEvent.click(await screen.findByRole("button", { name: /retry anchor/i }));
    expect(await screen.findByRole("status")).toHaveTextContent(/retry queued/i);
    expect(url).toBe("/revisions/r1/retry-anchor");
    expect(method).toBe("post");
  });

  it("shows an API error in the alert style", async () => {
    renderActions(["ADMIN"], failed(), fail(409, "CONFLICT", "Anchoring is already in progress"));
    await userEvent.click(await screen.findByRole("button", { name: /retry anchor/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/already in progress/i);
  });
});

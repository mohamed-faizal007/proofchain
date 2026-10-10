import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import { AxiosError } from "axios";
import { MemoryRouter, Route, Routes, useParams } from "react-router-dom";
import { api, createClient } from "../api/client";
import type { Role } from "../api/types";
import { AuthProvider } from "../auth/AuthContext";
import { ProtectedRoute } from "../auth/ProtectedRoute";
import { setStoredToken } from "../auth/storage";
import { routerFuture } from "../routerFuture";
import { RevisionNew } from "./RevisionNew";

const ME = {
  id: "u1",
  email: "issuer@proofchain.local",
  full_name: "Issuer",
  is_active: true,
  created_at: "2024-01-01T00:00:00Z",
};

const DOCUMENT = {
  document: { id: "doc-1", title: "Lease Agreement", owner_id: "u1" },
  latest_approved_revision: null,
};

function response(config: InternalAxiosRequestConfig, data: unknown, status: number) {
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

function DetailProbe() {
  const { id } = useParams();
  return <div>Document detail {id}</div>;
}

/** GET answers `document`; POST /documents/doc-1/revisions is handled by `submit`. */
function renderPage(roles: Role[], submit: AxiosAdapter, document: unknown = DOCUMENT) {
  setStoredToken("test-token");
  api.defaults.adapter = (config) =>
    config.method === "post" ? submit(config) : ok(document)(config);
  const authClient = createClient({ adapter: ok({ ...ME, roles }) });
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter future={routerFuture} initialEntries={["/documents/doc-1/revisions/new"]}>
        <AuthProvider client={authClient}>
          <Routes>
            <Route
              path="/documents/:id/revisions/new"
              element={
                <ProtectedRoute>
                  <RevisionNew />
                </ProtectedRoute>
              }
            />
            <Route path="/documents/:id" element={<DetailProbe />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function fillValidForm(note = "Raised the rent"): Promise<void> {
  await userEvent.type(await screen.findByLabelText(/change note/i), note);
  const file = new File(["%PDF-1.4"], "lease-v2.pdf", { type: "application/pdf" });
  await userEvent.upload(screen.getByLabelText(/choose pdf file/i), file);
}

const submitButton = () => screen.getByRole("button", { name: /submit revision/i });

describe("RevisionNew page", () => {
  it("shows a role-required message for a non-ISSUER user", async () => {
    renderPage(["VERIFIER"], ok({}));
    expect(await screen.findByText(/requires the issuer role/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/change note/i)).not.toBeInTheDocument();
  });

  it("refuses an ISSUER who does not own the document", async () => {
    renderPage(["ISSUER"], ok({}), {
      ...DOCUMENT,
      document: { ...DOCUMENT.document, owner_id: "u9" },
    });
    expect(await screen.findByText(/only the owner of this document/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/change note/i)).not.toBeInTheDocument();
  });

  it("renders the form with the document title", async () => {
    renderPage(["ISSUER"], ok({}));
    expect(await screen.findByLabelText(/change note/i)).toBeInTheDocument();
    expect(screen.getByText("Lease Agreement")).toBeInTheDocument();
    expect(screen.getByLabelText(/choose pdf file/i)).toBeInTheDocument();
  });

  it("requires a file and a change note before submitting", async () => {
    let calls = 0;
    renderPage(["ISSUER"], (config) => {
      calls += 1;
      return ok({})(config);
    });
    await screen.findByLabelText(/change note/i);
    await userEvent.click(submitButton());
    expect(await screen.findByText(/change note is required/i)).toBeInTheDocument();
    expect(await screen.findByText(/select a pdf file/i)).toBeInTheDocument();
    expect(calls).toBe(0);
  });

  it("clears the change-note error once the user types a note", async () => {
    renderPage(["ISSUER"], ok({}));
    await screen.findByLabelText(/change note/i);
    await userEvent.click(submitButton());
    expect(await screen.findByText(/change note is required/i)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText(/change note/i), "x");
    expect(screen.queryByText(/change note is required/i)).not.toBeInTheDocument();
  });

  it("uploads the file and note, then redirects to the document detail page", async () => {
    let sent: FormData | undefined;
    renderPage(["ISSUER"], (config) => {
      sent = config.data as FormData;
      return ok(
        { document: { id: "doc-1" }, revision: { id: "rev-2", status: "PENDING" } },
        201,
      )(config);
    });
    await fillValidForm();
    await userEvent.click(submitButton());
    expect(await screen.findByText("Document detail doc-1")).toBeInTheDocument();
    expect(sent?.get("change_note")).toBe("Raised the rent");
    expect((sent?.get("file") as File).name).toBe("lease-v2.pdf");
  });

  it.each([
    [409, "PENDING_REVISION_EXISTS", /already waiting for approval/i],
    [422, "NO_CONTENT_CHANGE", /identical to the latest approved/i],
    [413, "FILE_TOO_LARGE", /too large/i],
    [422, "INVALID_PDF", /not a valid pdf/i],
    [403, "FORBIDDEN", /only the owner of this document/i],
  ])("shows %s %s as an error and stays on the form", async (status, code, expectedText) => {
    renderPage(["ISSUER"], fail(status, code, "raw server message"));
    await fillValidForm();
    await userEvent.click(submitButton());
    expect(await screen.findByRole("alert")).toHaveTextContent(expectedText);
    expect(screen.queryByText(/document detail/i)).not.toBeInTheDocument();
  });

  it("falls back to the server message for an unmapped error code", async () => {
    renderPage(["ISSUER"], fail(500, "INTERNAL_ERROR", "Something broke on the server"));
    await fillValidForm();
    await userEvent.click(submitButton());
    expect(await screen.findByRole("alert")).toHaveTextContent(/something broke on the server/i);
  });

  it("sends exactly one request when the submit button is double-clicked", async () => {
    let calls = 0;
    renderPage(["ISSUER"], (config) => {
      calls += 1;
      return ok({ document: { id: "doc-1" }, revision: { id: "rev-2" } }, 201)(config);
    });
    await fillValidForm();
    const button = submitButton();
    fireEvent.click(button);
    fireEvent.click(button);
    await waitFor(() => expect(screen.getByText("Document detail doc-1")).toBeInTheDocument());
    expect(calls).toBe(1);
  });
});

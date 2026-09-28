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
import { DocumentNew } from "./DocumentNew";

const ME = {
  id: "u1",
  email: "issuer@proofchain.local",
  full_name: "Issuer",
  is_active: true,
  created_at: "2024-01-01T00:00:00Z",
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

function DocIdProbe() {
  const { id } = useParams();
  return <div>Document detail {id}</div>;
}

/** documentsAdapter backs the shared `api` client (used by useCreateDocument); it is only
 *  invoked on submit, well after render, so setting it before render() is enough. */
function renderDocumentNew(roles: Role[], documentsAdapter?: AxiosAdapter) {
  setStoredToken("test-token");
  if (documentsAdapter) api.defaults.adapter = documentsAdapter;
  const authClient = createClient({ adapter: ok({ ...ME, roles }) });

  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter future={routerFuture} initialEntries={["/documents/new"]}>
        <AuthProvider client={authClient}>
          <Routes>
            <Route
              path="/documents/new"
              element={
                <ProtectedRoute>
                  <DocumentNew />
                </ProtectedRoute>
              }
            />
            <Route path="/documents/:id" element={<DocIdProbe />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function fillValidForm(): Promise<void> {
  await userEvent.type(await screen.findByLabelText(/title/i), "Lease Agreement");
  const file = new File(["%PDF-1.4"], "lease.pdf", { type: "application/pdf" });
  await userEvent.upload(screen.getByLabelText(/choose pdf file/i), file);
}

describe("DocumentNew page", () => {
  it("shows a role-required message for a non-ISSUER user", async () => {
    renderDocumentNew(["VERIFIER"]);
    expect(await screen.findByText(/requires the issuer role/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/title/i)).not.toBeInTheDocument();
  });

  it("validates the required title and file before submitting", async () => {
    renderDocumentNew(["ISSUER"]);
    await screen.findByLabelText(/title/i);
    await userEvent.click(screen.getByRole("button", { name: /create document/i }));
    expect(await screen.findByText(/title is required/i)).toBeInTheDocument();
    expect(await screen.findByText(/select a pdf file/i)).toBeInTheDocument();
  });

  it("rejects a non-PDF file by extension/type before ever uploading it", async () => {
    renderDocumentNew(["ISSUER"]);
    await userEvent.type(await screen.findByLabelText(/title/i), "Lease");
    // Dropped (not picked through the accept-filtered native input) so extension/type
    // validation is what catches it, not the browser's own file picker filter.
    const notPdf = new File(["hello"], "notes.txt", { type: "text/plain" });
    fireEvent.drop(screen.getByTestId("file-dropzone"), { dataTransfer: { files: [notPdf] } });
    await userEvent.click(screen.getByRole("button", { name: /create document/i }));
    expect(await screen.findByText(/file must be a \.pdf file/i)).toBeInTheDocument();
  });

  it("uploads a valid PDF and navigates to the new document", async () => {
    renderDocumentNew(
      ["ISSUER"],
      ok({
        document: { id: "doc-42", title: "Lease Agreement" },
        revision: { id: "rev-1", revision_no: 1 },
      }),
    );
    await fillValidForm();
    await userEvent.click(screen.getByRole("button", { name: /create document/i }));
    expect(await screen.findByText("Document detail doc-42")).toBeInTheDocument();
  });

  it.each([
    ["FILE_TOO_LARGE", 413, /too large/i],
    ["INVALID_PDF", 422, /not a valid pdf/i],
    ["ENCRYPTED_PDF", 422, /encrypted pdfs are not supported/i],
    ["NO_EXTRACTABLE_TEXT", 422, /no extractable text/i],
  ])("maps %s to a clear message", async (code, status, expectedText) => {
    renderDocumentNew(["ISSUER"], fail(status, code, "raw server message"));
    await fillValidForm();
    await userEvent.click(screen.getByRole("button", { name: /create document/i }));
    expect(await screen.findByText(expectedText)).toBeInTheDocument();
  });

  it("maps a 403 to an ISSUER-role message", async () => {
    renderDocumentNew(["ISSUER"], fail(403, "FORBIDDEN", "raw server message"));
    await fillValidForm();
    await userEvent.click(screen.getByRole("button", { name: /create document/i }));
    expect(await screen.findByText(/requires the issuer role/i)).toBeInTheDocument();
  });

  it("sends exactly one request when the submit button is double-clicked", async () => {
    let callCount = 0;
    const countingAdapter: AxiosAdapter = (config: InternalAxiosRequestConfig) => {
      callCount += 1;
      return Promise.resolve({
        data: { document: { id: "doc-1" }, revision: { id: "rev-1" } },
        status: 201,
        statusText: "Created",
        headers: {},
        config,
      } as AxiosResponse);
    };
    renderDocumentNew(["ISSUER"], countingAdapter);
    await fillValidForm();

    const button = screen.getByRole("button", { name: /create document/i });
    fireEvent.click(button);
    fireEvent.click(button);

    await waitFor(() => expect(screen.getByText("Document detail doc-1")).toBeInTheDocument());
    expect(callCount).toBe(1);
  });
});

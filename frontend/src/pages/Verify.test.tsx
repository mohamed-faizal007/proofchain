import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import { AxiosError } from "axios";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, vi } from "vitest";
import { api, createClient } from "../api/client";
import type { Role } from "../api/types";
import { AuthProvider } from "../auth/AuthContext";
import { setStoredToken } from "../auth/storage";
import { routerFuture } from "../routerFuture";
import { makeReport } from "../test/verificationFixtures";
import { Verify } from "./Verify";

const openPdf = vi.hoisted(() => vi.fn());
vi.mock("../lib/pdfjs", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../lib/pdfjs")>()),
  openPdf,
}));

const reply = (config: InternalAxiosRequestConfig, data: unknown): AxiosResponse => ({
  data,
  status: 200,
  statusText: "OK",
  headers: {},
  config,
});

function failure(
  config: InternalAxiosRequestConfig,
  status: number,
  code: string,
  message: string,
) {
  const response = {
    data: { error: { code, message } },
    status,
    statusText: "",
    headers: {},
    config,
  };
  return Promise.reject(
    new AxiosError("failed", "ERR_BAD_REQUEST", config, null, response as never),
  );
}

interface Sent {
  file: File | null;
  documentId: string | null;
  includeNlp: string | null;
}
let posts: Sent[] = [];
let downloads: string[] = [];
let verifyImpl: (config: InternalAxiosRequestConfig) => Promise<AxiosResponse>;

function installAdapter() {
  posts = [];
  downloads = [];
  api.defaults.adapter = ((config: InternalAxiosRequestConfig) => {
    const url = String(config.url);
    if (url === "/verify") {
      const form = config.data as FormData;
      posts.push({
        file: form.get("file") as File | null,
        documentId: form.get("document_id") as string | null,
        includeNlp: form.get("include_nlp") as string | null,
      });
      return verifyImpl(config);
    }
    if (url === "/documents") {
      return Promise.resolve(
        reply(config, {
          items: [{ id: "doc-1", title: "Lease Agreement" }],
          page: 1,
          page_size: 100,
          total: 1,
        }),
      );
    }
    if (url.endsWith("/download")) {
      downloads.push(url);
      return Promise.resolve(reply(config, new Blob(["REF"], { type: "application/pdf" })));
    }
    return Promise.reject(new Error(`unexpected ${url}`));
  }) as AxiosAdapter;
}

function renderVerify(roles: Role[] | null) {
  if (roles) setStoredToken("t");
  else setStoredToken(null);
  const authClient = createClient({
    adapter: ((config: InternalAxiosRequestConfig) =>
      Promise.resolve(
        reply(config, {
          id: "u1",
          email: "a@b.c",
          full_name: "A",
          roles: roles ?? [],
          is_active: true,
          created_at: "2024-01-01T00:00:00Z",
        }),
      )) as AxiosAdapter,
  });
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter future={routerFuture}>
        <AuthProvider client={authClient}>
          <Verify />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const pdf = () => new File(["CAND"], "upload.pdf", { type: "application/pdf" });

async function chooseFile(file = pdf()) {
  const input = await screen.findByLabelText("Choose PDF file");
  await userEvent.upload(input, file);
}
const submit = () => userEvent.click(screen.getByRole("button", { name: /^verify$/i }));

beforeEach(() => {
  installAdapter();
  verifyImpl = (config) => Promise.resolve(reply(config, makeReport()));
  openPdf.mockReset();
  openPdf.mockImplementation(async () => ({
    numPages: 1,
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

describe("Verify: form", () => {
  it("shows a required-file error and sends nothing when no file is chosen", async () => {
    renderVerify(null);
    await submit();
    expect(await screen.findByText("Select a PDF file.")).toBeInTheDocument();
    expect(posts).toHaveLength(0);
  });

  it("rejects a non-PDF client-side", async () => {
    renderVerify(null);
    // fireEvent, not userEvent.upload: the latter honours the input's `accept` and drops the file.
    fireEvent.change(await screen.findByLabelText("Choose PDF file"), {
      target: { files: [new File(["x"], "notes.txt", { type: "text/plain" })] },
    });
    await submit();
    expect(await screen.findByText(/must be a \.pdf file/i)).toBeInTheDocument();
    expect(posts).toHaveLength(0);
  });

  it("anonymous: sends multipart file + include_nlp=true and no document_id or picker", async () => {
    renderVerify(null);
    expect(screen.queryByLabelText(/compare against a document/i)).not.toBeInTheDocument();
    await chooseFile();
    await submit();
    await screen.findByRole("region", { name: "Verdict" });
    expect(posts).toHaveLength(1);
    expect(posts[0]?.file?.name).toBe("upload.pdf");
    expect(posts[0]?.includeNlp).toBe("true");
    expect(posts[0]?.documentId).toBeNull();
  });

  it("signed in: sends the picked document_id and include_nlp=false when unchecked", async () => {
    renderVerify(["VERIFIER"]);
    const picker = await screen.findByLabelText(/compare against a document/i);
    await screen.findByRole("option", { name: "Lease Agreement" }); // options load after sign-in
    await userEvent.selectOptions(picker, "doc-1");
    await userEvent.click(screen.getByLabelText(/explain the changes/i));
    await chooseFile();
    await submit();
    await screen.findByRole("region", { name: "Verdict" });
    expect(posts[0]?.documentId).toBe("doc-1");
    expect(posts[0]?.includeNlp).toBe("false");
  });

  it.each([
    [422, "INVALID_PDF", /not a valid pdf/i],
    [422, "ENCRYPTED_PDF", /encrypted pdfs are not supported/i],
    [422, "NO_EXTRACTABLE_TEXT", /no extractable text/i],
    [413, "FILE_TOO_LARGE", /too large/i],
  ])("maps %s %s to a readable message", async (status, code, pattern) => {
    verifyImpl = (config) => failure(config, status, code, "server text");
    renderVerify(null);
    await chooseFile();
    await submit();
    expect(await screen.findByRole("alert")).toHaveTextContent(pattern);
  });

  it("shows the busy state and sends exactly one request on a double click", async () => {
    let release: (r: AxiosResponse) => void = () => {};
    verifyImpl = (config) =>
      new Promise((resolve) => {
        release = () => resolve(reply(config, makeReport()));
      });
    renderVerify(null);
    await chooseFile();
    const button = screen.getByRole("button", { name: /^verify$/i });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(await screen.findByRole("button", { name: /verifying/i })).toBeDisabled();
    expect(posts).toHaveLength(1);
    release(reply({} as InternalAxiosRequestConfig, null));
    await screen.findByRole("region", { name: "Verdict" });
  });
});

describe("Verify: fresh inline result (the uploaded File is still in memory)", () => {
  it("signed in: candidate viewer, reference viewer, no 'not stored' banner, link to the saved report", async () => {
    renderVerify(["VERIFIER"]);
    await chooseFile();
    await submit();
    const candidate = await screen.findByTestId("viewer-candidate");
    expect(await within(candidate).findByTestId("pdf-page-1")).toBeInTheDocument();
    expect(
      await within(screen.getByTestId("viewer-reference")).findByTestId("pdf-page-1"),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("candidate-not-stored")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open saved report/i })).toHaveAttribute(
      "href",
      "/verifications/ver-1",
    );
    expect(downloads).toEqual(["/revisions/rev-ref/download"]);
  });

  it("anonymous: candidate viewer works, the reference is hidden as 'sign in', no saved link", async () => {
    renderVerify(null);
    await chooseFile();
    await submit();
    expect(await screen.findByTestId("reference-hidden-anonymous")).toBeInTheDocument();
    expect(
      await within(await screen.findByTestId("viewer-candidate")).findByTestId("pdf-page-1"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /open saved report/i })).not.toBeInTheDocument();
    expect(downloads).toEqual([]);
  });

  it("'Verify another file' returns to an empty form", async () => {
    renderVerify(null);
    await chooseFile();
    await submit();
    await userEvent.click(await screen.findByRole("button", { name: /verify another file/i }));
    await waitFor(() => expect(screen.getByText(/drag and drop a pdf here/i)).toBeInTheDocument());
  });
});

describe("Verify: unknown document", () => {
  const unknown = () => makeReport({ verdict: "UNKNOWN_DOCUMENT", document: null });

  it("signed in: offers a document picker and re-verifies the same file against the pick", async () => {
    verifyImpl = (config) => {
      const documentId = (config.data as FormData).get("document_id");
      return Promise.resolve(
        reply(config, documentId ? makeReport({ verdict: "TAMPERED" }) : unknown()),
      );
    };
    renderVerify(["VERIFIER"]);
    await chooseFile();
    await submit();
    const picker = await screen.findByLabelText("Document to compare against");
    await screen.findByRole("option", { name: "Lease Agreement" });
    const rerun = screen.getByRole("button", { name: /verify against this document/i });
    expect(rerun).toBeDisabled();
    await userEvent.selectOptions(picker, "doc-1");
    await userEvent.click(rerun);
    await waitFor(() =>
      expect(screen.getByRole("region", { name: "Verdict" })).toHaveAttribute(
        "data-verdict",
        "TAMPERED",
      ),
    );
    expect(posts).toHaveLength(2);
    expect(posts[1]?.documentId).toBe("doc-1");
    expect(posts[1]?.file?.name).toBe("upload.pdf");
    expect(screen.queryByLabelText("Document to compare against")).not.toBeInTheDocument();
  });

  it("anonymous: no picker (the document list needs a sign-in)", async () => {
    verifyImpl = (config) => Promise.resolve(reply(config, unknown()));
    renderVerify(null);
    await chooseFile();
    await submit();
    await screen.findByRole("region", { name: "Verdict" });
    expect(screen.queryByLabelText("Document to compare against")).not.toBeInTheDocument();
  });
});

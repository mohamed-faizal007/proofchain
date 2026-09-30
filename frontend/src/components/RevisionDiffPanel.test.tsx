import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import { AxiosError } from "axios";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import { api } from "../api/client";
import type { RevisionDiff, Revision, RevisionStatus } from "../api/types";
import type { PdfViewerProps } from "./PdfViewerWithHighlights";
import { routerFuture } from "../routerFuture";
import { ANALYSIS_R1, localizationWith, region } from "../test/verificationFixtures";
import { RevisionDiffPanel } from "./RevisionDiffPanel";

// The viewer itself is covered elsewhere; here we only care which revision / highlights it gets.
vi.mock("./LazyPdfViewer", () => ({
  default: (props: PdfViewerProps) => (
    <div
      data-testid={`viewer-${props.revisionId}`}
      data-highlights={props.highlights.length}
      data-focused={props.focusedId ?? ""}
    />
  ),
}));

function rev(id: string, no: number, status: RevisionStatus, parent: string | null): Revision {
  return {
    id,
    document_id: "doc-1",
    revision_no: no,
    parent_revision_id: parent,
    change_note: null,
    status,
    version_no: status === "APPROVED" ? no : null,
    submitted_by: "u1",
    submitted_at: "2026-01-01T00:00:00Z",
    reviewed_by: null,
    reviewed_at: null,
    review_comment: null,
    original_filename: `v${no}.pdf`,
    size_bytes: 1,
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
  };
}

const R1 = rev("r1", 1, "APPROVED", null);
const R2 = rev("r2", 2, "REJECTED", "r1");
const R3 = rev("r3", 3, "PENDING", "r1");
const REVISIONS = [R1, R2, R3];

/** RevisionDiffOut (04_API_SPEC): no verdict, no steps, no chain_check. */
function diffFor(id: string, against: string, analysis: RevisionDiff["analysis"] = null) {
  return {
    revision_id: id,
    against_revision_id: against,
    localization: localizationWith([
      region({
        id: "r1",
        ref_page: 0,
        cand_page: 0,
        ref_bbox: [1, 1, 2, 2],
        cand_bbox: [3, 3, 4, 4],
        cand_text: "Rent is 80,000",
        ref_text: "Rent is 50,000",
      }),
    ]),
    analysis,
  };
}

const json = (config: InternalAxiosRequestConfig, data: unknown, status = 200): AxiosResponse =>
  ({ data, status, statusText: "", headers: {}, config }) as AxiosResponse;

interface Call {
  url: string;
  against: string | undefined;
}

function install(opts: {
  calls: Call[];
  parents?: Record<string, string>;
  analysis?: RevisionDiff["analysis"];
  fail?: { status: number; code: string; message: string };
}) {
  const adapter: AxiosAdapter = (config) => {
    const m = /^\/revisions\/([^/]+)\/diff$/.exec(config.url ?? "");
    if (!m) return Promise.reject(new Error(`unexpected ${config.url}`));
    const against = (config.params as { against?: string } | undefined)?.against;
    opts.calls.push({ url: config.url ?? "", against });
    if (opts.fail) {
      const response = json(
        config,
        { error: { code: opts.fail.code, message: opts.fail.message } },
        opts.fail.status,
      );
      return Promise.reject(new AxiosError("failed", "ERR_BAD_REQUEST", config, null, response));
    }
    const ref = against ?? opts.parents?.[m[1]] ?? "r1";
    return Promise.resolve(json(config, diffFor(m[1], ref, opts.analysis ?? null)));
  };
  api.defaults.adapter = adapter;
}

function renderPanel(revisions: Revision[], opts: Parameters<typeof install>[0]) {
  install(opts);
  return render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter future={routerFuture}>
        <RevisionDiffPanel revisions={revisions} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("RevisionDiffPanel", () => {
  it("defaults to the latest revision against its parent (no `against` param)", async () => {
    const calls: Call[] = [];
    renderPanel(REVISIONS, { calls, parents: { r3: "r1" } });
    expect(await screen.findByTestId("viewer-r3")).toBeInTheDocument();
    expect(calls).toEqual([{ url: "/revisions/r3/diff", against: undefined }]);
    // reference pane uses the against_revision_id the server resolved
    expect(screen.getByTestId("viewer-r1")).toHaveAttribute("data-highlights", "1");
    expect(screen.getByTestId("viewer-r3")).toHaveAttribute("data-highlights", "1");
  });

  it("renders a RevisionDiffOut-shaped response (no verdict/steps/chain_check) cleanly", async () => {
    const { container } = renderPanel(REVISIONS, { calls: [] });
    await screen.findByTestId("viewer-r3");
    // The change list is there...
    expect(screen.getByRole("region", { name: "Changes" })).toBeInTheDocument();
    expect(screen.getByText("Page 1")).toBeInTheDocument();
    // ...and none of the /verify-only UI is left behind as an empty shell.
    expect(screen.queryByRole("region", { name: "Verdict" })).toBeNull();
    expect(screen.queryByRole("region", { name: "Chain proof" })).toBeNull();
    expect(screen.queryByText(/pipeline/i)).toBeNull();
    expect(screen.queryByText(/chain proof/i)).toBeNull();
    expect(screen.queryByText(/uploaded file/i)).toBeNull();
    expect(screen.queryByTestId("candidate-not-stored")).toBeNull();
    // No missing field leaked into the DOM as text, and no heading is an empty shell.
    expect(container.textContent).not.toMatch(/undefined|null|NaN/);
    for (const h of screen.getAllByRole("heading")) expect(h.textContent?.trim()).not.toBe("");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("renders analysis explanations when present, and works with analysis null", async () => {
    const { unmount } = renderPanel(REVISIONS, { calls: [], analysis: [ANALYSIS_R1] });
    expect(await screen.findByText(/Section 4 \(Payment Terms\)/)).toBeInTheDocument();
    unmount();
    renderPanel(REVISIONS, { calls: [], analysis: null });
    await screen.findByTestId("viewer-r3");
    expect(screen.queryByText(/Section 4/)).toBeNull();
  });

  it("any revision is a valid side (spec: any status may be diffed), labelled by status", async () => {
    const calls: Call[] = [];
    renderPanel(REVISIONS, { calls });
    await screen.findByTestId("viewer-r3");
    const reference = screen.getByLabelText(/reference/i);
    const labels = within(reference)
      .getAllByRole("option")
      .map((o) => o.textContent);
    expect(labels[0]).toMatch(/parent/i);
    expect(labels.some((l) => /v2.*rejected/i.test(l ?? ""))).toBe(true);
    expect(labels.some((l) => /v1.*approved/i.test(l ?? ""))).toBe(true);
    // the candidate cannot be its own reference
    expect(labels.some((l) => /v3/.test(l ?? ""))).toBe(false);

    await userEvent.selectOptions(reference, "r2");
    await waitFor(() => expect(calls.at(-1)).toEqual({ url: "/revisions/r3/diff", against: "r2" }));
  });

  it("changing the candidate refetches and resets the reference to the parent default", async () => {
    const calls: Call[] = [];
    renderPanel(REVISIONS, { calls, parents: { r2: "r1" } });
    await screen.findByTestId("viewer-r3");
    await userEvent.selectOptions(screen.getByLabelText(/reference/i), "r2");
    await userEvent.selectOptions(screen.getByLabelText(/candidate/i), "r2");
    await waitFor(() =>
      expect(calls.at(-1)).toEqual({ url: "/revisions/r2/diff", against: undefined }),
    );
    expect((screen.getByLabelText(/reference/i) as HTMLSelectElement).value).toBe("");
  });

  it("a candidate with no parent needs an explicit reference and sends nothing until chosen", async () => {
    const calls: Call[] = [];
    renderPanel(REVISIONS, { calls });
    await screen.findByTestId("viewer-r3");
    await userEvent.selectOptions(screen.getByLabelText(/candidate/i), "r1");
    expect(await screen.findByText(/no parent.*choose a reference/i)).toBeInTheDocument();
    expect(calls.filter((c) => c.url === "/revisions/r1/diff")).toHaveLength(0);
    await userEvent.selectOptions(screen.getByLabelText(/reference/i), "r3");
    await waitFor(() => expect(calls.at(-1)).toEqual({ url: "/revisions/r1/diff", against: "r3" }));
  });

  it("a document with a single revision explains that a diff needs two, and requests nothing", () => {
    const calls: Call[] = [];
    renderPanel([R1], { calls });
    expect(screen.getByText(/at least two revisions/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/candidate/i)).toBeNull();
    expect(calls).toHaveLength(0);
  });

  it("explains a canonicalization-version conflict (409)", async () => {
    renderPanel(REVISIONS, {
      calls: [],
      fail: { status: 409, code: "CONFLICT", message: "canon mismatch" },
    });
    expect(await screen.findByRole("alert")).toHaveTextContent(/canonicalization version/i);
  });

  it("shows the server message for a 422", async () => {
    renderPanel(REVISIONS, {
      calls: [],
      fail: {
        status: 422,
        code: "VALIDATION_ERROR",
        message: "against belongs to another document",
      },
    });
    expect(await screen.findByRole("alert")).toHaveTextContent(/another document/);
  });

  it("clicking a change focuses it in both viewers", async () => {
    renderPanel(REVISIONS, { calls: [] });
    await screen.findByTestId("viewer-r3");
    await userEvent.click(within(screen.getByTestId("change-r1")).getByRole("button"));
    expect(screen.getByTestId("viewer-r3")).toHaveAttribute("data-focused", "r1");
    expect(screen.getByTestId("viewer-r1")).toHaveAttribute("data-focused", "r1");
  });

  it("says so when the revisions are identical", async () => {
    install({ calls: [] });
    const identical = {
      ...diffFor("r3", "r1"),
      localization: { ...localizationWith([]), status: "IDENTICAL" },
    };
    api.defaults.adapter = ((config: InternalAxiosRequestConfig) =>
      Promise.resolve(json(config, identical))) as AxiosAdapter;
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter future={routerFuture}>
          <RevisionDiffPanel revisions={REVISIONS} />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText(/identical/i)).toBeInTheDocument();
  });
});

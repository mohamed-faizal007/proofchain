import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, vi } from "vitest";
import { api } from "../api/client";
import type { AnalysisItem, ChangeRegion, VerificationReport } from "../api/types";
import type { PdfDocLike, PdfPageLike } from "../lib/pdfjs";
import { routerFuture } from "../routerFuture";
import {
  ANALYSIS_R1,
  localizationWith,
  makeReport,
  REFERENCE,
  region,
} from "../test/verificationFixtures";
import { CANDIDATE_NOT_STORED_MESSAGE, VerificationReportView } from "./VerificationReportView";

// pdf.js is mocked; which fake document comes back depends on the bytes handed to openPdf, so
// the reference and candidate viewers can be given DIFFERENT page counts.
const openPdf = vi.hoisted(() => vi.fn());
vi.mock("../lib/pdfjs", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../lib/pdfjs")>()),
  openPdf,
}));

const PAGE_W = 600;
const SCALE = 800 / PAGE_W; // no layout in jsdom: the viewer falls back to an 800px width

function fakePage(): PdfPageLike {
  return {
    rotate: 0,
    getViewport: ({ scale }) => ({ width: PAGE_W * scale, height: 800 * scale }),
    render: vi.fn(() => ({ promise: new Promise(() => {}), cancel: vi.fn() })),
  };
}
const fakeDoc = (pages: number): PdfDocLike => ({
  numPages: pages,
  getPage: () => Promise.resolve(fakePage()),
  destroy: () => Promise.resolve(),
});

let downloads: string[] = [];

function stubDownloads() {
  downloads = [];
  api.defaults.adapter = ((config: InternalAxiosRequestConfig) => {
    downloads.push(String(config.url));
    return Promise.resolve({
      data: new Blob(["REF"], { type: "application/pdf" }),
      status: 200,
      statusText: "OK",
      headers: {},
      config,
    } as AxiosResponse);
  }) as AxiosAdapter;
}

beforeEach(() => {
  stubDownloads();
  openPdf.mockReset();
  openPdf.mockImplementation(async (buf: ArrayBuffer) => {
    const text = new TextDecoder().decode(buf);
    return fakeDoc(text.startsWith("CAND") ? 3 : 2); // reference: 2 pages, candidate: 3 pages
  });
  vi.stubGlobal("IntersectionObserver", undefined);
});
afterEach(() => vi.unstubAllGlobals());

const candidateFile = () => new File(["CAND"], "upload.pdf", { type: "application/pdf" });

function renderView(props: { report?: VerificationReport; file?: File; isAnonymous?: boolean }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter future={routerFuture}>
        <VerificationReportView
          report={props.report ?? makeReport()}
          candidateFile={props.file}
          isAnonymous={props.isAnonymous ?? false}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const reportWith = (
  regions: ChangeRegion[],
  analysis: AnalysisItem[] | null = null,
): VerificationReport => {
  return { ...makeReport(), analysis, localization: localizationWith(regions) };
};

const left = (el: HTMLElement) => parseFloat(el.style.left);

describe("candidate availability: fresh /verify result vs stored /verifications/:id", () => {
  it("fresh result: the candidate viewer renders from the in-memory File, with no banner", async () => {
    renderView({ file: candidateFile() });
    const candidate = await screen.findByTestId("viewer-candidate");
    expect(await within(candidate).findByTestId("pdf-page-1")).toBeInTheDocument();
    expect(screen.queryByTestId("candidate-not-stored")).not.toBeInTheDocument();
    // The candidate came from the File: the only download is the reference revision.
    expect(downloads).toEqual(["/revisions/rev-ref/download"]);
  });

  it("stored report: a clear banner, the reference viewer, and NO candidate viewer at all", async () => {
    renderView({});
    expect(screen.getByTestId("candidate-not-stored")).toHaveTextContent(
      CANDIDATE_NOT_STORED_MESSAGE,
    );
    expect(CANDIDATE_NOT_STORED_MESSAGE).toBe(
      "The uploaded file isn't stored -- this view shows the reference document and the detected changes, but not the original upload.",
    );
    expect(
      await within(screen.getByTestId("viewer-reference")).findByTestId("pdf-page-1"),
    ).toBeInTheDocument();
    // No empty/broken candidate pane, and pdf.js was only ever opened for the reference.
    expect(screen.queryByTestId("viewer-candidate")).not.toBeInTheDocument();
    expect(screen.queryByText(/^Uploaded$/)).not.toBeInTheDocument();
    expect(openPdf).toHaveBeenCalledTimes(1);
  });

  it("the banner is dismissible", async () => {
    renderView({});
    await userEvent.click(within(screen.getByTestId("candidate-not-stored")).getByRole("button"));
    expect(screen.queryByTestId("candidate-not-stored")).not.toBeInTheDocument();
    expect(screen.getByTestId("viewer-reference")).toBeInTheDocument();
  });
});

describe("page/bbox indexing: ref_* only into the reference viewer, cand_* only into the candidate", () => {
  // Reference has 2 pages, candidate has 3. r1 sits on page index 1 of BOTH documents but with
  // different boxes; r2 exists only on candidate page 3 (index 2); r3 only on reference page 1.
  const A: [number, number, number, number] = [10, 20, 110, 50];
  const B: [number, number, number, number] = [300, 400, 400, 450];
  const C: [number, number, number, number] = [120, 60, 220, 90];
  const D: [number, number, number, number] = [30, 700, 130, 730];
  const regions = [
    region({ id: "r1", type: "MODIFIED", ref_page: 1, ref_bbox: A, cand_page: 1, cand_bbox: B }),
    region({ id: "r2", type: "INSERTED", cand_page: 2, cand_bbox: C }),
    region({ id: "r3", type: "DELETED", ref_page: 0, ref_bbox: D }),
  ];

  it("each viewer draws the right box on the right page", async () => {
    renderView({ report: reportWith(regions), file: candidateFile() });
    const ref = screen.getByTestId("viewer-reference");
    const cand = screen.getByTestId("viewer-candidate");

    // Reference: 2 pages only.
    const refP2 = await within(ref).findByTestId("pdf-page-2");
    const refP1 = within(ref).getByTestId("pdf-page-1");
    expect(within(ref).queryByTestId("pdf-page-3")).not.toBeInTheDocument();
    expect(left(within(refP2).getByTestId("highlight-r1"))).toBeCloseTo(A[0] * SCALE);
    expect(left(within(refP1).getByTestId("highlight-r3"))).toBeCloseTo(D[0] * SCALE);
    expect(within(ref).queryByTestId("highlight-r2")).not.toBeInTheDocument();
    expect(within(refP2).queryByTestId("highlight-r3")).not.toBeInTheDocument();

    // Candidate: 3 pages.
    const candP2 = await within(cand).findByTestId("pdf-page-2");
    const candP3 = await within(cand).findByTestId("pdf-page-3");
    expect(left(within(candP2).getByTestId("highlight-r1"))).toBeCloseTo(B[0] * SCALE);
    expect(left(within(candP3).getByTestId("highlight-r2"))).toBeCloseTo(C[0] * SCALE);
    expect(within(cand).queryByTestId("highlight-r3")).not.toBeInTheDocument();

    // Same page index, different boxes: a ref/cand swap would make these equal.
    expect(left(within(refP2).getByTestId("highlight-r1"))).not.toBeCloseTo(
      left(within(candP2).getByTestId("highlight-r1")),
    );
  });
});

describe("reference viewer hidden: anonymous vs no reference are distinct", () => {
  it("anonymous TAMPERED result WITH a real reference_revision still hides the viewer", async () => {
    const report = reportWith([region({ id: "r1", ref_page: 0, cand_page: 0 })]);
    expect(report.reference_revision).not.toBeNull();
    renderView({ report, file: candidateFile(), isAnonymous: true });
    expect(screen.getByTestId("reference-hidden-anonymous")).toHaveTextContent(
      /sign in to view the reference document/i,
    );
    expect(screen.queryByTestId("reference-hidden-no-reference")).not.toBeInTheDocument();
    await within(screen.getByTestId("viewer-candidate")).findByTestId("pdf-page-1");
    expect(downloads).toEqual([]); // the reference revision is never requested
  });

  it("no reference (reference_revision null) is hidden with its own message and reason", () => {
    const report = makeReport({
      reference_revision: null,
      localization: null,
      no_reference_reason: "NO_APPROVED_REVISION",
    });
    renderView({ report });
    expect(screen.getByTestId("reference-hidden-no-reference")).toHaveTextContent(
      /no reference document was available.*no approved revision/i,
    );
    expect(screen.queryByTestId("reference-hidden-anonymous")).not.toBeInTheDocument();
    expect(downloads).toEqual([]);
  });
});

describe("exact match: the matched revision fills the reference pane", () => {
  it("shows the matched revision instead of 'no reference'", async () => {
    const report = makeReport({
      verdict: "AUTHENTIC_LATEST",
      reference_revision: null,
      matched_revision: REFERENCE,
      localization: null,
    });
    renderView({ report, file: candidateFile() });
    expect(screen.queryByTestId("reference-hidden-no-reference")).not.toBeInTheDocument();
    await within(screen.getByTestId("viewer-reference")).findByTestId("pdf-page-1");
    expect(downloads).toEqual([`/revisions/${REFERENCE.id}/download`]);
  });
});

describe("analysis null (NLP skipped) vs present", () => {
  const regions = [
    region({
      id: "r1",
      ref_page: 0,
      cand_page: 0,
      ref_bbox: [1, 1, 9, 9],
      cand_bbox: [1, 1, 9, 9],
    }),
  ];

  it("analysis null: the change list renders from localization alone, nothing broken or apologetic", () => {
    renderView({ report: reportWith(regions, null) });
    const card = screen.getByTestId("change-r1");
    expect(card).toHaveTextContent(/modified/i);
    expect(card).toHaveTextContent(/page 1/i);
    expect(card).not.toHaveTextContent(/severity/i);
    expect(card).not.toHaveTextContent(/amount change/i);
    expect(within(card).queryByLabelText("Token diff")).not.toBeInTheDocument();
    const changes = screen.getByRole("region", { name: "Changes" });
    expect(changes).not.toHaveTextContent(/unavailable|error|failed|not available/i);
  });

  it("analysis present: category, severity, entity before/after, token diff and explanation", () => {
    renderView({ report: reportWith(regions, [ANALYSIS_R1]) });
    const card = screen.getByTestId("change-r1");
    expect(card).toHaveTextContent(/amount change/i);
    expect(card).toHaveTextContent(/high severity/i);
    expect(card).toHaveTextContent(/₹50,000/);
    expect(card).toHaveTextContent(/₹80,000/);
    expect(within(card).getByLabelText("Token diff")).toHaveTextContent("Rent is ₹50,000 ₹80,000");
    expect(card).toHaveTextContent(/in Section 4 \(Payment Terms\)/);
  });

  it("groups changes by section title, falling back to the page", () => {
    const grouped = [
      region({ id: "a", cand_page: 1, section_id: "s4", section_title: "Payment Terms" }),
      region({ id: "b", cand_page: 1, section_id: "s4", section_title: "Payment Terms" }),
      region({ id: "c", cand_page: 2 }),
    ];
    renderView({ report: reportWith(grouped) });
    const payment = screen.getByRole("region", { name: "Payment Terms" });
    expect(within(payment).getAllByTestId(/^change-/)).toHaveLength(2);
    expect(
      within(screen.getByRole("region", { name: "Page 3" })).getAllByTestId(/^change-/),
    ).toHaveLength(1);
  });

  it("an anonymous (redacted) report with null text/bbox/section renders without crashing", () => {
    const redacted = [region({ id: "r1", ref_page: 0, cand_page: 0 })];
    renderView({ report: reportWith(redacted), file: candidateFile(), isAnonymous: true });
    expect(screen.getByTestId("change-r1")).toBeInTheDocument();
    expect(screen.getByText(/change locations are not included/i)).toBeInTheDocument();
  });
});

describe("click a change: both viewers scroll to and emphasise the right region", () => {
  const A: [number, number, number, number] = [10, 20, 110, 50];
  const B: [number, number, number, number] = [300, 400, 400, 450];
  const regions = [
    region({ id: "r1", type: "MODIFIED", ref_page: 1, ref_bbox: A, cand_page: 1, cand_bbox: B }),
    region({ id: "r2", type: "INSERTED", cand_page: 2, cand_bbox: [120, 60, 220, 90] }),
  ];
  let scrolled: Element[];
  beforeEach(() => {
    scrolled = [];
    Element.prototype.scrollIntoView = vi.fn(function (this: Element) {
      scrolled.push(this);
    });
  });

  it("a MODIFIED change scrolls/emphasises its box in BOTH viewers", async () => {
    renderView({ report: reportWith(regions), file: candidateFile() });
    const ref = screen.getByTestId("viewer-reference");
    const cand = screen.getByTestId("viewer-candidate");
    const refBox = await within(ref).findByTestId("highlight-r1");
    const candBox = await within(cand).findByTestId("highlight-r1");
    expect(refBox.className).not.toMatch(/ring-2/);

    await userEvent.click(within(screen.getByTestId("change-r1")).getByRole("button"));

    await waitFor(() => expect(scrolled).toEqual(expect.arrayContaining([refBox, candBox])));
    expect(refBox.className).toMatch(/ring-2/);
    expect(candBox.className).toMatch(/ring-2/);
    expect(screen.getByTestId("change-r1").className).toMatch(/ring-2/);
  });

  it("an INSERTED change only exists in the candidate viewer, and only that one scrolls", async () => {
    renderView({ report: reportWith(regions), file: candidateFile() });
    const cand = screen.getByTestId("viewer-candidate");
    const ref = screen.getByTestId("viewer-reference");
    const candBox = await within(cand).findByTestId("highlight-r2");
    await within(ref).findByTestId("pdf-page-1");

    await userEvent.click(within(screen.getByTestId("change-r2")).getByRole("button"));

    await waitFor(() => expect(scrolled).toEqual([candBox]));
    expect(candBox.className).toMatch(/ring-2/);
    expect(within(ref).queryByTestId("highlight-r2")).not.toBeInTheDocument();
  });
});

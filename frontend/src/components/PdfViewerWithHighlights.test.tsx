import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from "axios";
import { afterEach, beforeEach, vi } from "vitest";
import { api } from "../api/client";
import type { PageHighlight } from "../lib/bbox";
import type { PdfDocLike, PdfPageLike } from "../lib/pdfjs";
import { PDF_LOAD_OPTIONS } from "../lib/pdfjs";
import PdfViewerWithHighlights from "./PdfViewerWithHighlights";

const openPdf = vi.hoisted(() => vi.fn());
vi.mock("../lib/pdfjs", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../lib/pdfjs")>()),
  openPdf,
}));

// IntersectionObserver that tracks its targets and lets tests fire callbacks manually.
class MockIO {
  static instances: MockIO[] = [];
  targets = new Set<Element>();
  constructor(private cb: IntersectionObserverCallback) {
    MockIO.instances.push(this);
  }
  observe(el: Element) {
    this.targets.add(el);
  }
  unobserve(el: Element) {
    this.targets.delete(el);
  }
  disconnect() {
    this.targets.clear();
  }
  fire(el: Element, isIntersecting: boolean) {
    this.cb([{ target: el, isIntersecting } as IntersectionObserverEntry], this as never);
  }
}
function setIntersecting(el: Element, isIntersecting: boolean) {
  const owners = MockIO.instances.filter((io) => io.targets.has(el));
  expect(owners.length).toBeGreaterThan(0);
  act(() => owners.forEach((io) => io.fire(el, isIntersecting)));
}

interface FakePage extends PdfPageLike {
  tasks: { cancel: ReturnType<typeof vi.fn> }[];
}
function fakePage(rotate = 0, width = 600, height = 800): FakePage {
  const tasks: FakePage["tasks"] = [];
  return {
    rotate,
    tasks,
    getViewport: ({ scale }) => ({ width: width * scale, height: height * scale }),
    render: vi.fn(() => {
      const task = { promise: new Promise(() => {}), cancel: vi.fn() };
      tasks.push(task);
      return task;
    }),
  };
}
function fakeDoc(pages: FakePage[]): PdfDocLike & { destroy: ReturnType<typeof vi.fn> } {
  return {
    numPages: pages.length,
    getPage: (n) => Promise.resolve(pages[n - 1]),
    destroy: vi.fn(() => Promise.resolve()),
  };
}

function stubDownload(impl?: () => Promise<unknown>) {
  api.defaults.adapter = ((config: InternalAxiosRequestConfig) =>
    impl
      ? impl()
      : Promise.resolve({
          data: new Blob(["%PDF-1.4"], { type: "application/pdf" }),
          status: 200,
          statusText: "OK",
          headers: {},
          config,
        } as AxiosResponse)) as AxiosAdapter;
}

function renderViewer(highlights: PageHighlight[] = [], props: { focusedId?: string } = {}) {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <PdfViewerWithHighlights revisionId="r1" highlights={highlights} {...props} />
    </QueryClientProvider>,
  );
}

const hl = (id: string, type: PageHighlight["type"], page: number): PageHighlight => ({
  id,
  type,
  page,
  bbox: [60, 100, 160, 130],
});

beforeEach(() => {
  MockIO.instances = [];
  vi.stubGlobal("IntersectionObserver", MockIO);
  URL.createObjectURL = vi.fn(() => "blob:x");
  URL.revokeObjectURL = vi.fn();
  stubDownload();
  openPdf.mockReset();
});
afterEach(() => vi.unstubAllGlobals());

async function pageEl(n: number) {
  return screen.findByTestId(`pdf-page-${n}`);
}

describe("PdfViewerWithHighlights: loading / error / empty", () => {
  it("shows a loading status while the PDF downloads", async () => {
    stubDownload(() => new Promise(() => {}));
    renderViewer();
    expect(await screen.findByRole("status")).toHaveTextContent(/loading pdf/i);
  });

  it("shows the error with a Retry that refetches", async () => {
    let calls = 0;
    stubDownload(() => {
      calls += 1;
      return Promise.reject(new Error("network down"));
    });
    renderViewer();
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/could not load/i);
    await userEvent.click(within(alert).getByRole("button", { name: /retry/i }));
    await waitFor(() => expect(calls).toBe(2));
  });

  it("shows a distinct message when pdf.js cannot parse the file", async () => {
    openPdf.mockRejectedValue(new Error("Invalid PDF structure"));
    renderViewer();
    expect(await screen.findByRole("alert")).toHaveTextContent(/not a readable pdf/i);
  });

  it("a genuinely empty (0-page) document shows its own message, not the per-page hint", async () => {
    openPdf.mockResolvedValue(fakeDoc([]));
    renderViewer([hl("a", "MODIFIED", 0)]);
    expect(await screen.findByText(/this pdf has no pages/i)).toBeInTheDocument();
    expect(screen.queryByText(/no highlighted changes on this page/i)).not.toBeInTheDocument();
  });

  it("a page with no highlights (while another page has some) shows the per-page hint", async () => {
    openPdf.mockResolvedValue(fakeDoc([fakePage(), fakePage()]));
    renderViewer([hl("a", "MODIFIED", 0)]);
    const page2 = await pageEl(2);
    expect(within(page2).getByText(/no highlighted changes on this page/i)).toBeInTheDocument();
    expect(
      within(await pageEl(1)).queryByText(/no highlighted changes on this page/i),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/this pdf has no pages/i)).not.toBeInTheDocument();
  });
});

describe("PdfViewerWithHighlights: untrusted PDF hardening", () => {
  it("asserts the hardening options (eval off, XFA off, no auto-fetch/stream, no scripting flag)", () => {
    expect(PDF_LOAD_OPTIONS).toEqual({
      isEvalSupported: false,
      enableXfa: false,
      disableAutoFetch: true,
      disableStream: true,
    });
    expect(PDF_LOAD_OPTIONS).not.toHaveProperty("enableScripting");
  });

  it("opens the fetched bytes via openPdf and never creates object URLs or links", async () => {
    openPdf.mockResolvedValue(fakeDoc([fakePage()]));
    renderViewer();
    await pageEl(1);
    expect(openPdf).toHaveBeenCalledTimes(1);
    expect(openPdf.mock.calls[0][0]).toBeInstanceOf(ArrayBuffer);
    expect(URL.createObjectURL).not.toHaveBeenCalled();
    expect(document.querySelector("iframe, embed, object, a[href]")).toBeNull();
  });

  it("destroys the pdf.js document on unmount", async () => {
    const doc = fakeDoc([fakePage()]);
    openPdf.mockResolvedValue(doc);
    const { unmount } = renderViewer();
    await pageEl(1);
    unmount();
    expect(doc.destroy).toHaveBeenCalled();
  });
});

describe("PdfViewerWithHighlights: visible-page-only rendering", () => {
  it("mounts a canvas and renders only when the page intersects, cancels when it leaves", async () => {
    const page = fakePage();
    openPdf.mockResolvedValue(fakeDoc([page]));
    renderViewer();
    const el = await pageEl(1);

    expect(el.querySelector("canvas")).toBeNull();
    expect(page.render).not.toHaveBeenCalled();

    setIntersecting(el, true);
    await waitFor(() => expect(el.querySelector("canvas")).not.toBeNull());
    expect(page.render).toHaveBeenCalledTimes(1);
    expect(page.tasks[0].cancel).not.toHaveBeenCalled();

    setIntersecting(el, false);
    await waitFor(() => expect(el.querySelector("canvas")).toBeNull());
    expect(page.tasks[0].cancel).toHaveBeenCalledTimes(1);
  });

  it("only renders the pages that intersect", async () => {
    const pages = [fakePage(), fakePage(), fakePage()];
    openPdf.mockResolvedValue(fakeDoc(pages));
    renderViewer();
    const el2 = await pageEl(2);
    setIntersecting(el2, true);
    await waitFor(() => expect(pages[1].render).toHaveBeenCalled());
    expect(pages[0].render).not.toHaveBeenCalled();
    expect(pages[2].render).not.toHaveBeenCalled();
  });

  it("cancels an in-flight render on unmount", async () => {
    const page = fakePage();
    openPdf.mockResolvedValue(fakeDoc([page]));
    const { unmount } = renderViewer();
    setIntersecting(await pageEl(1), true);
    await waitFor(() => expect(page.render).toHaveBeenCalled());
    unmount();
    expect(page.tasks[0].cancel).toHaveBeenCalled();
  });
});

describe("PdfViewerWithHighlights: highlights", () => {
  it("draws each type with a colour class, a text label and a distinct border style", async () => {
    openPdf.mockResolvedValue(fakeDoc([fakePage()]));
    renderViewer([
      { ...hl("m", "MODIFIED", 0), bbox: [10, 10, 50, 30] },
      { ...hl("i", "INSERTED", 0), bbox: [10, 40, 50, 60] },
      { ...hl("d", "DELETED", 0), bbox: [10, 70, 50, 90] },
    ]);
    const page = await pageEl(1);
    const m = within(page).getByTestId("highlight-m");
    const i = within(page).getByTestId("highlight-i");
    const d = within(page).getByTestId("highlight-d");

    expect(m).toHaveTextContent("Modified");
    expect(i).toHaveTextContent("Inserted");
    expect(d).toHaveTextContent("Deleted");
    expect(m).toHaveAttribute("aria-label", "Modified region");
    expect(m.className).toMatch(/amber/);
    expect(i.className).toMatch(/green/);
    expect(d.className).toMatch(/red/);
    const styles = [m, i, d].map((n) => n.className.match(/border-(solid|dashed|dotted)/)?.[1]);
    expect(new Set(styles).size).toBe(3);
    expect(screen.getByRole("list", { name: /highlight legend/i })).toBeInTheDocument();
  });

  it("scales boxes with the page width (fit-width = 800px fallback over a 600pt page)", async () => {
    openPdf.mockResolvedValue(fakeDoc([fakePage()]));
    renderViewer([hl("m", "MODIFIED", 0)]); // bbox [60,100,160,130]
    const box = within(await pageEl(1)).getByTestId("highlight-m");
    const s = 800 / 600;
    expect(parseFloat(box.style.left)).toBeCloseTo(60 * s);
    expect(parseFloat(box.style.top)).toBeCloseTo(100 * s);
    expect(parseFloat(box.style.width)).toBeCloseTo(100 * s);
    expect(parseFloat(box.style.height)).toBeCloseTo(30 * s);
  });

  it("zoom +/- and fit-width rescale the overlay boxes (bbox math), not just the canvas", async () => {
    const page = fakePage();
    openPdf.mockResolvedValue(fakeDoc([page]));
    renderViewer([hl("m", "MODIFIED", 0)]);
    const el = await pageEl(1);
    setIntersecting(el, true);
    await waitFor(() => expect(page.render).toHaveBeenCalledTimes(1));
    const box = () => within(el).getByTestId("highlight-m");
    const baseLeft = parseFloat(box().style.left);
    const baseWidth = parseFloat(box().style.width);

    await userEvent.click(screen.getByRole("button", { name: /zoom in/i }));
    await waitFor(() => expect(parseFloat(box().style.left)).toBeCloseTo(baseLeft * 1.25));
    expect(parseFloat(box().style.width)).toBeCloseTo(baseWidth * 1.25);
    expect(parseFloat(el.style.width)).toBeCloseTo(800 * 1.25);
    // the page canvas is re-rendered at the new scale too
    await waitFor(() => expect(page.render).toHaveBeenCalledTimes(2));

    await userEvent.click(screen.getByRole("button", { name: /zoom out/i }));
    await userEvent.click(screen.getByRole("button", { name: /zoom out/i }));
    await waitFor(() => expect(parseFloat(box().style.left)).toBeCloseTo(baseLeft * 0.75));

    await userEvent.click(screen.getByRole("button", { name: /fit width/i }));
    await waitFor(() => expect(parseFloat(box().style.left)).toBeCloseTo(baseLeft));
  });

  it("scrolls the focused highlight into view", async () => {
    openPdf.mockResolvedValue(fakeDoc([fakePage()]));
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    renderViewer([hl("m", "MODIFIED", 0)], { focusedId: "m" });
    await pageEl(1);
    await waitFor(() => expect(scroll).toHaveBeenCalled());
  });
});

describe("PdfViewerWithHighlights: page rotation (out of scope)", () => {
  it("rotate=0 as reported by pdf.js: boxes drawn, no rotation notice", async () => {
    openPdf.mockResolvedValue(fakeDoc([fakePage(0)]));
    renderViewer([hl("m", "MODIFIED", 0)]);
    const page = await pageEl(1);
    expect(within(page).getByTestId("highlight-m")).toBeInTheDocument();
    expect(within(page).queryByText(/rotated/i)).not.toBeInTheDocument();
  });

  it("rotate=90: notice shown and boxes are NOT drawn on that page", async () => {
    openPdf.mockResolvedValue(fakeDoc([fakePage(90)]));
    renderViewer([hl("m", "MODIFIED", 0)]);
    const page = await pageEl(1);
    expect(within(page).getByText(/page is rotated \(90°\)/i)).toBeInTheDocument();
    expect(within(page).queryByTestId("highlight-m")).not.toBeInTheDocument();
  });
});

describe("PdfViewerWithHighlights: in-memory file source (verification upload)", () => {
  it("opens the File's bytes with NO download request and no object URL", async () => {
    let requests = 0;
    stubDownload(() => {
      requests += 1;
      return Promise.reject(new Error("must not be called"));
    });
    openPdf.mockResolvedValue(fakeDoc([fakePage()]));
    const file = new File(["CAND-BYTES"], "upload.pdf", { type: "application/pdf" });
    render(
      <QueryClientProvider client={new QueryClient()}>
        <PdfViewerWithHighlights file={file} highlights={[hl("a", "MODIFIED", 0)]} />
      </QueryClientProvider>,
    );
    expect(await pageEl(1)).toBeInTheDocument();
    const bytes = openPdf.mock.calls[0]?.[0] as ArrayBuffer;
    expect(new TextDecoder().decode(bytes)).toBe("CAND-BYTES");
    expect(requests).toBe(0);
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });
});

import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import LazyPdfViewer from "./LazyPdfViewer";

vi.mock("./PdfViewerWithHighlights", () => ({
  default: () => <div>real viewer</div>,
}));

describe("LazyPdfViewer", () => {
  it("shows a fallback, then the dynamically imported viewer", async () => {
    render(<LazyPdfViewer revisionId="r1" highlights={[]} />);
    expect(screen.getByRole("status")).toHaveTextContent(/loading viewer/i);
    expect(await screen.findByText("real viewer")).toBeInTheDocument();
  });
});

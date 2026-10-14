import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { FileDropzone } from "./FileDropzone";

const zone = () => screen.getByTestId("file-dropzone");
const dragItems = (type: string) => ({
  dataTransfer: { items: [{ kind: "file", type }], files: [] },
});

describe("FileDropzone", () => {
  it("shows the accepted type and size limit before anything is chosen", () => {
    render(<FileDropzone accept=".pdf" onFileSelected={vi.fn()} />);
    expect(screen.getByText(/pdf only, up to \d+ mb/i)).toBeInTheDocument();
  });

  it("highlights a PDF drag-over as droppable", () => {
    render(<FileDropzone accept=".pdf" onFileSelected={vi.fn()} />);
    fireEvent.dragOver(zone(), dragItems("application/pdf"));
    expect(screen.getByText(/drop to select this file/i)).toBeInTheDocument();
    fireEvent.dragLeave(zone());
    expect(screen.queryByText(/drop to select this file/i)).not.toBeInTheDocument();
  });

  it("warns during a drag of a non-PDF, before the drop", () => {
    render(<FileDropzone accept=".pdf" onFileSelected={vi.fn()} />);
    fireEvent.dragOver(zone(), dragItems("image/png"));
    expect(screen.getByText(/only pdf files can be uploaded/i)).toBeInTheDocument();
  });

  it("shows the chosen file name and size, and marks an invalid choice", () => {
    render(
      <FileDropzone
        accept=".pdf"
        onFileSelected={vi.fn()}
        selectedFileName="lease.pdf"
        selectedFileSize={2 * 1024 * 1024}
        invalid
        describedBy="err"
      />,
    );
    expect(screen.getByText("lease.pdf")).toBeInTheDocument();
    expect(screen.getByText(/2\.0 MB/)).toBeInTheDocument();
    expect(zone()).toHaveAttribute("aria-describedby", "err");
    expect(zone().className).toMatch(/border-red/);
  });

  it("passes the dropped file to the caller", () => {
    const onFileSelected = vi.fn();
    render(<FileDropzone accept=".pdf" onFileSelected={onFileSelected} />);
    const file = new File(["x"], "a.pdf", { type: "application/pdf" });
    fireEvent.drop(zone(), { dataTransfer: { files: [file] } });
    expect(onFileSelected).toHaveBeenCalledWith(file);
  });
});

import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

/** Guards the pdf.js code split: pdf.js (~450 kB + a 1.2 MB worker) must only ever be reached
 * through LazyPdfViewer's dynamic import. A static import elsewhere silently pulls it into the
 * main bundle. */
function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return sourceFiles(path);
    return /\.(ts|tsx)$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name) ? [path] : [];
  });
}

function importersOf(pattern: RegExp): string[] {
  return sourceFiles(join(process.cwd(), "src"))
    .filter((file) => pattern.test(readFileSync(file, "utf8")))
    .map((file) => file.replace(/\\/g, "/").split("/src/")[1]);
}

describe("pdf.js chunk split", () => {
  it("pdfjs-dist is imported only from lib/pdfjs.ts", () => {
    expect(importersOf(/from\s+["']pdfjs-dist|import\(\s*["']pdfjs-dist/)).toEqual([
      "lib/pdfjs.ts",
    ]);
  });

  it("PdfViewerWithHighlights is imported only by LazyPdfViewer.tsx", () => {
    expect(
      importersOf(
        /from\s+["'][^"']*\/PdfViewerWithHighlights["']|import\(\s*["'][^"']*\/PdfViewerWithHighlights["']/,
      ),
    ).toEqual(["components/LazyPdfViewer.tsx"]);
  });

  it("lib/pdfjs is imported only by the viewer and PdfPage", () => {
    expect(importersOf(/from\s+["'][^"']*\/lib\/pdfjs["']/).sort()).toEqual([
      "components/PdfPage.tsx",
      "components/PdfViewerWithHighlights.tsx",
    ]);
  });
});

/** Server enforces the real limit; this only avoids an obviously-doomed upload. */
export const MAX_UPLOAD_MB = Number(import.meta.env.VITE_MAX_UPLOAD_MB) || 25;

/** Never trusted for security: the server re-validates the PDF and its size. */
export function validatePdfFile(file: File | null): string | null {
  if (!file) return "Select a PDF file.";
  if (!file.name.toLowerCase().endsWith(".pdf")) return "File must be a .pdf file.";
  if (file.type !== "application/pdf") return "File must be a PDF (application/pdf).";
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
    return `File must be ${MAX_UPLOAD_MB} MB or smaller.`;
  }
  return null;
}

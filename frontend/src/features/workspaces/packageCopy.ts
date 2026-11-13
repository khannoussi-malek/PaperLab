import type { PackageImportResult } from "@/api/client";

const REFUSALS: Record<string, string> = {
  package_unknown_format:
    "This file isn't a PaperLab package, or it comes from a newer PaperLab.",
  package_unsafe: "This file can't be opened safely.",
  package_too_large: "This package is too large to import.",
  package_invalid: "This package is damaged or incomplete.",
};

/** The export dialog's words when a package with its PDFs would be over the import cap. */
export const PACKAGE_TOO_LARGE = "This workspace is too large to export as one package.";
export const PDFS_TOO_LARGE =
  "With its PDFs this package would be over 200 MB, more than PaperLab can import. Export it without PDFs.";

/** A refused import in words; the server's code is never shown. */
export const packageErrorMessage = (code: string): string =>
  REFUSALS[code] ?? "Couldn't import this package. Try again.";

/** The line shown once a package is imported; the chat answers and the skipped PDFs are named only when there are some. */
export function importResultLine(result: PackageImportResult): string {
  const answers = result.answers > 0 ? `, ${result.answers} chat ${result.answers === 1 ? "answer" : "answers"}` : "";
  const line = `Imported "${result.name}": ${result.added} papers added, ${result.matched} already in your library, ${result.notes} notes${answers}.`;
  return result.pdfs_skipped > 0 ? `${line} ${result.pdfs_skipped} PDFs skipped.` : line;
}

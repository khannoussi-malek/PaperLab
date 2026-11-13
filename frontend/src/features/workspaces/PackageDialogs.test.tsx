// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { sileo } from "sileo";
import { ApiError, api, type PackageImportResult, type Workspace } from "@/api/client";
import { workspaceHref } from "@/lib/route";
import { PackageExportDialog, PackageRecordLink, ImportPackageButton } from "./PackageDialogs";
import { WorkspaceSidebar } from "./WorkspaceSidebar";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const workspace = { id: "w1", name: "Sepsis" } as Workspace;

function wrap(ui: React.ReactElement) {
  return render(<QueryClientProvider client={new QueryClient()}>{ui}</QueryClientProvider>);
}

const imported: PackageImportResult = {
  workspace_id: "w2",
  name: "Sepsis (2)",
  added: 3,
  matched: 2,
  notes: 5,
  pdfs_skipped: 0,
  has_record: true,
  answers: 0,
};

test("the export dialog links to the package without PDFs by default", () => {
  wrap(<PackageExportDialog workspace={workspace} onClose={() => {}} />);
  const box = screen.getByRole("checkbox", { name: "Include PDFs" });
  expect(box.getAttribute("aria-checked")).toBe("false");
  expect(screen.getByText("Without PDFs the file is small, and papers arrive as details only.")).toBeTruthy();
  const link = screen.getByRole("link", { name: "Download package" });
  expect(link.getAttribute("href")).toBe("/api/workspaces/w1/package?pdfs=false&answers=true");
  expect(link.hasAttribute("download")).toBe(true);
});

test("chat answers are included by default, with the fixed help text", () => {
  wrap(<PackageExportDialog workspace={workspace} onClose={() => {}} />);
  const box = screen.getByRole("checkbox", { name: "Include chat answers" });
  expect(box.getAttribute("aria-checked")).toBe("true");
  expect(
    screen.getByText("Answers keep their cited passages, so their citations still open after import."),
  ).toBeTruthy();
});

test("unticking Include chat answers takes answers=false into the download", () => {
  wrap(<PackageExportDialog workspace={workspace} onClose={() => {}} />);
  fireEvent.click(screen.getByRole("checkbox", { name: "Include chat answers" }));
  expect(screen.getByRole("link", { name: "Download package" }).getAttribute("href")).toBe(
    "/api/workspaces/w1/package?pdfs=false&answers=false",
  );
});

test("ticking Include PDFs changes the download to the one with PDFs", () => {
  wrap(<PackageExportDialog workspace={workspace} onClose={() => {}} />);
  fireEvent.click(screen.getByRole("checkbox", { name: "Include PDFs" }));
  expect(screen.getByRole("link", { name: "Download package" }).getAttribute("href")).toBe(
    "/api/workspaces/w1/package?pdfs=true&answers=true",
  );
});

test("the PDFs size check carries the answers choice, and follows it", async () => {
  const check = vi.spyOn(api, "checkPackage").mockResolvedValue(undefined);
  wrap(<PackageExportDialog workspace={workspace} onClose={() => {}} />);
  fireEvent.click(screen.getByRole("checkbox", { name: "Include PDFs" }));
  await waitFor(() => expect(check).toHaveBeenCalledWith("w1", true, true));
  fireEvent.click(screen.getByRole("checkbox", { name: "Include chat answers" }));
  await waitFor(() => expect(check).toHaveBeenCalledWith("w1", true, false));
});

test("picking a file posts it, shows the result line, then opens the new workspace", async () => {
  const importPackage = vi.spyOn(api, "importPackage").mockResolvedValue(imported);
  const toast = vi.spyOn(sileo, "success").mockReturnValue("" as never);
  wrap(<ImportPackageButton />);
  const file = new File(["zip"], "sepsis.paperlab", { type: "application/zip" });
  fireEvent.change(screen.getByLabelText("Package file"), { target: { files: [file] } });
  await waitFor(() => expect(toast).toHaveBeenCalled());
  expect(importPackage).toHaveBeenCalledWith(file);
  expect(toast).toHaveBeenCalledWith({
    title: 'Imported "Sepsis (2)": 3 papers added, 2 already in your library, 5 notes.',
  });
  expect(window.location.hash).toBe(workspaceHref("w2"));
});

test("a refused package shows its code in words and opens nothing", async () => {
  vi.spyOn(api, "importPackage").mockRejectedValue(
    new ApiError("package_unsafe", 422, { detail: "package_unsafe" }),
  );
  const toast = vi.spyOn(sileo, "error").mockReturnValue("" as never);
  window.location.hash = "#/";
  wrap(<ImportPackageButton />);
  fireEvent.change(screen.getByLabelText("Package file"), {
    target: { files: [new File(["x"], "bad.paperlab")] },
  });
  await waitFor(() => expect(toast).toHaveBeenCalledWith({ title: "This file can't be opened safely." }));
  expect(window.location.hash).toBe("#/");
});

test("an upload over the body cap says the package is too large", async () => {
  vi.spyOn(api, "importPackage").mockRejectedValue(new ApiError("Upload too big", 413, { detail: "Upload too big" }));
  const toast = vi.spyOn(sileo, "error").mockReturnValue("" as never);
  wrap(<ImportPackageButton />);
  fireEvent.change(screen.getByLabelText("Package file"), {
    target: { files: [new File(["x"], "big.paperlab")] },
  });
  await waitFor(() => expect(toast).toHaveBeenCalledWith({ title: "This package is too large to import." }));
});

test("a package that is too large with its PDFs says so and offers no download", async () => {
  vi.spyOn(api, "checkPackage").mockRejectedValue(
    new ApiError("package_too_large_with_pdfs", 409, { detail: "package_too_large_with_pdfs" }),
  );
  wrap(<PackageExportDialog workspace={workspace} onClose={() => {}} />);
  fireEvent.click(screen.getByRole("checkbox", { name: "Include PDFs" }));
  expect(
    await screen.findByText(
      "With its PDFs this package would be over 200 MB, more than PaperLab can import. Export it without PDFs.",
    ),
  ).toBeTruthy();
  expect(screen.queryByRole("link", { name: "Download package" })).toBeNull();
});

test("a package that fits with its PDFs keeps its download", async () => {
  const check = vi.spyOn(api, "checkPackage").mockResolvedValue(undefined);
  wrap(<PackageExportDialog workspace={workspace} onClose={() => {}} />);
  fireEvent.click(screen.getByRole("checkbox", { name: "Include PDFs" }));
  await waitFor(() => expect(check).toHaveBeenCalledWith("w1", true, true));
  expect(screen.getByRole("link", { name: "Download package" }).getAttribute("href")).toBe(
    "/api/workspaces/w1/package?pdfs=true&answers=true",
  );
});

test("the screening record link appears only when the workspace has one", async () => {
  const has = vi.spyOn(api, "hasPackageRecord").mockResolvedValue(true);
  wrap(<PackageRecordLink workspaceId="w2" />);
  const link = await screen.findByRole("link", { name: "Screening record from the package" });
  expect(link.getAttribute("href")).toBe("/api/workspaces/w2/package-record");
  expect(has).toHaveBeenCalledWith("w2");
});

test("no record, no link", async () => {
  vi.spyOn(api, "hasPackageRecord").mockResolvedValue(false);
  wrap(<PackageRecordLink workspaceId="w1" />);
  await waitFor(() => expect(api.hasPackageRecord).toHaveBeenCalled());
  expect(screen.queryByRole("link", { name: "Screening record from the package" })).toBeNull();
});

test("the workspace row menu opens the export dialog", async () => {
  vi.spyOn(api, "listWorkspaces").mockResolvedValue([workspace]);
  wrap(<WorkspaceSidebar activeId={null} />);
  const trigger = await screen.findByRole("button", { name: "Workspace actions" });
  fireEvent.pointerDown(trigger);
  fireEvent.click(await screen.findByRole("menuitem", { name: "Export package…" }));
  expect(await screen.findByRole("dialog", { name: "Export package" })).toBeTruthy();
});

test("a workspace too large even without PDFs says so plainly and offers no download", async () => {
  vi.spyOn(api, "checkPackage").mockRejectedValue(new ApiError("package_too_large", 409, { detail: "package_too_large" }));
  wrap(<PackageExportDialog workspace={workspace} onClose={() => {}} />);
  expect(await screen.findByText("This workspace is too large to export as one package.")).toBeTruthy();
  expect(screen.queryByRole("link", { name: "Download package" })).toBeNull();
});

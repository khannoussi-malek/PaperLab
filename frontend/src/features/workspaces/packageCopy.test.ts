import { expect, test } from "vitest";
import { importResultLine, packageErrorMessage } from "./packageCopy";

const result = {
  workspace_id: "w2",
  name: "Sepsis review",
  added: 3,
  matched: 2,
  notes: 5,
  pdfs_skipped: 0,
  has_record: true,
  answers: 0,
};

test("the import result line uses the fixed wording", () => {
  expect(importResultLine(result)).toBe(
    'Imported "Sepsis review": 3 papers added, 2 already in your library, 5 notes.',
  );
});

test("the result line adds the skipped PDFs only when there are some", () => {
  expect(importResultLine({ ...result, pdfs_skipped: 2 })).toBe(
    'Imported "Sepsis review": 3 papers added, 2 already in your library, 5 notes. 2 PDFs skipped.',
  );
});

test("the result line names the chat answers when there are some", () => {
  expect(importResultLine({ ...result, answers: 4 })).toBe(
    'Imported "Sepsis review": 3 papers added, 2 already in your library, 5 notes, 4 chat answers.',
  );
});

test("the chat answers come before the skipped PDFs in the result line", () => {
  expect(importResultLine({ ...result, answers: 4, pdfs_skipped: 2 })).toBe(
    'Imported "Sepsis review": 3 papers added, 2 already in your library, 5 notes, 4 chat answers. 2 PDFs skipped.',
  );
});

test("each refusal code is shown in plain words", () => {
  expect(packageErrorMessage("package_unknown_format")).toBe(
    "This file isn't a PaperLab package, or it comes from a newer PaperLab.",
  );
  expect(packageErrorMessage("package_unsafe")).toBe(
    "This file can't be opened safely.",
  );
  expect(packageErrorMessage("package_too_large")).toBe(
    "This package is too large to import.",
  );
  expect(packageErrorMessage("package_invalid")).toBe(
    "This package is damaged or incomplete.",
  );
});

test("an unknown failure gets the generic line, never the raw code", () => {
  expect(packageErrorMessage("boom_internal")).toBe(
    "Couldn't import this package. Try again.",
  );
});

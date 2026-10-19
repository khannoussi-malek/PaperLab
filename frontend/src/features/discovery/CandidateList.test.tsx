// @vitest-environment jsdom
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, it, vi } from "vitest";
import type { Candidate } from "@/api/client";
import { AlreadyInLibraryError, NoFreePdfError, api } from "@/api/client";
import { CandidateList } from "./CandidateList";

const found = {
  title: "REAL Sampling",
  authors: [],
  sources: [],
  external_ids: {},
  pdf_urls: ["https://x/a.pdf"],
  paper_id: null,
  cited_by_count: null,
} as unknown as Candidate;

beforeEach(() => vi.restoreAllMocks());

it("turns a duplicate refusal into a link to the paper that holds it", async () => {
  vi.spyOn(api, "addCandidate").mockRejectedValue(
    new AlreadyInLibraryError("already_in_library", "p7"),
  );
  render(
    <QueryClientProvider client={new QueryClient()}>
      <CandidateList candidates={[found]} empty="No papers found." />
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Add REAL Sampling" }));
  expect(
    await screen.findByRole("link", { name: "Already in your library" }),
  ).toHaveAttribute("href", "#/papers/p7");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

const noPdf = { ...found, pdf_urls: [] } as unknown as Candidate;
const paper = { id: "p9" } as never;
const show = (candidate: Candidate, workspaceId?: string) => {
  const client = new QueryClient();
  const invalidate = vi.spyOn(client, "invalidateQueries");
  render(
    <QueryClientProvider client={client}>
      <CandidateList candidates={[candidate]} empty="none" workspaceId={workspaceId} />
    </QueryClientProvider>,
  );
  return invalidate;
};

it("offers Save without PDF on a candidate with no free PDF, and sends the flag", async () => {
  const add = vi.spyOn(api, "addCandidate").mockResolvedValue(paper);
  const invalidate = show(noPdf, "w1");
  expect(screen.queryByRole("button", { name: "Add REAL Sampling" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Save without PDF: REAL Sampling" }));
  expect(await screen.findByRole("link", { name: "In library" })).toBeInTheDocument();
  expect(add).toHaveBeenCalledWith(noPdf, "w1", true);
  const keys = invalidate.mock.calls.map(([filter]) => (filter as { queryKey: unknown }).queryKey);
  expect(keys).toContainEqual(["papers"]);
  expect(keys).toContainEqual(["workspaces"]);
});

it("keeps Add the primary action when a free PDF is listed, and sends no flag", async () => {
  const add = vi.spyOn(api, "addCandidate").mockResolvedValue(paper);
  show(found);
  expect(screen.queryByRole("button", { name: /Save without PDF/ })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Add REAL Sampling" }));
  await screen.findByRole("link", { name: "In library" });
  expect(add).toHaveBeenCalledWith(found, undefined, undefined);
});

it("says a no_free_pdf refusal in words and offers Save without PDF as the retry", async () => {
  const add = vi
    .spyOn(api, "addCandidate")
    .mockRejectedValueOnce(new NoFreePdfError("No free PDF was found for this paper. Open its page, download the PDF and use Upload PDFs."))
    .mockResolvedValueOnce(paper);
  show(found);
  fireEvent.click(screen.getByRole("button", { name: "Add REAL Sampling" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("No free PDF was found for this paper.");
  fireEvent.click(screen.getByRole("button", { name: "Save without PDF: REAL Sampling" }));
  expect(await screen.findByRole("link", { name: "In library" })).toBeInTheDocument();
  expect(add).toHaveBeenLastCalledWith(found, undefined, true);
});

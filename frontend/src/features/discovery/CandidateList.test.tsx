// @vitest-environment jsdom
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, it, vi } from "vitest";
import type { Candidate } from "@/api/client";
import { AlreadyInLibraryError, api } from "@/api/client";
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

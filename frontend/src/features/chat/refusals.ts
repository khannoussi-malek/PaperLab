/** Why an answer failed, in words, and what the user can do about it. */
export type ChatProblem = { message: string; retryable: boolean; reindex: boolean }

// The 409s a chat POST answers before streaming, for a paper or a workspace, in words.
const REFUSALS: Record<string, ChatProblem> = {
  paper_not_ready: {
    message: 'This paper is still being processed. Ask again once it is ready.',
    retryable: true,
    reindex: false,
  },
  paper_not_indexed: {
    message: 'This paper was added before chat existed, so it has no search index yet.',
    retryable: false,
    reindex: true,
  },
  workspace_empty: { message: 'Add papers to chat with this workspace.', retryable: false, reindex: false },
  workspace_not_indexed: {
    message: "None of this workspace's papers can be searched yet. Ask again once they finish processing.",
    retryable: true,
    reindex: false,
  },
}

/** A refused question (a non-2xx response before streaming): known codes in words; a server error can be retried. */
export function refusal(status: number, detail: string): ChatProblem {
  return REFUSALS[detail] ?? { message: detail, retryable: status >= 500, reindex: false }
}

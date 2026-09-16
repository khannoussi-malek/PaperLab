/** Why an answer failed, in words, and what the user can do about it. `settings`: the fix is on the settings page. */
export type ChatProblem = { message: string; retryable: boolean; reindex: boolean; settings?: boolean }

// The 404s and 409s a chat POST answers before streaming, for a paper or a workspace, in words.
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
  // Retry asks again with the dropdown's new pick: the default, once the models list has refetched.
  model_not_found: {
    message: 'The model you picked was removed. Ask again to use the default model.',
    retryable: true,
    reindex: false,
  },
  no_model: { message: 'No model is set up for chat yet.', retryable: false, reindex: false, settings: true },
  embedding_model_changed: {
    message: 'Your library was indexed with a different embedding model. Re-index it to chat again.',
    retryable: false,
    reindex: false,
    settings: true,
  },
}

/** A refused question (a non-2xx response before streaming): known codes in words; a server error can be retried. */
export function refusal(status: number, detail: string): ChatProblem {
  return REFUSALS[detail] ?? { message: detail, retryable: status >= 500, reindex: false }
}

/**
 * Why an answer failed, in words, and what the user can do about it. `settings`: the fix is on the settings page.
 * `endsThread`: the answer a follow-up continued is gone, so the panel stops following it. `download`: the fix is the
 * search model's Download button, shown in place.
 */
export type ChatProblem = {
  message: string
  retryable: boolean
  reindex: boolean
  settings?: boolean
  endsThread?: boolean
  download?: boolean
}

const FOLLOWED_ANSWER_GONE: ChatProblem = {
  message: 'The answer you were following is gone. Ask again to start a new question.',
  retryable: false,
  reindex: false,
  endsThread: true,
}

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
  // No search model yet (D136): a long paper or a workspace needs search; a short paper is sent whole and never gets here.
  search_not_set_up: {
    message: "Search isn't set up, so this can't be searched yet.",
    retryable: false,
    reindex: false,
    download: true,
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
  parent_not_found: FOLLOWED_ANSWER_GONE,
  parent_scope: FOLLOWED_ANSWER_GONE,
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

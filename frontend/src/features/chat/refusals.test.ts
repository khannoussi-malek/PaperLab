import { describe, expect, it } from 'vitest'
import { refusal } from './refusals'

describe('refusal', () => {
  it('words a follow-up whose answer is gone, ends its thread, and offers no Retry', () => {
    const gone = {
      message: 'The answer you were following is gone. Ask again to start a new question.',
      retryable: false,
      reindex: false,
      endsThread: true,
    }
    expect(refusal(404, 'parent_not_found')).toEqual(gone)
    expect(refusal(409, 'parent_scope')).toEqual(gone)
  })

  it("words a paper that isn't ready as retryable, and one without an index as needing a re-index", () => {
    expect(refusal(409, 'paper_not_ready')).toEqual({
      message: 'This paper is still being processed. Ask again once it is ready.',
      retryable: true,
      reindex: false,
    })
    expect(refusal(409, 'paper_not_indexed')).toMatchObject({ retryable: false, reindex: true })
  })

  it("words an empty workspace, and one whose papers can't be searched yet", () => {
    expect(refusal(409, 'workspace_empty')).toEqual({
      message: 'Add papers to chat with this workspace.',
      retryable: false,
      reindex: false,
    })
    expect(refusal(409, 'workspace_not_indexed')).toEqual({
      message: "None of this workspace's papers can be searched yet. Ask again once they finish processing.",
      retryable: true,
      reindex: false,
    })
  })

  it('offers Retry after a server error, with its detail', () => {
    expect(refusal(500, 'Internal Server Error')).toEqual({
      message: 'Internal Server Error',
      retryable: true,
      reindex: false,
    })
    expect(refusal(503, 'Service Unavailable')).toMatchObject({ retryable: true })
  })

  it('shows any other refusal as sent, without Retry', () => {
    expect(refusal(404, 'workspace 1 not found')).toEqual({
      message: 'workspace 1 not found',
      retryable: false,
      reindex: false,
    })
    // errorDetail has already turned a validation list into this line.
    expect(refusal(422, 'Check these fields: question.')).toMatchObject({ retryable: false })
  })

  it('words a removed model as retryable, and a missing model or a changed embedding model as fixed in Settings', () => {
    expect(refusal(404, 'model_not_found')).toEqual({
      message: 'The model you picked was removed. Ask again to use the default model.',
      retryable: true,
      reindex: false,
    })
    expect(refusal(409, 'no_model')).toEqual({
      message: 'No model is set up for chat yet.',
      retryable: false,
      reindex: false,
      settings: true,
    })
    expect(refusal(409, 'embedding_model_changed')).toMatchObject({ retryable: false, settings: true })
  })

  it("words a search that isn't set up, and offers the search model's download instead of Retry", () => {
    expect(refusal(409, 'search_not_set_up')).toEqual({
      message: "Search isn't set up, so this can't be searched yet.",
      retryable: false,
      reindex: false,
      download: true,
    })
  })

  it('words a search being rebuilt, whose panel shows the rebuild and offers Retry once it ends', () => {
    expect(refusal(409, 'search_rebuilding')).toEqual({
      message: 'Search is being rebuilt.',
      retryable: true,
      reindex: false,
      rebuild: true,
    })
  })
})

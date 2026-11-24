import { ApiError, request, sendJson } from '../http'
import type { AnswerCheck, AnswerProvenance, ChatAnswer, ChatScope, Note } from '@/entities'

const chatUrl = (scope: ChatScope) =>
  scope.kind === 'hit'
    ? `/api/workspaces/${scope.workspaceId}/search/hits/${scope.id}/chat`
    : `/api/${scope.kind === 'paper' ? 'papers' : 'workspaces'}/${scope.id}/chat`

export const chatApi = {
  listChat: (scope: ChatScope) => request<ChatAnswer[]>(chatUrl(scope)),
  /** How a saved answer was made: its model, connection, prompt, skill and passages. */
  answerProvenance: (outputId: string) => request<AnswerProvenance>(`/api/llm-outputs/${outputId}/provenance`),
  /** The answer's newest check (M34), or null before any. */
  answerCheck: async (outputId: string): Promise<AnswerCheck | null> => {
    try {
      return await request<AnswerCheck>(`/api/chat/answers/${outputId}/check`)
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) return null
      throw e
    }
  },
  startAnswerCheck: (outputId: string, confirmRemote = false) =>
    request<AnswerCheck>(`/api/chat/answers/${outputId}/check`, sendJson('POST', { confirm_remote: confirmRemote })),
  /** Saves block `index` of a saved answer's suggested notes. A second save is refused with `already_saved`. */
  saveSuggestion: (outputId: string, index: number) =>
    request<Note>(`/api/chat/answers/${outputId}/notes`, sendJson('POST', { index })),
  /** A chart of the scope's captured data, saved as a chat answer (M14); rejects with the reason nothing was drawn. */
  askChartAnswer: (scope: ChatScope, question: string, modelId: string | null) =>
    request<{ output_id: string }>(`${chatUrl(scope)}/chart`, sendJson('POST', { question, model_id: modelId })),
  /**
   * The raw response: on success its body is the SSE stream that `useChatStream` reads. `modelId` null: the default.
   * `parentId`: the saved answer this question follows up (paper chat only); null for a question on its own.
   * `skillId`: the skill the question runs with (null: No skill). A search hit's chat has no skills, so it sends none.
   * `eachPaper` (workspace chat, M8.5): read each paper on its own first, then answer from what each says.
   */
  askChat: (
    scope: ChatScope,
    question: string,
    modelId: string | null,
    parentId: string | null,
    skillId: string | null,
    signal?: AbortSignal,
    eachPaper = false,
  ) =>
    fetch(chatUrl(scope), {
      ...sendJson('POST', {
        question,
        model_id: modelId,
        parent_id: parentId,
        ...(scope.kind === 'hit' ? {} : { skill_id: skillId }),
        ...(eachPaper ? { each_paper: true } : {}),
      }),
      signal,
    }),
}

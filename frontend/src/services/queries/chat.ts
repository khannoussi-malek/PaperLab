import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ALREADY_SAVED } from '@/features/chat/noteBlocks'
import { api } from '@/services/api'
import type { ChatScope } from '@/entities'
import { keys } from './core'
import { refreshNotes } from './notes'

/** Saved questions and answers for a paper or a workspace, oldest first. */
export const useChatHistory = (scope: ChatScope) =>
  useQuery({ queryKey: keys.chat(scope), queryFn: () => api.listChat(scope) })

/** Asks for a chart answer (M14); the saved answer then comes back in the history. */
export function useAskChart(scope: ChatScope) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ question, modelId }: { question: string; modelId: string | null }) =>
      api.askChartAnswer(scope, question, modelId),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.chat(scope) }),
  })
}

/** For the chat stream, which isn't a query: refetch the history once an answer is saved. */
export function useInvalidateChatHistory(scope: ChatScope) {
  const client = useQueryClient()
  return () => client.invalidateQueries({ queryKey: keys.chat(scope) })
}

/** Saves a suggested note from a saved answer. Resolves once the answer's history knows it (its card then reads Saved)
 * and the notes lists have refetched. On `already_saved` the history is refetched too: it names the note. */
export function useSaveSuggestion() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ outputId, index }: { scope: ChatScope; outputId: string; index: number }) =>
      api.saveSuggestion(outputId, index),
    onSuccess: (_note, { scope }) =>
      Promise.all([client.invalidateQueries({ queryKey: keys.chat(scope) }), refreshNotes(client)]),
    onError: (error, { scope }) =>
      error.message === ALREADY_SAVED ? client.invalidateQueries({ queryKey: keys.chat(scope) }) : undefined,
  })
}

/** How a saved answer was made; read only when its disclosure opens, so chat history stays as fast. */
const answerCheckKey = (outputId: string) => ['llm-outputs', outputId, 'check'] as const
const CHECK_POLL_MS = 2000

/** An answer's newest check (M34), polled while it runs; read only for an answer the history says has one. */
export const useAnswerCheck = (outputId: string, enabled: boolean) =>
  useQuery({
    queryKey: answerCheckKey(outputId),
    queryFn: () => api.answerCheck(outputId),
    enabled,
    refetchInterval: (query) => (query.state.data?.state === 'running' ? CHECK_POLL_MS : false),
  })

export function useStartAnswerCheck(outputId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (confirmRemote: boolean) => api.startAnswerCheck(outputId, confirmRemote),
    onSuccess: (check) => client.setQueryData(answerCheckKey(outputId), check),
  })
}

export const useAnswerProvenance = (outputId: string, enabled: boolean) =>
  useQuery({ queryKey: ['llm-outputs', outputId, 'provenance'] as const, queryFn: () => api.answerProvenance(outputId), enabled })

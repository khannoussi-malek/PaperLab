import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/services/api'
import type { EvidenceCard, EvidenceChange } from '@/entities'
import { keys } from './core'

const POLL_MS = 2000
const isGenerating = (card: EvidenceCard | null | undefined) => card?.status === 'generating'

/** The workspace's evidence table; polls while any card is still being made. */
export const useEvidenceCards = (workspaceId: string) =>
  useQuery({
    queryKey: keys.evidenceCards(workspaceId),
    queryFn: () => api.listEvidenceCards(workspaceId),
    refetchInterval: (query) => (query.state.data?.some((row) => isGenerating(row.card)) ? POLL_MS : false),
  })

/** One paper's card, or null when it has none yet; polls while it is being made. */
export const useEvidenceCard = (paperId: string) =>
  useQuery({
    queryKey: keys.evidenceCard(paperId),
    queryFn: () => api.getEvidenceCard(paperId).catch((e: Error) => (/no evidence card/i.test(e.message) ? null : Promise.reject(e))),
    refetchInterval: (query) => (isGenerating(query.state.data) ? POLL_MS : false),
  })

function useRefreshEvidence<V, R>(mutationFn: (variables: V) => Promise<R>, scope: { paperId?: string; workspaceId?: string }) {
  const client = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: () =>
      Promise.all([
        scope.paperId && client.invalidateQueries({ queryKey: keys.evidenceCard(scope.paperId) }),
        scope.workspaceId && client.invalidateQueries({ queryKey: keys.evidenceCards(scope.workspaceId) }),
      ]),
  })
}

export const useGenerateEvidenceCards = (workspaceId: string) =>
  useRefreshEvidence(() => api.generateEvidenceCards(workspaceId), { workspaceId })

export function useGenerateEvidenceCard(workspaceId?: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (v: { paperId: string; regenerate: boolean; confirm: boolean }) =>
      api.generateEvidenceCard(v.paperId, v.regenerate, v.confirm),
    onSuccess: (_cards, v) =>
      Promise.all([
        client.invalidateQueries({ queryKey: keys.evidenceCard(v.paperId) }),
        workspaceId && client.invalidateQueries({ queryKey: keys.evidenceCards(workspaceId) }),
      ]),
  })
}

export const useEditEvidenceCard = (paperId: string, workspaceId?: string) =>
  useRefreshEvidence((changes: EvidenceChange[]) => api.editEvidenceCard(paperId, changes), { paperId, workspaceId })

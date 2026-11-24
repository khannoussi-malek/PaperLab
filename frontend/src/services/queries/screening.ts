import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { ScreeningState, ScreeningUpdate } from '@/entities'
import { api } from '@/services/api'
import { keys } from './core'

/** The workspace's screening criteria and suggestion-job state (M31b). Polls only while a suggestion job is
 * running or stopping; the hit pool itself refreshes separately once the job goes back to idle. */
export const useScreeningState = (workspaceId: string) =>
  useQuery({
    queryKey: keys.screening(workspaceId),
    queryFn: () => api.screeningState(workspaceId),
    refetchInterval: (query) => (query.state.data?.suggest_status === 'idle' ? false : 2000),
  })

function useScreeningMutation<T>(workspaceId: string, fn: (arg: T) => Promise<ScreeningState>) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: (state) => {
      client.setQueryData(keys.screening(workspaceId), state)
      client.invalidateQueries({ queryKey: keys.searchHitsRoot(workspaceId) })
      client.invalidateQueries({ queryKey: keys.rankedHits(workspaceId) })
    },
  })
}

export const useSaveScreening = (workspaceId: string) =>
  useScreeningMutation(workspaceId, (body: ScreeningUpdate) => api.saveScreening(workspaceId, body))
export const useStartSuggestions = (workspaceId: string) =>
  useScreeningMutation(workspaceId, (confirmRemote: boolean) => api.startSuggestions(workspaceId, confirmRemote))
export const useStopSuggestions = (workspaceId: string) =>
  useScreeningMutation(workspaceId, () => api.stopSuggestions(workspaceId))

/** The PRISMA flow-diagram counts (`runs`: a single run id, or `'all'` to combine every run in the workspace). */
export function usePrismaExport(workspaceId: string, runs: string) {
  return useQuery({
    queryKey: keys.prisma(workspaceId, runs),
    queryFn: () => api.prismaExport(workspaceId, runs),
  })
}

export const useReadingContext = (paperId: string) =>
  useQuery({ queryKey: keys.readingContext(paperId), queryFn: () => api.readingContext(paperId) })

/** Shared by `useReadingQueue` and ReadingQueueTab's per-run "has included papers" probes, so both hit one cache entry. */
export const readingQueueOptions = (workspaceId: string, runId: string) => ({
  queryKey: keys.readingQueue(workspaceId, runId),
  queryFn: () => api.readingQueue(workspaceId, runId),
})

export const useReadingQueue = (workspaceId: string, runId: string | null, enabled = true) =>
  useQuery({
    ...readingQueueOptions(workspaceId, runId ?? 'none'),
    enabled: enabled && runId != null,
  })

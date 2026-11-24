import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { SavedSearch, SavedSearchCreate, SavedSearchUpdate } from '@/entities'
import { api } from '@/services/api'
import { keys, PAPERS_POLL_MS } from './core'

/** Polls only while one of its runs is going, so "N new" moves when a scheduled run finds something. */
export const useSavedSearches = (workspaceId: string) =>
  useQuery({
    queryKey: keys.savedSearches(workspaceId),
    queryFn: () => api.listSavedSearches(workspaceId),
    refetchInterval: (query) =>
      query.state.data?.some((s: SavedSearch) => s.last_run_status === 'running') ? PAPERS_POLL_MS : false,
  })

function useSavedSearchMutation<V, R>(workspaceId: string, mutationFn: (variables: V) => Promise<R>, alsoRuns = false) {
  const client = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: keys.savedSearches(workspaceId) }),
        ...(alsoRuns ? [client.invalidateQueries({ queryKey: keys.searchRuns(workspaceId) })] : []),
      ]),
  })
}

export const useCreateSavedSearch = (workspaceId: string) =>
  useSavedSearchMutation(workspaceId, (body: SavedSearchCreate) => api.createSavedSearch(workspaceId, body))
export const useUpdateSavedSearch = (workspaceId: string) =>
  useSavedSearchMutation(workspaceId, (v: { id: string; body: SavedSearchUpdate }) =>
    api.updateSavedSearch(workspaceId, v.id, v.body))
export const useDeleteSavedSearch = (workspaceId: string) =>
  useSavedSearchMutation(workspaceId, (id: string) => api.deleteSavedSearch(workspaceId, id))
/** Resolves with the new run, so the caller can switch the Search tab to it. */
export const useRunSavedSearchNow = (workspaceId: string) =>
  useSavedSearchMutation(workspaceId, (id: string) => api.runSavedSearchNow(workspaceId, id), true)

/** The reader opened a saved search's new finds: its "N new" count starts again from now. */
export const useMarkSavedSearchSeen = (workspaceId: string) =>
  useSavedSearchMutation(workspaceId, (id: string) => api.markSavedSearchSeen(workspaceId, id))

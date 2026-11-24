import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/services/api'
import type { ReferencePage, References, ReferencesDirection } from '@/entities'
import { keys, PAPERS_POLL_MS } from './core'

/** Poll the References page only while an unfetched paper is still fetching. */
export function referencePagePollInterval(page: ReferencePage | undefined): number | false {
  return page?.coverage.unfetched.some((paper) => paper.state === 'fetching') ? PAPERS_POLL_MS : false
}

/** One direction of a paper's references, fetched only once `enabled` (the References tab is open). Polls while the
 * fetch is still running, like the library polls ingest. */
export const useReferences = (paperId: string, direction: ReferencesDirection, enabled: boolean) =>
  useQuery({
    queryKey: keys.referencesDirection(paperId, direction),
    queryFn: () => api.references(paperId, direction),
    enabled,
    refetchInterval: (query) => (query.state.data?.state === 'fetching' ? PAPERS_POLL_MS : false),
  })

/** Queues a fetch of both directions. A second call while already fetching is harmless on the server too. */
export function useRefreshReferences(paperId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api.refreshReferences(paperId),
    onSuccess: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: keys.references(paperId) }),
        client.invalidateQueries({ queryKey: ['reference-page'] }),
      ]),
  })
}

/** Imports one reference. Each row owns its own mutation, so only that row shows "Importing…". Matches the row in
 * every cached listing, in either paper's tab and the References page, since the caller no longer names one paper. */
export function useImportReference() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ refId, workspaceId }: { refId: string; workspaceId?: string }) =>
      api.importReference(refId, workspaceId),
    onSuccess: (paper, { refId }) => {
      const marked = (data: References | undefined) =>
        data
          ? { ...data, rows: data.rows.map((row) => (row.id === refId ? { ...row, paper_id: paper.id } : row)) }
          : data
      client.setQueriesData<References>({ queryKey: ['references'] }, marked)
      return Promise.all([
        client.invalidateQueries({ queryKey: keys.papers, exact: true }),
        client.invalidateQueries({ queryKey: keys.workspaces }),
        client.invalidateQueries({ queryKey: ['reference-page'] }),
      ])
    },
  })
}

/** Marks or unmarks a reference To read (D164). While it runs, the row shows the state requested and is disabled.
 * `onUnqueued` fires only once both invalidations below have refetched (spec note 11): a row that just left the
 * References page's To read section can no longer run its own onSuccess after it unmounts. */
export function useQueueReference(onUnqueued?: () => void) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ refId, queue }: { refId: string; queue: boolean }) =>
      queue ? api.queueReference(refId) : api.unqueueReference(refId),
    onSuccess: async (_result, { queue }) => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ['references'] }),
        client.invalidateQueries({ queryKey: ['reference-page'] }),
      ])
      if (!queue) onUnqueued?.()
    },
  })
}

/** The whole library's, or one workspace's, References page (D166): polls while an unfetched paper is fetching.
 * `enabled` false (the caller hasn't yet confirmed a workspace id exists) holds the request rather than asking for
 * an unknown workspace's listing (spec §3.10: "the listing isn't asked for"). */
export const useReferencePage = (workspaceId: string | null, enabled = true) =>
  useQuery({
    queryKey: ['reference-page', workspaceId ?? 'library'],
    queryFn: () => api.referencePage(workspaceId),
    enabled,
    refetchInterval: (query) => referencePagePollInterval(query.state.data),
    placeholderData: keepPreviousData,
  })

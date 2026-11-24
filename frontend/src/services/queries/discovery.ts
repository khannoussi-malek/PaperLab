import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { sameCandidate } from '@/features/discovery/candidateMeta'
import { api } from '@/services/api'
import type { Candidate, SearchResult } from '@/entities'
import { keys } from './core'

/** Checks an idea against the library. Read-only, so nothing to invalidate. */
export function useNovelty() {
  return useMutation({ mutationFn: (text: string) => api.novelty(text) })
}

// A search asks every source that is on, and OpenAlex costs money past a small daily allowance; suggestions change
// slowly.
const SEARCH_STALE_MS = 10 * 60_000
const SIMILAR_STALE_MS = 60 * 60_000

/** Searches once per submitted query; `query` is null until the first submit. No refetch on focus/reconnect: a
 * search costs OpenAlex credits and isn't worth spending again just because the tab regained focus. */
export const useSearchPapers = (query: string | null) =>
  useQuery({
    queryKey: keys.search(query ?? ''),
    queryFn: () => api.searchPapers(query!),
    enabled: query !== null,
    staleTime: SEARCH_STALE_MS,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })

/** Semantic Scholar's suggestions for a paper, fetched only once `enabled` (the Similar tab is open). No refetch on
 * focus/reconnect: same reasoning as useSearchPapers. */
export const useSimilarPapers = (paperId: string, enabled: boolean) =>
  useQuery({
    queryKey: keys.similar(paperId),
    queryFn: () => api.similarPapers(paperId),
    enabled,
    staleTime: SIMILAR_STALE_MS,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })

/** Adds one found paper. Each row owns one, so its "In library" state stays with it. */
export function useAddCandidate(workspaceId?: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ candidate, saveWithoutPdf }: { candidate: Candidate; saveWithoutPdf?: boolean }) =>
      api.addCandidate(candidate, workspaceId, saveWithoutPdf),
    onSuccess: (paper, { candidate }) => {
      // So a row still shows "In library" after the dialog (or the Similar tab) is closed and reopened, even though
      // that only rereads the cache: the rows themselves unmount, and the cached candidate otherwise still lacks
      // paper_id until the next real search. New arrays and objects throughout: never mutate cached query data.
      const marked = (candidates: Candidate[]) =>
        candidates.map((existing) =>
          sameCandidate(existing, candidate) ? { ...existing, paper_id: paper.id } : existing,
        )
      // Two shapes under discovery: a search holds { results, notices }, suggestions are a plain list.
      client.setQueriesData<SearchResult>({ queryKey: keys.searches }, (found) =>
        found ? { ...found, results: marked(found.results) } : found,
      )
      client.setQueriesData<Candidate[]>({ queryKey: keys.suggestions }, (found) => (found ? marked(found) : found))
      return Promise.all([
        client.invalidateQueries({ queryKey: keys.papers, exact: true }),
        client.invalidateQueries({ queryKey: keys.workspaces }),
        // Stale, not refetched: an open search keeps its rows, and the next one asks again with the paper added.
        client.invalidateQueries({ queryKey: keys.discovery, refetchType: 'none' }),
      ])
    },
  })
}

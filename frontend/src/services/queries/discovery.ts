import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlreadyInLibraryError, api } from '@/services/api'
import { sameCandidate, type Candidate, type SearchResult } from '@/entities'
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

export type PublishedOutcome = { kind: 'added' } | { kind: 'owned'; paperId: string } | { kind: 'no-pdf' } | { kind: 'not-found' }

/** Looks the published DOI up the way Find papers does, and adds it only when a free PDF is listed. */
async function addPublished(doi: string): Promise<PublishedOutcome> {
  const { results } = await api.searchPapers(doi)
  const found = results.find((c) => c.doi?.toLowerCase() === doi.toLowerCase())
  if (!found) return { kind: 'not-found' }
  if (found.paper_id) return { kind: 'owned', paperId: found.paper_id }
  if (found.pdf_urls.length === 0) return { kind: 'no-pdf' }
  try {
    await api.addCandidate(found)
  } catch (error) {
    if (error instanceof AlreadyInLibraryError) return { kind: 'owned', paperId: error.paperId }
    throw error
  }
  return { kind: 'added' }
}

/** Adds a preprint's published version; an added paper refreshes the library and the workspaces. */
export function useAddPublishedVersion(doi: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => addPublished(doi),
    onSuccess: (outcome) =>
      outcome.kind === 'added' &&
      Promise.all([client.invalidateQueries({ queryKey: keys.papers }), client.invalidateQueries({ queryKey: keys.workspaces })]),
  })
}

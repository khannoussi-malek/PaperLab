import { useEffect, useRef, useState } from 'react'
import {
  QueryClient,
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type InfiniteData,
} from '@tanstack/react-query'
import { sameCandidate } from '@/features/discovery/candidateMeta'
import {
  api,
  type Candidate,
  type ChartSpec,
  type ChatScope,
  type DatasetCreate,
  type EligibilityUpdate,
  type GridIn,
  type Hit,
  type HitListOut,
  type HitReviewUpdate,
  type LLMConnectionUpdate,
  type NoteCreate,
  type NumberCreate,
  type NoteUpdate,
  type Paper,
  type PaperSourcesUpdate,
  type PaperUpdate,
  type PromoteRequest,
  type References,
  type ReferencesDirection,
  type SearchResult,
  type SearchRun,
  type SearchRunCreate,
  type SnowballRequest,
} from './client'

export const PAPERS_POLL_MS = 2000

export const queryClient = new QueryClient({
  // A local API answers or fails at once; retrying a 404 only delays the error the user needs to see.
  defaultOptions: { queries: { retry: false } },
})

const keys = {
  papers: ['papers'] as const,
  paper: (id: string) => ['papers', id] as const,
  notes: (paperId: string) => ['papers', paperId, 'notes'] as const,
  chunks: (paperId: string, page: number) => ['papers', paperId, 'chunks', page] as const,
  chat: (scope: ChatScope) => [scope.kind === 'paper' ? 'papers' : 'workspaces', scope.id, 'chat'] as const,
  // Every workspace query starts with this, so one invalidation refreshes the list, its counts and each home's tabs.
  workspaces: ['workspaces'] as const,
  workspacePapers: (id: string) => ['workspaces', id, 'papers'] as const,
  workspaceNotes: (id: string) => ['workspaces', id, 'notes'] as const,
  searchRuns: (workspaceId: string) => ['workspaces', workspaceId, 'search', 'runs'] as const,
  searchRun: (workspaceId: string, runId: string) => ['workspaces', workspaceId, 'search', 'runs', runId] as const,
  searchHits: (workspaceId: string, stage1Status: string, acquisitionStatus: string) =>
    ['workspaces', workspaceId, 'search', 'hits', stage1Status, acquisitionStatus] as const,
  // A prefix of every searchHits key above (whatever the filters), for invalidating them all at once.
  searchHitsRoot: (workspaceId: string) => ['workspaces', workspaceId, 'search', 'hits'] as const,
  // A prefix of every usePrismaExport key (whatever `runs`) — small and cheap to invalidate wholesale, unlike
  // searchHitsRoot's multi-thousand-row pool above.
  prismaRoot: (workspaceId: string) => ['workspaces', workspaceId, 'search', 'prisma'] as const,
  prisma: (workspaceId: string, runs: string) => [...keys.prismaRoot(workspaceId), runs] as const,
  // Every dataset query starts with this; a saved grid or a captured number refreshes every list and detail.
  datasets: ['datasets'] as const,
  paperDatasets: (paperId: string) => ['datasets', 'paper', paperId] as const,
  dataset: (id: string) => ['datasets', id] as const,
  // Resolved data lives under charts too: changing any data refetches the charts that draw it.
  charts: ['charts'] as const,
  chart: (id: string) => ['charts', id] as const,
  resolved: (spec: ChartSpec) => ['charts', 'resolve', spec] as const,
  // Every model query starts with this: a change on the settings page refreshes the chat dropdown too.
  llm: ['llm'] as const,
  chatModels: ['llm', 'models'] as const,
  connections: ['llm', 'connections'] as const,
  available: (connectionId: string) => ['llm', 'connections', connectionId, 'available'] as const,
  embedding: ['embedding'] as const,
  paperSources: ['paper-sources'] as const,
  // Outside the papers key on purpose: refreshing the library must not re-ask the paper sources.
  discovery: ['discovery'] as const,
  searches: ['discovery', 'search'] as const,
  search: (query: string) => ['discovery', 'search', query] as const,
  suggestions: ['discovery', 'similar'] as const,
  similar: (paperId: string) => ['discovery', 'similar', paperId] as const,
  // Outside the papers key on purpose, like discovery: References has its own tab and its own poll.
  references: (paperId: string) => ['references', paperId] as const,
  referencesDirection: (paperId: string, direction: ReferencesDirection) =>
    ['references', paperId, direction] as const,
  mcpSetup: ['mcp', 'setup'] as const,
  setup: ['setup'] as const,
  // Its own key: the graph is one payload, refetched when the owner's own links change, not when the library polls.
  graph: ['graph'] as const,
  libraryGraph: (workspaceId: string | null) => ['graph', workspaceId ?? 'library'] as const,
}

/** Poll the library only while a paper is still ingesting. */
export function papersPollInterval(papers: Paper[] | undefined): number | false {
  return papers?.some((paper) => paper.status !== 'ready' && paper.status !== 'failed') ? PAPERS_POLL_MS : false
}

/** Poll a search run only while it's still running. */
export function searchRunPollInterval(run: SearchRun | undefined): number | false {
  return run?.status === 'running' ? PAPERS_POLL_MS : false
}

export const usePapers = () =>
  useQuery({
    queryKey: keys.papers,
    queryFn: api.listPapers,
    refetchInterval: (query) => papersPollInterval(query.state.data),
  })

export const usePaper = (id: string) => useQuery({ queryKey: keys.paper(id), queryFn: () => api.getPaper(id) })

export const useNotes = (paperId: string) =>
  useQuery({ queryKey: keys.notes(paperId), queryFn: () => api.listNotes(paperId) })

/** One page's chunks, fetched only when `page` is set: the reader's `?chunk=` target needs its rects. */
export const useChunksOnPage = (paperId: string, page: number | null) =>
  useQuery({
    queryKey: keys.chunks(paperId, page ?? 0),
    queryFn: () => api.listChunks(paperId, page!),
    enabled: page !== null,
  })

/** Saved questions and answers for a paper or a workspace, oldest first. */
export const useChatHistory = (scope: ChatScope) =>
  useQuery({ queryKey: keys.chat(scope), queryFn: () => api.listChat(scope) })

/** For the chat stream, which isn't a query: refetch the history once an answer is saved. */
export function useInvalidateChatHistory(scope: ChatScope) {
  const client = useQueryClient()
  return () => client.invalidateQueries({ queryKey: keys.chat(scope) })
}

/** Re-runs ingestion, which embeds the paper: the fix for papers ingested before chat existed. */
export function useReindexPaper(paperId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api.reingestPaper(paperId),
    onSettled: () => client.invalidateQueries({ queryKey: keys.paper(paperId) }),
  })
}

/** Generates note suggestions for one paper (P1 of this feature: cards to accept or dismiss, never saved on
 * their own). No cache to invalidate on success — nothing is written yet, the caller just renders the result;
 * accepting one goes through usePromoteNote, unchanged, which already invalidates the note lists that need it. */
export function useSuggestNotes(paperId: string) {
  return useMutation({ mutationFn: () => api.suggestNotes(paperId) })
}

/** Saves part of a chat answer as an AI note. Resolves once the lists that show it have refetched and include it. */
export function usePromoteNote() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (promote: PromoteRequest) => api.promoteNote(promote),
    // A workspace answer can anchor the note on several papers, and workspace Notes tabs and counts list it too.
    onSuccess: (note) =>
      Promise.all([
        ...note.anchors.map((anchor) => client.invalidateQueries({ queryKey: keys.notes(anchor.paper_id) })),
        client.invalidateQueries({ queryKey: keys.workspaces }),
      ]),
  })
}

/** Saves a manual correction. The reader shows the saved paper at once; the library refetches. */
export function useUpdatePaper(paperId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (update: PaperUpdate) => api.updatePaper(paperId, update),
    onSuccess: (paper) => {
      client.setQueryData(keys.paper(paperId), paper)
      return client.invalidateQueries({ queryKey: keys.papers, exact: true })
    },
  })
}

/** Uploads PDFs one by one; with a `workspaceId` (a workspace's Papers tab) each also joins that workspace. */
export function useUploadPapers(workspaceId?: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async (files: File[]) => {
      for (const file of files) await api.uploadPaper(file, workspaceId)
    },
    onSettled: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: keys.papers }),
        client.invalidateQueries({ queryKey: keys.workspaces }),
      ]),
  })
}

export function useDeletePaper() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: api.deletePaper,
    // The paper drops out of any workspace it was in; refresh their counts and membership lists too.
    onSettled: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: keys.papers }),
        client.invalidateQueries({ queryKey: keys.workspaces }),
      ]),
  })
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
    mutationFn: (candidate: Candidate) => api.addCandidate(candidate, workspaceId),
    onSuccess: (paper, candidate) => {
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

/** Workspaces with their paper and note counts. */
export const useWorkspaces = () => useQuery({ queryKey: keys.workspaces, queryFn: api.listWorkspaces })

/** One workspace, read from the list (the API has no single-workspace route). `null` once loaded if it doesn't exist. */
export const useWorkspace = (id: string) =>
  useQuery({
    queryKey: keys.workspaces,
    queryFn: api.listWorkspaces,
    select: (workspaces) => workspaces.find((workspace) => workspace.id === id) ?? null,
  })

/** A workspace's papers. Polls while one is ingesting, like the library, so an upload from the Papers tab shows progress. */
export const useWorkspacePapers = (id: string) =>
  useQuery({
    queryKey: keys.workspacePapers(id),
    queryFn: () => api.listWorkspacePapers(id),
    refetchInterval: (query) => papersPollInterval(query.state.data),
  })

/** Every note anchored in a workspace's papers, each once, by paper title then reading position. */
export const useWorkspaceNotes = (id: string) =>
  useQuery({ queryKey: keys.workspaceNotes(id), queryFn: () => api.listWorkspaceNotes(id) })

export function useWorkspaceMutations() {
  const client = useQueryClient()
  const onSuccess = () => client.invalidateQueries({ queryKey: keys.workspaces })
  return {
    create: useMutation({ mutationFn: api.createWorkspace, onSuccess }),
    rename: useMutation({
      mutationFn: ({ id, name }: { id: string; name: string }) => api.renameWorkspace(id, name),
      onSuccess,
    }),
    remove: useMutation({
      mutationFn: api.deleteWorkspace,
      // Papers keep existing, but their `workspace_ids` lose this workspace.
      onSuccess: () => Promise.all([onSuccess(), client.invalidateQueries({ queryKey: keys.papers })]),
    }),
  }
}

type Membership = { workspaceId: string; paperIds: string[]; member: boolean }

/** Adds papers to a workspace (`member: true`) or removes them. Check marks, counts and the workspace's tabs follow. */
export function useWorkspaceMembership() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async ({ workspaceId, paperIds, member }: Membership) => {
      for (const paperId of paperIds) {
        await (member ? api.addToWorkspace(workspaceId, paperId) : api.removeFromWorkspace(workspaceId, paperId))
      }
    },
    onSettled: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: keys.papers }),
        client.invalidateQueries({ queryKey: keys.workspaces }),
      ]),
  })
}

/** Starts a search run for a workspace's saved query. */
export function useStartSearchRun(workspaceId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: SearchRunCreate) => api.startSearchRun(workspaceId, body),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.searchRuns(workspaceId) }),
  })
}

/** Stops a running search run. `stop_run` 409s ("search_run_not_running") when the run already finished naturally
 * right as the user clicked Stop — a harmless race (Minor 5), not a real error, so it's swallowed here: the mutation
 * re-fetches the run's real (now-finished) state and resolves with that instead of surfacing `.isError`. */
export function useStopSearchRun(workspaceId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async (runId: string) => {
      try {
        return await api.stopSearchRun(workspaceId, runId)
      } catch (error) {
        if (error instanceof Error && error.message === 'search_run_not_running') {
          return api.getSearchRun(workspaceId, runId)
        }
        throw error
      }
    },
    onSuccess: () => client.invalidateQueries({ queryKey: keys.searchRuns(workspaceId) }),
  })
}

/** One search run; polls while it's still running. `runId` is null before a run has started. */
export const useSearchRun = (workspaceId: string, runId: string | null) =>
  useQuery({
    queryKey: keys.searchRun(workspaceId, runId ?? ''),
    queryFn: () => api.getSearchRun(workspaceId, runId!),
    enabled: runId !== null,
    refetchInterval: (query) => searchRunPollInterval(query.state.data),
  })

/** A run's hits, keyset-paginated; `stage1Status`/`acquisitionStatus` each filter to one status ('all' when omitted). */
export const useSearchHits = (workspaceId: string, stage1Status?: string, acquisitionStatus?: string) =>
  useInfiniteQuery({
    queryKey: keys.searchHits(workspaceId, stage1Status ?? 'all', acquisitionStatus ?? 'all'),
    queryFn: ({ pageParam }) =>
      api.listSearchHits(workspaceId, {
        after: pageParam, limit: 50, stage1_status: stage1Status, acquisition_status: acquisitionStatus,
      }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  })

/** Every source's raw, pre-dedup count of what it's found so far, summed (`run.stats_json.per_source_raw_count`)
 * — "how many papers we found," before removing the ones more than one source turned up. `undefined` before the
 * run has reported any progress yet. */
export function totalRawFound(run: SearchRun | undefined): number | undefined {
  const rawCounts = run?.stats_json?.per_source_raw_count as Record<string, number> | undefined
  return rawCounts ? Object.values(rawCounts).reduce((sum, count) => sum + count, 0) : undefined
}

/** Signals that the hit pool is worth refreshing, without refreshing it automatically.
 *
 * An earlier version auto-invalidated the pool on every bit of progress (I1). That doesn't scale: invalidating
 * an infinite query re-fetches every already-loaded page, not just new data, and a search run can find a pool of
 * 3,000+ hits spread across dozens of pages — re-fetching all of them, repeatedly, in the background while a real
 * run trickles in new results over many minutes froze the UI (observed: 70+ requests in a single burst, every
 * ~20s, for as long as the run kept running). There is no cheap way to fetch only the new tail with this query
 * library's infinite-query model, so the fix is to not do it automatically at all — surface a lightweight count
 * (from the already-polled `stats_json`, no extra request) and let an explicit user action (`acknowledge`) pay
 * the one-time cost of a real refresh, exactly once, on demand.
 *
 * Keyed off the *cumulative* `stats_json.per_source_raw_count` (summed across sources, via `totalRawFound`), not
 * `last_batch_new_hits` — the worker overwrites `last_batch_new_hits` fresh every batch
 * (workers/workspace_search.py), so it's "how many hits did *this* batch add," not a running total, and two
 * different batches can report the same count. */
export function useNewHitsAvailable(run: SearchRun | undefined) {
  const rawCountTotal = totalRawFound(run)
  const baseline = useRef<number | undefined>(undefined)
  const [available, setAvailable] = useState(false)

  useEffect(() => {
    if (rawCountTotal === undefined) return
    if (baseline.current === undefined) {
      baseline.current = rawCountTotal // first tick just sets the starting point — nothing "new" relative to it yet
      return
    }
    if (rawCountTotal > baseline.current) setAvailable(true)
  }, [rawCountTotal])

  return {
    available,
    acknowledge: () => {
      baseline.current = rawCountTotal
      setAvailable(false)
    },
  }
}

/** The one-time, explicit refresh `useNewHitsAvailable`'s banner triggers on click. */
export function useRefreshHits(workspaceId: string) {
  const client = useQueryClient()
  return () => client.invalidateQueries({ queryKey: keys.searchHitsRoot(workspaceId) })
}

/** After one hit's fields change (review, import, upload), refresh every cached view of the hit pool:
 *
 * - Patch the new fields directly into every already-loaded page, in place, with no network request. This is
 *   what keeps HitTable's own view correct — it holds the *unfiltered* pool, which can run into the thousands of
 *   hits across dozens of pages, and re-fetching all of them on every single review/import/upload is the same
 *   scaling problem `useNewHitsAvailable`'s docstring describes for background polling (observed: a full-pool
 *   refetch burst on every click).
 * - Actually re-fetch any *filtered* view (e.g. ManualAcquisitionTab's `acquisition_status: 'failed'` list, which
 *   `WorkspacePage` keeps mounted alongside HitTable via `forceMount`): changing a hit's status can push it in or
 *   out of a filter's membership, which patching its fields in place can't fix — but a filtered view is always a
 *   small, bounded subset of the pool, so a real refetch there is cheap.
 * - Also invalidate `prismaRoot`: review/import/upload/eligibility can all shift the PRISMA funnel's counts, and
 *   PrismaTab stays mounted forever (`WorkspacePage`'s `forceMount`), so its export query never refetches on its
 *   own without this. `prismaRoot`'s pool is tiny (a handful of runs), unlike `searchHitsRoot` above, so a
 *   wholesale invalidate here needs no predicate. */
function patchMatchingHits(
  client: QueryClient,
  workspaceId: string,
  match: (hit: Hit) => boolean,
  fields: Partial<Hit>,
) {
  client.setQueriesData<InfiniteData<HitListOut, string | undefined>>(
    { queryKey: keys.searchHitsRoot(workspaceId) },
    (data) =>
      data && {
        ...data,
        pages: data.pages.map((page) => ({
          ...page,
          items: page.items.map((item) => (match(item) ? { ...item, ...fields } : item)),
        })),
      },
  )
  client.invalidateQueries({
    queryKey: keys.searchHitsRoot(workspaceId),
    predicate: (query) => query.queryKey[4] !== 'all' || query.queryKey[5] !== 'all',
  })
  client.invalidateQueries({ queryKey: keys.prismaRoot(workspaceId) })
}

function patchHitFields(client: QueryClient, workspaceId: string, hitId: string, fields: Partial<Hit>) {
  patchMatchingHits(client, workspaceId, (hit) => hit.id === hitId, fields)
}

/** Whether a cached hit is the one an eligibility update (keyed by paper + run, not hit id) just changed. */
export function matchesEligibleHit(hit: Hit, paperId: string, runId: string): boolean {
  return hit.paper_id === paperId && hit.run_id === runId
}

/** Reviews one hit (the stage-1 triage decision). */
export function usePatchSearchHit(workspaceId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ hitId, body }: { hitId: string; body: HitReviewUpdate }) =>
      api.patchSearchHit(workspaceId, hitId, body),
    onSuccess: (hit) => patchHitFields(client, workspaceId, hit.id, hit),
  })
}

/** Imports one hit into the corpus (the only way the UI calls this — HitTable's per-hit "Add PDF" button; see its
 * docstring for why this is never a bulk action). The import response only carries counts, not the updated hit,
 * so this derives the new `acquisition_status` from them directly: `imported` and `failed` are each 0 or 1 for a
 * single targeted hit, and exactly one of them is 1 — `failed` here means no free copy was found automatically,
 * not a request error, so it resolves rather than rejects (HitPreview keeps offering the manual options). */
export function useImportSearchHits(workspaceId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (hitIds: [string]) => api.importSearchHits(workspaceId, hitIds),
    onSuccess: (result, [hitId]) =>
      patchHitFields(client, workspaceId, hitId, { acquisition_status: result.imported > 0 ? 'imported' : 'failed' }),
  })
}

/** Imports every hit still pending acquisition in the current (unfiltered) pool — the deliberate "bulk" action
 * behind HitTable's "Import all with PDF in this filter" button, as opposed to `useImportSearchHits`'s one-hit-at-
 * a-time "Add PDF". The response carries no ids of what changed (could be many hits at once), so there's nothing
 * to patch — same reasoning as `useSnowball`'s reset: drop the unfiltered pool's own query back to page 1 and
 * re-fetch just that (never a blanket `invalidateQueries` over the whole family, which would re-fetch every
 * already-loaded page of a pool that can run into the thousands), plus a real, cheap refetch of any filtered
 * view whose membership could have shifted (e.g. ManualAcquisitionTab's `'failed'` filter). */
export function useImportAllHits(workspaceId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api.importSearchHits(workspaceId, undefined),
    onSuccess: () =>
      Promise.all([
        client.resetQueries({ queryKey: keys.searchHits(workspaceId, 'all', 'all'), exact: true }),
        client.invalidateQueries({
          queryKey: keys.searchHitsRoot(workspaceId),
          predicate: (query) => query.queryKey[4] !== 'all' || query.queryKey[5] !== 'all',
        }),
        client.invalidateQueries({ queryKey: keys.prismaRoot(workspaceId) }),
      ]),
  })
}

/** Deletes every hit not yet imported or manually acquired — the pool's own "start over" action. Same reset
 * (never invalidate) treatment of the big unfiltered pool as `useImportAllHits`, for the same reason: this can
 * change every row in it at once, and invalidating an infinite query re-fetches every already-loaded page. */
export function useClearSearchHits(workspaceId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api.clearSearchHits(workspaceId),
    onSuccess: () =>
      Promise.all([
        client.resetQueries({ queryKey: keys.searchHits(workspaceId, 'all', 'all'), exact: true }),
        client.invalidateQueries({
          queryKey: keys.searchHitsRoot(workspaceId),
          predicate: (query) => query.queryKey[4] !== 'all' || query.queryKey[5] !== 'all',
        }),
        client.invalidateQueries({ queryKey: keys.prismaRoot(workspaceId) }),
      ]),
  })
}

/** Manual acquisition (Task 10): uploads a PDF for one hit that had no free download. */
export function useUploadHitPdf(workspaceId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ hitId, file }: { hitId: string; file: File }) => api.uploadHitPdf(workspaceId, hitId, file),
    onSuccess: (hit) => patchHitFields(client, workspaceId, hit.id, hit),
  })
}

/** Sets a paper's stage-2 eligibility for one search run. The response is a full `EligibilityOut`, not a hit, so
 * this patches its `stage2_status`/`stage2_exclude_reason` onto every cached hit whose `(paper_id, run_id)`
 * matches `(paper_id, search_run_id)` from the response — never by `hit.id`, which the response doesn't carry.
 * Same filtered-views-only real invalidate as `patchHitFields`; see `patchMatchingHits`'s docstring above. */
export function useSetEligibility(workspaceId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ paperId, runId, body }: { paperId: string; runId: string; body: EligibilityUpdate }) =>
      api.setEligibility(workspaceId, paperId, runId, body),
    onSuccess: (out) =>
      patchMatchingHits(client, workspaceId, (hit) => matchesEligibleHit(hit, out.paper_id, out.search_run_id), {
        stage2_status: out.stage2_status,
        stage2_exclude_reason: out.stage2_exclude_reason,
      }),
  })
}

/** Runs backward/forward snowballing from a set of seed papers. The response (`new_hits`, `skipped_seeds`,
 * `errors`) carries no ids of what it created, so there's nothing to patch — the counts are surfaced directly
 * from this mutation's own `.data`/`.isSuccess`/`.isError` by ScreeningTab, the same way `HitTable` already
 * reads `useImportSearchHits`'s `failed` count from mutation state without any cache patching.
 *
 * `onSuccess` always invalidates `prismaRoot`: a snowballed hit can shift the PRISMA funnel's counts, and
 * PrismaTab stays mounted forever (`WorkspacePage`'s `forceMount`), so its export query never refetches on its
 * own without this.
 *
 * When `new_hits > 0`, it also *resets* — `exact: true`, one query, never the whole family — the unfiltered
 * pool's own query (`searchHits(workspaceId, 'all', 'all')`). Without this, a snowballed hit was invisible in
 * the Search tab until an unrelated refetch or a full reload: nothing else marks that query stale. `reset`, not
 * `invalidate`: invalidating an infinite query re-fetches every already-loaded page — the exact request storm
 * `patchMatchingHits`'s docstring describes for a pool that can run into the thousands of hits across dozens of
 * pages — while resetting drops it back to just page 1 and re-fetches only that. HARD RULE: never
 * `invalidateQueries({ queryKey: searchHitsRoot(workspaceId) })` here, or any other filtered variant — a
 * snowball call can run while the Search tab's big unfiltered pool (or a filtered tab) is mounted too, and a
 * wholesale invalidate would re-trigger a full refetch on every click. */
export function useSnowball(workspaceId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: SnowballRequest) => api.snowball(workspaceId, body),
    onSuccess: (result) => {
      const work = [client.invalidateQueries({ queryKey: keys.prismaRoot(workspaceId) })]
      if (result.new_hits > 0) {
        work.push(client.resetQueries({ queryKey: keys.searchHits(workspaceId, 'all', 'all'), exact: true }))
      }
      return Promise.all(work)
    },
  })
}

/** The PRISMA flow-diagram counts (`runs`: a single run id, or `'all'` to combine every run in the workspace). */
export function usePrismaExport(workspaceId: string, runs: string) {
  return useQuery({
    queryKey: keys.prisma(workspaceId, runs),
    queryFn: () => api.prismaExport(workspaceId, runs),
  })
}

export function useNoteMutations(paperId: string) {
  const client = useQueryClient()
  const onSuccess = () => client.invalidateQueries({ queryKey: keys.notes(paperId) })
  return {
    create: useMutation({ mutationFn: (note: NoteCreate) => api.createNote(note), onSuccess }),
    update: useMutation({
      mutationFn: ({ id, ...patch }: { id: string } & NoteUpdate) => api.updateNote(id, patch),
      onSuccess,
    }),
    remove: useMutation({ mutationFn: api.deleteNote, onSuccess }),
  }
}

/** A paper's datasets (captured tables and its numbers), in page order. */
export const usePaperDatasets = (paperId: string) =>
  useQuery({ queryKey: keys.paperDatasets(paperId), queryFn: () => api.listDatasets(paperId) })

/** Every dataset, most recently changed first: the chart builder's list of sources. */
export const useAllDatasets = () => useQuery({ queryKey: [...keys.datasets, 'all'], queryFn: () => api.listDatasets() })

export const useDataset = (id: string | null) =>
  useQuery({ queryKey: keys.dataset(id ?? ''), queryFn: () => api.getDataset(id!), enabled: id !== null })

/** Loads a dataset from an event (the chart builder's data picker), from `useDataset`'s cache when it's there. */
export function useLoadDataset() {
  const client = useQueryClient()
  return (id: string) => client.ensureQueryData({ queryKey: keys.dataset(id), queryFn: () => api.getDataset(id) })
}

/** Data changes redraw charts: every mutation refreshes datasets and charts. */
export function useDatasetMutations() {
  const client = useQueryClient()
  const onSuccess = () =>
    Promise.all([
      client.invalidateQueries({ queryKey: keys.datasets }),
      client.invalidateQueries({ queryKey: keys.charts }),
    ])
  return {
    create: useMutation({ mutationFn: (dataset: DatasetCreate) => api.createDataset(dataset), onSuccess }),
    importFile: useMutation({
      mutationFn: ({ file, name }: { file: File; name?: string }) => api.importDataset(file, name),
      onSuccess,
    }),
    rename: useMutation({ mutationFn: ({ id, name }: { id: string; name: string }) => api.renameDataset(id, name), onSuccess }),
    saveGrid: useMutation({
      mutationFn: ({ id, grid, force = false }: { id: string; grid: GridIn; force?: boolean }) => api.saveGrid(id, grid, force),
      onSuccess,
    }),
    remove: useMutation({
      mutationFn: ({ id, force = false }: { id: string; force?: boolean }) => api.deleteDataset(id, force),
      onSuccess,
    }),
    addNumber: useMutation({
      mutationFn: ({ paperId, number }: { paperId: string; number: NumberCreate }) => api.addNumber(paperId, number),
      onSuccess,
    }),
  }
}

export const useCharts = () => useQuery({ queryKey: keys.charts, queryFn: api.listCharts })

export const useChart = (id: string | null) =>
  useQuery({ queryKey: keys.chart(id ?? ''), queryFn: () => api.getChart(id!), enabled: id !== null })

/** The data a spec draws, paired with that spec. While a changed spec refetches, the placeholder is the previous pair,
 * so the last drawing stays up (compiled from its own spec) instead of a blank chart. */
export const useResolvedChart = (spec: ChartSpec | null) =>
  useQuery({
    queryKey: keys.resolved(spec!),
    queryFn: async () => ({ spec: spec!, data: await api.resolveChart(spec!) }),
    enabled: spec !== null,
    placeholderData: keepPreviousData,
  })

/** Notes show their charts: refetch every notes list (reader and workspaces) after a chart or an embed changes. */
const refreshNotes = (client: QueryClient) =>
  client.invalidateQueries({ predicate: (query) => query.queryKey[2] === 'notes' || query.queryKey[0] === 'workspaces' })

export function useChartMutations() {
  const client = useQueryClient()
  const charts = () => client.invalidateQueries({ queryKey: keys.charts })
  // A chart's links to datasets show on the datasets ("used by"), and notes show the chart's title.
  const everything = () => Promise.all([charts(), client.invalidateQueries({ queryKey: keys.datasets }), refreshNotes(client)])
  return {
    create: useMutation({
      mutationFn: ({ title, spec }: { title: string; spec: ChartSpec }) => api.createChart(title, spec),
      onSuccess: everything,
    }),
    update: useMutation({
      mutationFn: ({ id, ...patch }: { id: string; title?: string; spec?: ChartSpec }) => api.updateChart(id, patch),
      onSuccess: everything,
    }),
    duplicate: useMutation({ mutationFn: api.duplicateChart, onSuccess: everything }),
    remove: useMutation({ mutationFn: api.deleteChart, onSuccess: everything }),
    addToNote: useMutation({ mutationFn: api.addChartToNote, onSuccess: everything }),
    attach: useMutation({
      mutationFn: ({ noteId, chartId }: { noteId: string; chartId: string }) => api.attachChart(noteId, chartId),
      onSuccess: everything,
    }),
    detach: useMutation({
      mutationFn: ({ noteId, chartId }: { noteId: string; chartId: string }) => api.detachChart(noteId, chartId),
      onSuccess: everything,
    }),
  }
}

/** The models chat can use, for the dropdown. */
export const useChatModels = () => useQuery({ queryKey: keys.chatModels, queryFn: api.listChatModels })

export const useConnections = () => useQuery({ queryKey: keys.connections, queryFn: api.listConnections })

/** A provider's own model list, fetched only while the Add model picker is open. */
export const useAvailableModels = (connectionId: string, enabled: boolean) =>
  useQuery({ queryKey: keys.available(connectionId), queryFn: () => api.availableModels(connectionId), enabled })

export const useEmbeddingStatus = () => useQuery({ queryKey: keys.embedding, queryFn: api.embeddingStatus })

/** For a stream that isn't a mutation (the search model's download): read the embedding status again. */
export function useInvalidateEmbedding() {
  const client = useQueryClient()
  return () => client.invalidateQueries({ queryKey: keys.embedding })
}

/** For streams that aren't mutations (a chat refusal, a finished pull): refetch connections and chat models. */
export function useInvalidateModels() {
  const client = useQueryClient()
  return () => client.invalidateQueries({ queryKey: keys.llm })
}

export function useConnectionMutations() {
  const client = useQueryClient()
  const onSuccess = () => client.invalidateQueries({ queryKey: keys.llm })
  return {
    create: useMutation({ mutationFn: api.createConnection, onSuccess }),
    update: useMutation({
      mutationFn: ({ id, ...body }: { id: string } & LLMConnectionUpdate) => api.updateConnection(id, body),
      onSuccess,
    }),
    remove: useMutation({ mutationFn: api.deleteConnection, onSuccess }),
    test: useMutation({ mutationFn: api.testConnection }),
    addModel: useMutation({
      mutationFn: ({ connectionId, name }: { connectionId: string; name: string }) => api.addModel(connectionId, name),
      onSuccess,
    }),
    removeModel: useMutation({ mutationFn: api.removeModel, onSuccess }),
    setDefault: useMutation({ mutationFn: api.setDefaultModel, onSuccess }),
    deleteInstalled: useMutation({
      mutationFn: ({ connectionId, name }: { connectionId: string; name: string }) =>
        api.deleteInstalledModel(connectionId, name),
      onSuccess,
    }),
  }
}

export const usePaperSources = () => useQuery({ queryKey: keys.paperSources, queryFn: api.paperSources })

/** Saves a switch, a key or the contact email. Which sources answer changes, so searches and suggestions ask again. */
export function useUpdatePaperSources() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (patch: PaperSourcesUpdate) => api.updatePaperSources(patch),
    onSuccess: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: keys.paperSources }),
        client.invalidateQueries({ queryKey: keys.discovery }),
      ]),
  })
}

/** Queues a re-embed of every paper; the status line refetches once it's queued. */
export function useReindexLibrary() {
  const client = useQueryClient()
  return useMutation({ mutationFn: api.reindexLibrary, onSettled: () => client.invalidateQueries({ queryKey: keys.embedding }) })
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
    onSuccess: () => client.invalidateQueries({ queryKey: keys.references(paperId) }),
  })
}

/** Imports one reference. Each row owns its own mutation, so only that row shows "Importing…". */
export function useImportReference(paperId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ refId, workspaceId }: { refId: string; workspaceId?: string }) =>
      api.importReference(refId, workspaceId),
    onSuccess: (paper, { refId }) => {
      // So the row still shows "In library" after the tab is closed and reopened, even though that only rereads the
      // cache. New arrays and objects throughout: never mutate cached query data. Matches both directions' caches,
      // since keys.references(paperId) is a prefix of each direction's own query key.
      const marked = (data: References | undefined) =>
        data
          ? { ...data, rows: data.rows.map((row) => (row.id === refId ? { ...row, paper_id: paper.id } : row)) }
          : data
      client.setQueriesData<References>({ queryKey: keys.references(paperId) }, marked)
      return Promise.all([
        client.invalidateQueries({ queryKey: keys.papers, exact: true }),
        client.invalidateQueries({ queryKey: keys.workspaces }),
      ])
    },
  })
}

/** The folder Connect Claude prefills. */
export const useMcpSetup = () => useQuery({ queryKey: keys.mcpSetup, queryFn: api.mcpSetup })

/** Connect Claude's server check. Nothing is cached: each click checks again. */
export const useCheckMcpServer = () => useMutation({ mutationFn: api.checkMcpServer })

/** Every library paper and the links between them, in one request (D109): layers and focus need no further calls. */
export const useLibraryGraph = (workspaceId: string | null) =>
  useQuery({
    queryKey: keys.libraryGraph(workspaceId),
    queryFn: () => api.libraryGraph(workspaceId),
    placeholderData: keepPreviousData,
  })

/** The owner's own links. Each write refetches the graph, which carries them. Save and remove report separately. */
export function usePaperLinkMutations() {
  const client = useQueryClient()
  const onSuccess = () => client.invalidateQueries({ queryKey: keys.graph })
  const create = useMutation({
    mutationFn: ({ from, to, label }: { from: string; to: string; label: string }) =>
      api.createPaperLink(from, to, label),
    onSuccess,
  })
  const rename = useMutation({
    mutationFn: ({ id, label }: { id: string; label: string }) => api.renamePaperLink(id, label),
    onSuccess,
  })
  const remove = useMutation({ mutationFn: api.deletePaperLink, onSettled: onSuccess })
  return {
    create,
    rename,
    remove,
    /** The dialog shows these two; the panel shows a failed removal, which has no dialog. */
    saveError: (create.error ?? rename.error)?.message ?? null,
    removeError: remove.error?.message ?? null,
  }
}

/** Whether the first-run setup is done (the server's one flag); read once on start (useOpenSetupOnStart). */
export const useSetup = () => useQuery({ queryKey: keys.setup, queryFn: api.setup })

/** Finish and Skip: done for every browser and the desktop app, since the flag lives on the server. */
export function useFinishSetup() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api.setSetupDone(true),
    onSuccess: (setup) => client.setQueryData(keys.setup, setup),
  })
}

import { QueryClient, keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { sameCandidate } from '@/features/discovery/candidateMeta'
import {
  api,
  type Candidate,
  type ChartSpec,
  type ChatScope,
  type DatasetCreate,
  type GridIn,
  type LLMConnectionUpdate,
  type NoteCreate,
  type NumberCreate,
  type NoteUpdate,
  type Paper,
  type PaperSourcesUpdate,
  type PaperUpdate,
  type PromoteRequest,
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
  // Outside the papers key on purpose: refreshing the library must not re-ask OpenAlex or Semantic Scholar.
  discovery: ['discovery'] as const,
  search: (query: string) => ['discovery', 'search', query] as const,
  similar: (paperId: string) => ['discovery', 'similar', paperId] as const,
}

/** Poll the library only while a paper is still ingesting. */
export function papersPollInterval(papers: Paper[] | undefined): number | false {
  return papers?.some((paper) => paper.status !== 'ready' && paper.status !== 'failed') ? PAPERS_POLL_MS : false
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

// Each OpenAlex search costs 10 of its 1,000 free daily credits; suggestions change slowly.
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
      client.setQueriesData<Candidate[]>({ queryKey: keys.discovery }, (candidates) =>
        candidates?.map((existing) =>
          sameCandidate(existing, candidate) ? { ...existing, paper_id: paper.id } : existing,
        ),
      )
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

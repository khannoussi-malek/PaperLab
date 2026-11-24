import { MutationCache, QueryClient } from '@tanstack/react-query'
import { PaperMergedError } from '@/services/api'
import type { ChartSpec, ChatScope, ReferencesDirection } from '@/entities'

export const PAPERS_POLL_MS = 2000

export const queryClient: QueryClient = new QueryClient({
  // A local API answers or fails at once; retrying a 404 only delays the error the user needs to see.
  defaultOptions: { queries: { retry: false } },
  mutationCache: new MutationCache({
    // A save on a paper merged meanwhile (R19): its details refetch, answer 410, and the reader moves to the kept one.
    // ponytail: the 410 names only the kept paper, so every open paper's details refetch; a merge is rare.
    onError: (error) => {
      if (error instanceof PaperMergedError)
        void queryClient.invalidateQueries({ predicate: (q) => q.queryKey[0] === 'papers' && q.queryKey.length === 2 })
    },
  }),
})

export const keys = {
  // Every manuscript query starts with this, so one invalidation refreshes lists, details, files and history.
  manuscripts: ['manuscripts'] as const,
  manuscriptList: (workspaceId: string | null) => ['manuscripts', 'list', workspaceId ?? 'orphans'] as const,
  manuscript: (id: string) => ['manuscripts', id] as const,
  manuscriptFile: (id: string, path: string) => ['manuscripts', id, 'file', path] as const,
  // Not under ['manuscripts', id]: an autosave invalidates that, and the papers only change on a pin, a section or
  // file operation, or a compile (which pins the keys it cites).
  manuscriptPapers: (id: string) => ['manuscriptPapers', id] as const,
  // Per-paper note counts for a set of papers; ['noteCounts'] is the prefix a note change invalidates.
  noteCounts: (sortedIds: string[]) => ['noteCounts', sortedIds] as const,
  // Keyed by compiledAt: a new compile refetches. Under ['manuscripts', id] so an autosave refreshes it too.
  missingKeys: (id: string, compiledAt: string | null | undefined) => ['manuscripts', id, 'missingKeys', compiledAt ?? null] as const,
  checkBadge: (id: string, compiledAt: string | null | undefined) => ['manuscripts', id, 'checkBadge', compiledAt ?? null] as const,
  checkList: (id: string) => ['manuscriptChecks', id, 'list'] as const,
  manuscriptSnapshots: (id: string) => ['manuscripts', id, 'snapshots'] as const,
  papers: ['papers'] as const,
  paper: (id: string) => ['papers', id] as const,
  notes: (paperId: string) => ['papers', paperId, 'notes'] as const,
  chunks: (paperId: string, page: number) => ['papers', paperId, 'chunks', page] as const,
  embeddingProgress: (paperId: string) => ['papers', paperId, 'embedding-progress'] as const,
  chat: (scope: ChatScope) =>
    scope.kind === 'hit'
      ? (['workspaces', scope.workspaceId, 'hits', scope.id, 'chat'] as const)
      : ([scope.kind === 'paper' ? 'papers' : 'workspaces', scope.id, 'chat'] as const),
  // Every workspace query starts with this, so one invalidation refreshes the list, its counts and each home's tabs.
  workspaces: ['workspaces'] as const,
  workspacePapers: (id: string) => ['workspaces', id, 'papers'] as const,
  tags: (ws: string) => ['workspaces', ws, 'tags'] as const,
  paperTags: (ws: string) => ['workspaces', ws, 'paper-tags'] as const,
  paperTagsOfPaper: (id: string) => ['papers', id, 'tags'] as const,
  workspaceNotes: (id: string) => ['workspaces', id, 'notes'] as const,
  packageRecord: (id: string) => ['workspaces', id, 'package-record'] as const,
  packageCheck: (id: string, pdfs: boolean, answers: boolean) =>
    ['workspaces', id, 'package-check', pdfs, answers] as const,
  searchRuns: (workspaceId: string) => ['workspaces', workspaceId, 'search', 'runs'] as const,
  evidenceCards: (workspaceId: string) => ['workspaces', workspaceId, 'evidence-cards'] as const,
  evidenceCard: (paperId: string) => ['papers', paperId, 'evidence-card'] as const,
  savedSearches: (workspaceId: string) => ['workspaces', workspaceId, 'saved-searches'] as const,
  searchRun: (workspaceId: string, runId: string) => ['workspaces', workspaceId, 'search', 'runs', runId] as const,
  searchHits: (workspaceId: string, stage1Status: string, acquisitionStatus: string) =>
    ['workspaces', workspaceId, 'search', 'hits', stage1Status, acquisitionStatus] as const,
  // A prefix of every searchHits key above (whatever the filters), for invalidating them all at once.
  searchHitsRoot: (workspaceId: string) => ['workspaces', workspaceId, 'search', 'hits'] as const,
  rankedHits: (workspaceId: string) => ['workspaces', workspaceId, 'search', 'ranked'] as const,
  screening: (workspaceId: string) => ['workspaces', workspaceId, 'search', 'screening'] as const,
  // A prefix of every usePrismaExport key (whatever `runs`) — small and cheap to invalidate wholesale, unlike
  // searchHitsRoot's multi-thousand-row pool above.
  snowballNext: (workspaceId: string) => ['workspaces', workspaceId, 'search', 'snowball-next'] as const,
  provenance: (workspaceId: string) => ['workspaces', workspaceId, 'search', 'provenance'] as const,
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
  // Every skills query starts with this, so one invalidation refreshes each kind's list and the hidden list.
  skills: ['skills'] as const,
  connections: ['llm', 'connections'] as const,
  available: (connectionId: string) => ['llm', 'connections', connectionId, 'available'] as const,
  embedding: ['embedding'] as const,
  voiceStatus: ['voice', 'status'] as const,
  voiceLatency: ['voice', 'latency'] as const,
  paperSources: ['paper-sources'] as const,
  paperEvents: (id: string) => ['papers', id, 'events'] as const,
  foundPdfs: ['papers', 'found-pdfs'] as const,
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
  mcpActivity: ['mcp', 'activity'] as const,
  mcpSettings: ['mcp', 'settings'] as const,
  setup: ['setup'] as const,
  // Its own key: the graph is one payload, refetched when the owner's own links change, not when the library polls.
  graph: ['graph'] as const,
  libraryGraph: (workspaceId: string | null) => ['graph', workspaceId ?? 'library'] as const,
  // The Notes page's lists: every note, one paper's, or those on no paper.
  allNotes: (paper: string | null) => ['notes', paper ?? 'all'] as const,
  triageEvents: (paperId: string) => ['papers', paperId, 'triage-events'] as const,
  readingContext: (paperId: string) => ['papers', paperId, 'reading-context'] as const,
  // A prefix of every readingQueue key below (whatever `runId`), like prismaRoot above — small and cheap to
  // invalidate wholesale whenever a screening/import action could change which papers (or priorities) it lists.
  readingQueueRoot: (workspaceId: string) => ['workspaces', workspaceId, 'search', 'reading-queue'] as const,
  readingQueue: (workspaceId: string, runId: string) => [...keys.readingQueueRoot(workspaceId), runId] as const,
}

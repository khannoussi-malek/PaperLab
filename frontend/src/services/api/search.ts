import { request, sendJson } from '../http'
import type { AcceptSuggestionsOut, BranchIn, BranchOut, BulkHitReviewUpdate, BulkUpdateOut, ClearHitsOut, EligibilityOut, EligibilityUpdate, Hit, HitListOut, HitReviewUpdate, ImportHitsOut, NextItem, PrismaExportOut, ProvenanceOut, ProvLink, RankedHits, ReadingContextList, ReadingQueue, SavedSearch, SavedSearchCreate, SavedSearchUpdate, ScreeningState, ScreeningUpdate, SearchRun, SearchRunCreate, SearchRunSummary, SnowballNextOut, SnowballOut, SnowballRequest } from '@/entities'

export const searchApi = {
  startSearchRun: (workspaceId: string, body: SearchRunCreate) =>
    request<SearchRun>(`/api/workspaces/${workspaceId}/search/runs`, sendJson('POST', body)),
  stopSearchRun: (workspaceId: string, runId: string) =>
    request<SearchRun>(`/api/workspaces/${workspaceId}/search/runs/${runId}/stop`, { method: 'POST' }),
  continueSearchRun: (workspaceId: string, runId: string) =>
    request<SearchRun>(`/api/workspaces/${workspaceId}/search/runs/${runId}`, { method: 'POST' }),
  listSavedSearches: (workspaceId: string) =>
    request<SavedSearch[]>(`/api/workspaces/${workspaceId}/saved-searches`),
  createSavedSearch: (workspaceId: string, body: SavedSearchCreate) =>
    request<SavedSearch>(`/api/workspaces/${workspaceId}/saved-searches`, sendJson('POST', body)),
  updateSavedSearch: (workspaceId: string, id: string, body: SavedSearchUpdate) =>
    request<SavedSearch>(`/api/workspaces/${workspaceId}/saved-searches/${id}`, sendJson('PATCH', body)),
  deleteSavedSearch: (workspaceId: string, id: string) =>
    request<void>(`/api/workspaces/${workspaceId}/saved-searches/${id}`, { method: 'DELETE' }),
  runSavedSearchNow: (workspaceId: string, id: string) =>
    request<SearchRun>(`/api/workspaces/${workspaceId}/saved-searches/${id}/run`, { method: 'POST' }),
  markSavedSearchSeen: (workspaceId: string, id: string) =>
    request<SavedSearch>(`/api/workspaces/${workspaceId}/saved-searches/${id}/seen`, { method: 'POST' }),
  listSearchRuns: (workspaceId: string, limit = 20) =>
    request<SearchRunSummary[]>(`/api/workspaces/${workspaceId}/search/runs?limit=${limit}`),
  getSearchRun: (workspaceId: string, runId: string) =>
    request<SearchRun>(`/api/workspaces/${workspaceId}/search/runs/${runId}`),
  listSearchHits: (
    workspaceId: string,
    params: {
      after?: string; limit?: number; stage1_status?: string; acquisition_status?: string; sort?: 'ai'; min_relevance?: number
      saved_search_id?: string; found_after?: string
    },
  ) => {
    const entries = Object.entries(params).filter(([, value]) => value !== undefined) as [string, string | number][]
    const query = new URLSearchParams(entries.map(([key, value]) => [key, String(value)]))
    return request<HitListOut>(`/api/workspaces/${workspaceId}/search/hits?${query}`)
  },
  patchSearchHit: (workspaceId: string, hitId: string, body: HitReviewUpdate) =>
    request<Hit>(`/api/workspaces/${workspaceId}/search/hits/${hitId}`, sendJson('PATCH', body)),
  bulkPatchSearchHits: (workspaceId: string, body: BulkHitReviewUpdate) =>
    request<BulkUpdateOut>(`/api/workspaces/${workspaceId}/search/hits/bulk`, sendJson('PATCH', body)),
  /** `inbox` ranks only what one saved search found after a time (M7.6); the model still trains on every decision. */
  rankedSearchHits: (workspaceId: string, limit = 200, inbox?: { saved_search_id: string; found_after: string }) =>
    request<RankedHits>(
      `/api/workspaces/${workspaceId}/search/hits/ranked?${new URLSearchParams({ limit: String(limit), ...inbox })}`,
    ),
  /** `hitIds` omitted imports every hit still pending acquisition. */
  importSearchHits: (workspaceId: string, hitIds?: string[]) =>
    request<ImportHitsOut>(
      `/api/workspaces/${workspaceId}/search/hits/import`, sendJson('POST', { hit_ids: hitIds ?? null }),
    ),
  /** Deletes every hit in the pool not yet imported or manually acquired; papers already in the corpus stay. */
  clearSearchHits: (workspaceId: string) =>
    request<ClearHitsOut>(`/api/workspaces/${workspaceId}/search/hits`, { method: 'DELETE' }),
  uploadHitPdf: (workspaceId: string, hitId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<Hit>(`/api/workspaces/${workspaceId}/search/hits/${hitId}/upload`, { method: 'POST', body: form })
  },
  snowball: (workspaceId: string, body: SnowballRequest) =>
    request<SnowballOut>(`/api/workspaces/${workspaceId}/search/snowball`, sendJson('POST', body)),
  provenance: (workspaceId: string, allHitsRun?: string) =>
    request<ProvenanceOut>(
      `/api/workspaces/${workspaceId}/search/provenance${allHitsRun ? `?all_hits_run=${allHitsRun}` : ''}`,
    ),
  setBranch: (workspaceId: string, body: BranchIn) =>
    request<BranchOut>(`/api/workspaces/${workspaceId}/search/branch`, sendJson('PUT', body)),
  snowballNext: (workspaceId: string) => request<NextItem[]>(`/api/workspaces/${workspaceId}/search/snowball-next`),
  runSnowballNext: (workspaceId: string) =>
    request<SnowballNextOut>(`/api/workspaces/${workspaceId}/search/snowball-next/run`, { method: 'POST' }),
  getSearchHit: (workspaceId: string, hitId: string) =>
    request<Hit>(`/api/workspaces/${workspaceId}/search/hits/${hitId}`),
  /** Reads one hit against the review question and writes its suggestion fields. A 409's `detail` is the code. */
  suggestHit: (workspaceId: string, hitId: string, confirmRemote = false) =>
    request<Hit>(`/api/workspaces/${workspaceId}/search/hits/${hitId}/suggest`, sendJson('POST', { confirm_remote: confirmRemote })),
  hitPaths: (workspaceId: string, hitId: string) =>
    request<ProvLink[][]>(`/api/workspaces/${workspaceId}/search/hits/${hitId}/paths`),
  setEligibility: (workspaceId: string, paperId: string, runId: string, body: EligibilityUpdate) =>
    request<EligibilityOut>(
      `/api/workspaces/${workspaceId}/papers/${paperId}/eligibility?run=${runId}`,
      sendJson('PATCH', body),
    ),
  /** `runs`: a single run id, or `'all'` to combine every run in the workspace. */
  prismaExport: (workspaceId: string, runs: string) =>
    request<PrismaExportOut>(`/api/workspaces/${workspaceId}/search/prisma?runs=${runs}`),
  readingContext: (paperId: string) => request<ReadingContextList>(`/api/papers/${paperId}/reading-context`),
  /** `runId`: a single run id, or `'all'` for every run in the workspace (one row per paper). */
  readingQueue: (workspaceId: string, runId: string) =>
    request<ReadingQueue>(`/api/workspaces/${workspaceId}/search/reading-queue${runId === 'all' ? '' : `?run=${runId}`}`),
  screeningState: (workspaceId: string) => request<ScreeningState>(`/api/workspaces/${workspaceId}/search/screening`),
  /** Any subset of the criteria and settings. */
  saveScreening: (workspaceId: string, body: ScreeningUpdate) =>
    request<ScreeningState>(`/api/workspaces/${workspaceId}/search/screening`, sendJson('PUT', body)),
  acceptSuggestions: (workspaceId: string, hitIds: string[]) =>
    request<AcceptSuggestionsOut>(
      `/api/workspaces/${workspaceId}/search/hits/accept-suggestions`, sendJson('POST', { hit_ids: hitIds }),
    ),
  startSuggestions: (workspaceId: string, confirmRemote: boolean) =>
    request<ScreeningState>(
      `/api/workspaces/${workspaceId}/search/suggestions`, sendJson('POST', { confirm_remote: confirmRemote }),
    ),
  stopSuggestions: (workspaceId: string) =>
    request<ScreeningState>(`/api/workspaces/${workspaceId}/search/suggestions/stop`, { method: 'POST' }),
}

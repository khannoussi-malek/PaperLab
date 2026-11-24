import type { components } from './schema'

// The three continue fields are intersected in by hand until gen:api sees them.
export type SearchRun = components['schemas']['SearchRunOut'] & {
  can_continue?: boolean
  sources_left?: string[]
  paused_sources?: string[]
}
// Written by hand to match the backend's SearchRunSummary until gen:api sees the list route.
export type SearchRunSummary = {
  id: string
  query_text: string
  status: string
  started_at: string
  stopped_at: string | null
  sources_json: string[]
  per_source_raw_count: Record<string, number>
  failed_sources: string[]
  hit_count: number
  can_continue: boolean
  sources_left: string[]
  paused_sources: string[]
  outcome?: string
  snowball?: SnowballStats | null
}
export type SnowballStats = components['schemas']['SnowballStats']
export type SavedSearch = components['schemas']['SavedSearchOut']
export type SavedSearchCreate = components['schemas']['SavedSearchCreate']
export type SavedSearchUpdate = components['schemas']['SavedSearchUpdate']
export type SearchRunCreate = components['schemas']['SearchRunCreate']
// The five sources search_batch actually fans out to (backend's SearchSource Literal) — unlike PaperSourceId,
// never includes 'unpaywall', which has no search/discovery role (spec §6).
// Named SearchRunSource, not SearchSource: M25 gives the embedding search source that name instead (SearchSourceOut).
export type SearchRunSource = SearchRunCreate['sources'][number]
export type Hit = components['schemas']['HitOut']
export type HitListOut = components['schemas']['HitListOut']
export type HitReviewUpdate = components['schemas']['HitReviewUpdate']
export type BulkHitReviewUpdate = components['schemas']['BulkHitReviewUpdate']
export type BulkUpdateOut = components['schemas']['BulkUpdateOut']
export type ImportHitsOut = components['schemas']['ImportHitsOut']
export type RankedHits = components['schemas']['RankedHitsOut']
export type ClearHitsOut = components['schemas']['ClearHitsOut']
export type SnowballRequest = components['schemas']['SnowballRequest']
export type SnowballOut = components['schemas']['SnowballOut']
export type ProvenanceOut = components['schemas']['ProvenanceOut']
export type BranchIn = components['schemas']['BranchIn']
export type BranchOut = components['schemas']['BranchOut']
export type SnowballNextOut = components['schemas']['SnowballNextOut']
export type NextItem = components['schemas']['NextItem']
export type ProvBranch = components['schemas']['ProvBranch']
export type ProvNode = components['schemas']['ProvNode']
export type ProvLink = components['schemas']['ProvLink']
export type ProvRoot = components['schemas']['ProvRoot']
export type LevelStats = components['schemas']['LevelStats']
export type EligibilityUpdate = components['schemas']['EligibilityUpdate']
export type EligibilityOut = components['schemas']['EligibilityOut']
export type PrismaExportOut = components['schemas']['PrismaExportOut']
export type ReadingContextList = components['schemas']['ReadingContextListOut']
export type ReadingQueue = components['schemas']['ReadingQueueOut']
export type ScreeningState = components['schemas']['ScreeningStateOut']
export type ScreeningUpdate = components['schemas']['ScreeningCriteriaUpdate']
export type AcceptSuggestionsOut = components['schemas']['AcceptSuggestionsOut']

/** A saved search's new finds: hits its runs found after `since` (its last look when the reader opened them). */
export type SavedSearchInbox = { savedSearchId: string; query: string; since: string }

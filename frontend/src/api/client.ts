import type { components } from './schema'

export type Manuscript = components['schemas']['ManuscriptOut']
export type ManuscriptDetail = components['schemas']['ManuscriptDetailOut']
export type ManuscriptImport = components['schemas']['ManuscriptImportOut']
export type ManuscriptTemplate = components['schemas']['TemplateOut']
export type ManuscriptFile = components['schemas']['FileOut']
export type ManuscriptFileText = components['schemas']['FileTextOut']
export type ManuscriptSnapshot = components['schemas']['SnapshotOut']
export type EvidenceFound = components['schemas']['EvidenceFoundOut']
export type EvidenceRow = components['schemas']['EvidenceRowOut']
export type NoteCounts = Record<string, components['schemas']['PaperNoteCounts']>
export type MissingKey = components['schemas']['MissingKeyOut']
export type ReviewRun = components['schemas']['ReviewRunOut']
export type CheckItem = components['schemas']['CheckItemOut']
export type ReviewState = components['schemas']['ReviewOut']
export type ReviewSentence = components['schemas']['SentenceOut']
export type ReviewStart = { file: string; base: string; from?: number | null; to?: number | null; include_uncited?: boolean; confirm_remote?: boolean }
export type SectionReview = components['schemas']['SectionReviewOut']
export type SectionFinding = components['schemas']['FindingOut']
export type SectionRef = components['schemas']['RefOut']
export type SectionSpan = components['schemas']['SectionSpanOut']
export type SectionReviewStart = components['schemas']['SectionReviewIn']
export type Diagram = components['schemas']['DiagramOut']
export type DiagramStart = components['schemas']['DiagramIn']
export type CitablePaper = components['schemas']['CitablePaperOut']
export type ManuscriptCreate = components['schemas']['ManuscriptCreate']
export type ManuscriptPatch = components['schemas']['ManuscriptPatch']
export type Paper = components['schemas']['PaperOut']
export type PaperUpdate = components['schemas']['PaperUpdate']
export type ReadingIn = components['schemas']['ReadingIn']
export type TriageEvent = components['schemas']['TriageEventOut']
export type TriageDecisionIn = components['schemas']['TriageDecisionIn']
export type TriageDecision = components['schemas']['TriageDecisionOut']
export type TriageSummary = components['schemas']['TriageSummaryOut']
export type EvidenceCard = components['schemas']['CardOut']
export type EvidenceCardRow = components['schemas']['CardRowOut']
export type EvidenceChange = components['schemas']['EditIn']['changes'][number]
export type Chunk = components['schemas']['ChunkOut']
export type Note = components['schemas']['NoteOut']
export type NoteCreate = components['schemas']['NoteCreate']
export type NoteUpdate = components['schemas']['NoteUpdate']
export type ChatSource = components['schemas']['ChatSource']
export type NoteSource = components['schemas']['NoteSource']
export type ChatAnswer = components['schemas']['ChatAnswer']
export type SavedNote = components['schemas']['SavedNoteOut']
// Prefixed: the DOM already has a global `ErrorEvent`.
export type ChatSourcesEvent = components['schemas']['SourcesEvent']
export type ChatTokenEvent = components['schemas']['TokenEvent']
export type ChatDoneEvent = components['schemas']['DoneEvent']
export type ChatErrorEvent = components['schemas']['ErrorEvent']
export type PromoteRequest = components['schemas']['PromoteRequest']
export type NoteSuggestion = components['schemas']['NoteSuggestionOut']
export type NoteSuggestionsOut = components['schemas']['NoteSuggestionsOut']
export type TagSummary = components['schemas']['TagOut']
export type TagResult = components['schemas']['TagResultOut']
export type TagRenamed = components['schemas']['TagRenamed']
export type TagDeleted = components['schemas']['TagDeleted']
export type PaperTagGroup = components['schemas']['PaperTagGroup']
export type ImportPreview = components['schemas']['ImportPreviewOut']
export type ImportProgress = components['schemas']['ImportProgressOut']
export type ImportResult = components['schemas']['ImportResultOut']
export type Workspace = components['schemas']['WorkspaceOut']
export type ChartRef = components['schemas']['ChartRefOut']
export type Dataset = components['schemas']['DatasetOut']
export type DatasetSummary = components['schemas']['DatasetSummaryOut']
export type DatasetCreate = components['schemas']['DatasetCreate']
export type GridIn = components['schemas']['GridIn']
export type TablePreview = components['schemas']['TablePreviewOut']
export type ChartUse = components['schemas']['ChartUseOut']
export type NumberCandidate = components['schemas']['NumberCandidateOut']
export type NumberCreate = components['schemas']['NumberCreate']
export type NumberAdded = components['schemas']['NumberAddedOut']
export type Chart = components['schemas']['ChartOut']
export type ChartSummary = components['schemas']['ChartSummaryOut']
export type ChartSpec = Chart['spec']
export type SeriesChartSpec = components['schemas']['SeriesChart']
export type SeriesSpec = components['schemas']['Series']
export type ResolvedData = components['schemas']['ResolvedDataOut']
export type ResolvedDataset = components['schemas']['ResolvedDatasetOut']
export type ResolvedCell = components['schemas']['ResolvedCellOut']
export type ChatModel = components['schemas']['ChatModelOut']
export type LLMConnection = components['schemas']['ConnectionOut']
export type LLMConnectionCreate = components['schemas']['ConnectionCreate']
export type LLMConnectionUpdate = components['schemas']['ConnectionUpdate']
export type LLMModel = components['schemas']['ModelOut']
export type ConnectionCheck = components['schemas']['ConnectionCheckOut']
export type AvailableModels = components['schemas']['AvailableModelsOut']
export type PullProgressEvent = components['schemas']['PullProgressEvent']
export type PullDoneEvent = components['schemas']['PullDoneEvent']
export type PullErrorEvent = components['schemas']['PullErrorEvent']
export type EmbeddingStatus = components['schemas']['EmbeddingStatusOut']
export type SearchSource = components['schemas']['SearchSourceOut']
export type SearchSourceIn = components['schemas']['SearchSourceIn']
export type Rebuild = components['schemas']['RebuildOut']
export type DownloadProgressEvent = components['schemas']['DownloadProgressEvent']
export type DownloadDoneEvent = components['schemas']['DownloadDoneEvent']
export type DownloadErrorEvent = components['schemas']['DownloadErrorEvent']
export type Candidate = components['schemas']['CandidateOut']
export type SearchResult = components['schemas']['SearchOut']
export type PaperSources = components['schemas']['PaperSourcesOut']
export type PaperSource = components['schemas']['PaperSourceOut']
export type PaperSourceId = PaperSource['id']
export type PaperEvent = components['schemas']['PaperEventOut']
export type FoundPdf = components['schemas']['FoundPdfOut']
export type PaperSourcesUpdate = components['schemas']['PaperSourcesUpdate']
export type References = components['schemas']['ReferencesOut']
export type Reference = components['schemas']['ReferenceOut']
export type ReferencesDirection = References['direction']
export type ReferencePage = components['schemas']['ReferencePageOut']
export type RefreshOut = components['schemas']['RefreshOut']
export type McpSetup = components['schemas']['McpSetupOut']
export type McpCheck = components['schemas']['McpCheckOut']
export type SetupState = components['schemas']['SetupOut']
export type GraphNode = components['schemas']['GraphNode']
export type GraphLink = components['schemas']['GraphLink']
export type LibraryGraph = components['schemas']['GraphOut']
export type PaperLinkOut = components['schemas']['LinkOut']
export type PaperSections = components['schemas']['SectionsOut']
export type Section = components['schemas']['SectionOut']
export type Lens = components['schemas']['LensOut']
export type LensId = Lens['id']
export type Role = Section['role']
export type SectionRoleIn = components['schemas']['SectionRoleIn']
export type Brief = components['schemas']['BriefOut']
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
}
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
export type EligibilityUpdate = components['schemas']['EligibilityUpdate']
export type EligibilityOut = components['schemas']['EligibilityOut']
export type PrismaExportOut = components['schemas']['PrismaExportOut']
export type ReadingContextList = components['schemas']['ReadingContextListOut']
export type ReadingQueue = components['schemas']['ReadingQueueOut']
export type ScreeningState = components['schemas']['ScreeningStateOut']
export type ScreeningUpdate = components['schemas']['ScreeningCriteriaUpdate']
export type AcceptSuggestionsOut = components['schemas']['AcceptSuggestionsOut']

/** Where a chat lives: the reader's paper, or a workspace. */
export type ChatScope = { kind: 'paper' | 'workspace'; id: string }
const chatUrl = (scope: ChatScope) => `/api/${scope.kind === 'paper' ? 'papers' : 'workspaces'}/${scope.id}/chat`

/** The last `loc` segment of each FastAPI validation error that has one, deduplicated and in order. */
function invalidFields(errors: unknown[]): string[] {
  const fields = errors.flatMap((error) => {
    const loc = typeof error === 'object' && error !== null && 'loc' in error ? (error as { loc: unknown }).loc : null
    const field = Array.isArray(loc) ? loc.at(-1) : null
    return typeof field === 'string' ? [field] : []
  })
  return [...new Set(fields)]
}

/** A failed response's `detail` as readable text. FastAPI sends a string, or a list of validation errors. */
export async function errorDetail(response: Response): Promise<string> {
  const detail: unknown = await response.json().then((body) => body?.detail ?? response.statusText, () => response.statusText)
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const fields = invalidFields(detail)
    return fields.length > 0 ? `Check these fields: ${fields.join(', ')}.` : 'Some details are invalid.'
  }
  return JSON.stringify(detail)
}

/** A 409 that names the library paper already holding what was being added (or imported). */
export class AlreadyInLibraryError extends Error {
  readonly paperId: string

  constructor(message: string, paperId: string) {
    super(message)
    this.name = 'AlreadyInLibraryError'
    this.paperId = paperId
  }
}

/** The 410 a merged paper's id gets: it names the paper it was merged into. */
export class PaperMergedError extends Error {
  readonly keptId: string

  constructor(message: string, keptId: string) {
    super(message)
    this.name = 'PaperMergedError'
    this.keptId = keptId
  }
}

/** The 409 an Add gets when no free PDF was found: it carries what was tried, and the paper can be saved without one. */
export class NoFreePdfError extends Error {
  readonly tried: { url: string; outcome: string }[]
  readonly freeCopies: string[]

  constructor(message: string, tried: { url: string; outcome: string }[] = [], freeCopies: string[] = []) {
    super(message)
    this.name = 'NoFreePdfError'
    this.tried = tried
    this.freeCopies = freeCopies
  }
}

/** Any other failed response: `code` is the server's `detail` and `body` the rest of its JSON (path, limit, updated_at…). */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly body: Record<string, unknown>

  constructor(message: string, status: number, body: Record<string, unknown>) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = typeof body.detail === 'string' ? body.detail : message
    this.body = body
  }
}

/** True for a 409 ApiError whose server code is `code` (changed_since, already_undone, not_a_desk_event). */
export const isConflict = (e: unknown, code: string) => e instanceof ApiError && e.status === 409 && e.code === code

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) {
    const parsed: unknown = await response.clone().json().catch(() => null)
    const body: Record<string, unknown> = parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : {}
    const message = await errorDetail(response)
    // The typed errors keep the statuses they always had; any other failure is an ApiError.
    if (response.status === 409 || response.status === 410) {
      if (response.status === 410 && typeof body.kept_id === 'string') throw new PaperMergedError(message, body.kept_id)
      if (typeof body.paper_id === 'string') throw new AlreadyInLibraryError(message, body.paper_id)
      // no_free_pdf's detail is the server's sentence; its `tried` list is what marks it (main.py's DomainError handler)
      if (Array.isArray(body.tried))
        throw new NoFreePdfError(message, body.tried as NoFreePdfError['tried'], Array.isArray(body.free_copies) ? (body.free_copies as string[]) : [])
    }
    throw new ApiError(message, response.status, body)
  }
  return (response.status === 204 ? undefined : await response.json()) as T
}

export const citationsUrl = (workspaceId: string, format: string) =>
  `/api/workspaces/${encodeURIComponent(workspaceId)}/citations?format=${format}`

/** BibTeX plus each paper's PDF and notes, as Zotero imports it. */
export const zoteroZipUrl = (workspaceId: string) =>
  `/api/workspaces/${encodeURIComponent(workspaceId)}/citations.zip?format=bibtex&notes=true`

export const notesZipUrl = (workspaceId: string) => `/api/workspaces/${encodeURIComponent(workspaceId)}/notes.zip`

export type NotesImportResult = {
  created: number
  linked_papers: number
  unmatched_files: number
  skipped_duplicates: number
}

const manuscriptPath = (path: string) => path.split('/').map(encodeURIComponent).join('/')

const sendJson = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  listPapers: () => request<Paper[]>('/api/papers'),
  getPaper: (id: string) => request<Paper>(`/api/papers/${id}`),
  /** With a `workspaceId`, the new paper also joins that workspace. */
  uploadPaper: (file: File, workspaceId?: string) => {
    const form = new FormData()
    form.append('file', file)
    if (workspaceId) form.append('workspace_id', workspaceId)
    return request<Paper>('/api/papers', { method: 'POST', body: form })
  },
  /** Markdown files as unanchored notes, linked to library papers by the DOIs they contain. */
  importNotes: (files: File[]) => {
    const form = new FormData()
    for (const file of files) form.append('files', file)
    return request<NotesImportResult>('/api/notes/import', { method: 'POST', body: form })
  },
  updatePaper: (id: string, update: PaperUpdate) => request<Paper>(`/api/papers/${id}`, sendJson('PATCH', update)),
  /** The reader's own record (D118, D119): passes finished, keep/later/drop, or both. A field left out keeps its
   * value. 422 for an out-of-range pass, an unknown decision, or an empty body. `source` names where the change came
   * from (`reader` is the server's default, `library` the row menu). */
  setReading: (id: string, changes: ReadingIn, source?: 'reader' | 'library') => {
    const init = sendJson('PUT', changes)
    return request<Paper>(`/api/papers/${id}/reading`, source ? { ...init, headers: { ...init.headers, 'X-PaperLab-Source': source } } : init)
  },
  triageEvents: async (id: string) => (await request<{ events: TriageEvent[] }>(`/api/papers/${id}/triage-events`)).events,
  decideTriage: (paperId: string, body: TriageDecisionIn) => request<TriageDecision>(`/api/papers/${paperId}/triage-decisions`, sendJson('POST', body)),
  undoTriage: (eventId: string) => request<TriageDecision>(`/api/triage-events/${eventId}/undo`, { method: 'POST' }),
  triageSummary: (sessionId: string) => request<TriageSummary>(`/api/triage-summary?session_id=${encodeURIComponent(sessionId)}`),
  deletePaper: (id: string) => request<void>(`/api/papers/${id}`, { method: 'DELETE' }),
  /** Attaches `file` to a paper saved without a PDF; it then ingests. 409 already_has_pdf, 422 not_a_pdf / pdf_too_large. */
  uploadPaperPdf: (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<Paper>(`/api/papers/${id}/pdf`, { method: 'POST', body: form })
  },
  /** Looks for a free copy and attaches it. Rejects NoFreePdfError (what was tried), AlreadyInLibraryError, or already_has_pdf. */
  findPaperPdf: (id: string) => request<Paper>(`/api/papers/${id}/find-pdf`, { method: 'POST' }),
  reingestPaper: (id: string) => request<Paper>(`/api/papers/${id}/reingest`, { method: 'POST' }),
  paperFileUrl: (id: string) => `/api/papers/${id}/file`,
  /** Papers outside the library for a title, DOI, arXiv ID or OpenAlex ID, and a notice per source that failed. */
  searchPapers: (query: string) => request<SearchResult>(`/api/discovery/search?q=${encodeURIComponent(query)}`),
  similarPapers: (paperId: string) => request<Candidate[]>(`/api/papers/${paperId}/similar`),
  /** Downloads a found paper's free PDF into the library (or, with `saveWithoutPdf`, saves it without one); with a `workspaceId` it also joins that workspace. */
  addCandidate: (candidate: Candidate, workspaceId?: string, saveWithoutPdf = false) =>
    request<Paper>(
      '/api/discovery/add',
      sendJson('POST', { candidate, workspace_id: workspaceId ?? null, save_without_pdf: saveWithoutPdf }),
    ),
  listChunks: (paperId: string, page: number) => request<Chunk[]>(`/api/papers/${paperId}/chunks?page=${page}`),
  /** Every chunk of a paper, in reading order: the lens fades and jumps need their rects. */
  listAllChunks: (paperId: string) => request<Chunk[]>(`/api/papers/${paperId}/chunks`),
  /** Every section with its role, and every lens with its chunks. */
  paperSections: (paperId: string) => request<PaperSections>(`/api/papers/${paperId}/sections`),
  /** The reader's role for a heading (`role` null: back to the automatic one). Answers the sections again. */
  setSectionRole: (paperId: string, change: SectionRoleIn) =>
    request<PaperSections>(`/api/papers/${paperId}/section-roles`, sendJson('PUT', change)),
  listBriefs: (paperId: string) => request<Brief[]>(`/api/papers/${paperId}/briefs`),
  /** The raw response: on success its body is the brief's SSE stream, with chat's events. No body: `modelId` is the
   *  optional `?model_id=` query, and null asks the default. */
  generateBrief: (paperId: string, lens: LensId, modelId: string | null, signal?: AbortSignal) =>
    fetch(`/api/papers/${paperId}/briefs/${lens}${modelId ? `?model_id=${encodeURIComponent(modelId)}` : ''}`, {
      method: 'POST',
      signal,
    }),
  listNotes: (paperId: string) => request<Note[]>(`/api/papers/${paperId}/notes`),
  createNote: (note: NoteCreate) => request<Note>('/api/notes', sendJson('POST', note)),
  updateNote: (id: string, patch: NoteUpdate) => request<Note>(`/api/notes/${id}`, sendJson('PATCH', patch)),
  deleteNote: (id: string) => request<void>(`/api/notes/${id}`, { method: 'DELETE' }),
  /** Every note, newest first: all of them (`null`), a paper's (its id), or those on no paper (`'none'`). */
  listAllNotes: (paper: string | null) => request<Note[]>(paper === null ? '/api/notes' : `/api/notes?paper=${paper}`),
  /** Replaces a note's papers; a passage on a paper left out goes with it. */
  setNotePapers: (noteId: string, paperIds: string[]) =>
    request<Note>(`/api/notes/${noteId}/papers`, sendJson('PUT', { paper_ids: paperIds })),
  listWorkspaces: () => request<Workspace[]>('/api/workspaces'),
  createWorkspace: (name: string) => request<Workspace>('/api/workspaces', sendJson('POST', { name })),
  renameWorkspace: (id: string, name: string) =>
    request<Workspace>(`/api/workspaces/${id}`, sendJson('PATCH', { name })),
  deleteWorkspace: (id: string) => request<void>(`/api/workspaces/${id}`, { method: 'DELETE' }),
  listTags: (ws: string) => request<TagSummary[]>(`/api/workspaces/${ws}/tags`),
  paperTags: (ws: string) => request<Record<string, string[]>>(`/api/workspaces/${ws}/paper-tags`),
  tagsOfPaper: (paperId: string) => request<PaperTagGroup[]>(`/api/papers/${paperId}/tags`),
  applyTag: (ws: string, tag: string, paperIds: string[]) =>
    request<TagResult>(`/api/workspaces/${ws}/tags/apply`, sendJson('POST', { tag, paper_ids: paperIds })),
  removeTag: (ws: string, tag: string, paperIds: string[]) =>
    request<TagResult>(`/api/workspaces/${ws}/tags/remove`, sendJson('POST', { tag, paper_ids: paperIds })),
  renameTag: (ws: string, tagId: string, newName: string) =>
    request<TagRenamed>(`/api/workspaces/${ws}/tags/${tagId}`, sendJson('PATCH', { new_name: newName })),
  deleteTag: (ws: string, tagId: string) =>
    request<TagDeleted>(`/api/workspaces/${ws}/tags/${tagId}`, { method: 'DELETE' }),
  listWorkspacePapers: (id: string) => request<Paper[]>(`/api/workspaces/${id}/papers`),
  listWorkspaceNotes: (id: string) => request<Note[]>(`/api/workspaces/${id}/notes`),
  addToWorkspace: (workspaceId: string, paperId: string) =>
    request<void>(`/api/workspaces/${workspaceId}/papers/${paperId}`, { method: 'PUT' }),
  removeFromWorkspace: (workspaceId: string, paperId: string) =>
    request<void>(`/api/workspaces/${workspaceId}/papers/${paperId}`, { method: 'DELETE' }),
  listChat: (scope: ChatScope) => request<ChatAnswer[]>(chatUrl(scope)),
  promoteNote: (promote: PromoteRequest) => request<Note>('/api/notes/promote', sendJson('POST', promote)),
  /** Saves block `index` of a saved answer's suggested notes. A second save is refused with `already_saved`. */
  saveSuggestion: (outputId: string, index: number) =>
    request<Note>(`/api/chat/answers/${outputId}/notes`, sendJson('POST', { index })),
  /** One-click suggestions, not automatic notes: accept one through promoteNote, unchanged, using this
   * response's own output_id and a suggestion's chunk_id. */
  suggestNotes: (paperId: string) =>
    request<NoteSuggestionsOut>(`/api/papers/${paperId}/notes/suggest`, { method: 'POST' }),
  previewTable: (paperId: string, page: number, region: [number, number, number, number]) =>
    request<TablePreview>(`/api/papers/${paperId}/tables/preview`, sendJson('POST', { page, region })),
  addNumber: (paperId: string, number: NumberCreate) =>
    request<NumberAdded>(`/api/papers/${paperId}/numbers`, sendJson('POST', number)),
  numberCandidates: (text: string) => request<NumberCandidate[]>('/api/numbers/candidates', sendJson('POST', { text })),
  /** A paper's datasets, or every dataset without a paper id. */
  listDatasets: (paperId?: string) =>
    request<DatasetSummary[]>(paperId ? `/api/datasets?paper_id=${paperId}` : '/api/datasets'),
  getDataset: (id: string) => request<Dataset>(`/api/datasets/${id}`),
  createDataset: (dataset: DatasetCreate) => request<Dataset>('/api/datasets', sendJson('POST', dataset)),
  /** CSV from a file, or text pasted from a spreadsheet wrapped in a File. */
  importDataset: (file: File, name?: string) => {
    const form = new FormData()
    form.append('file', file)
    if (name) form.append('name', name)
    return request<Dataset>('/api/datasets/import', { method: 'POST', body: form })
  },
  renameDataset: (id: string, name: string) => request<Dataset>(`/api/datasets/${id}`, sendJson('PATCH', { name })),
  /** Without `force`, removing a column a chart uses fails with `used_by_charts`. */
  saveGrid: (id: string, grid: GridIn, force = false) =>
    request<Dataset>(`/api/datasets/${id}/grid${force ? '?force=true' : ''}`, sendJson('PUT', grid)),
  deleteDataset: (id: string, force = false) =>
    request<void>(`/api/datasets/${id}${force ? '?force=true' : ''}`, { method: 'DELETE' }),
  listCharts: () => request<ChartSummary[]>('/api/charts'),
  getChart: (id: string) => request<Chart>(`/api/charts/${id}`),
  createChart: (title: string, spec: ChartSpec) => request<Chart>('/api/charts', sendJson('POST', { title, spec })),
  updateChart: (id: string, patch: { title?: string; spec?: ChartSpec }) =>
    request<Chart>(`/api/charts/${id}`, sendJson('PATCH', patch)),
  duplicateChart: (id: string) => request<Chart>(`/api/charts/${id}/duplicate`, { method: 'POST' }),
  deleteChart: (id: string) => request<void>(`/api/charts/${id}`, { method: 'DELETE' }),
  /** The current cells a spec names, for a saved chart or an unsaved one in the builder. */
  resolveChart: (spec: ChartSpec) => request<ResolvedData>('/api/charts/resolve', sendJson('POST', { spec })),
  addChartToNote: (chartId: string) => request<Note>(`/api/charts/${chartId}/note`, { method: 'POST' }),
  attachChart: (noteId: string, chartId: string) =>
    request<void>(`/api/notes/${noteId}/charts/${chartId}`, { method: 'PUT' }),
  detachChart: (noteId: string, chartId: string) =>
    request<void>(`/api/notes/${noteId}/charts/${chartId}`, { method: 'DELETE' }),
  /**
   * The raw response: on success its body is the SSE stream that `useChatStream` reads. `modelId` null: the default.
   * `parentId`: the saved answer this question follows up (paper chat only); null for a question on its own.
   */
  askChat: (scope: ChatScope, question: string, modelId: string | null, parentId: string | null, signal?: AbortSignal) =>
    fetch(chatUrl(scope), { ...sendJson('POST', { question, model_id: modelId, parent_id: parentId }), signal }),
  listChatModels: () => request<ChatModel[]>('/api/llm/models'),
  listConnections: () => request<LLMConnection[]>('/api/llm/connections'),
  createConnection: (body: LLMConnectionCreate) => request<LLMConnection>('/api/llm/connections', sendJson('POST', body)),
  updateConnection: (id: string, body: LLMConnectionUpdate) =>
    request<LLMConnection>(`/api/llm/connections/${id}`, sendJson('PATCH', body)),
  deleteConnection: (id: string) => request<void>(`/api/llm/connections/${id}`, { method: 'DELETE' }),
  testConnection: (id: string) => request<ConnectionCheck>(`/api/llm/connections/${id}/test`, { method: 'POST' }),
  availableModels: (id: string) => request<AvailableModels>(`/api/llm/connections/${id}/available`),
  addModel: (connectionId: string, name: string) =>
    request<LLMModel>(`/api/llm/connections/${connectionId}/models`, sendJson('POST', { name })),
  removeModel: (id: string) => request<void>(`/api/llm/models/${id}`, { method: 'DELETE' }),
  setDefaultModel: (modelId: string) => request<LLMModel>('/api/llm/default', sendJson('PUT', { model_id: modelId })),
  /** The raw response: on success its body is the pull's SSE stream (progress…, then done or error). `addToChat`
   * false: Settings → Search's pull, which never lists the model in chat (`done.model` is null). */
  pullModel: (connectionId: string, name: string, signal?: AbortSignal, addToChat = true) =>
    fetch(`/api/llm/connections/${connectionId}/pull`, { ...sendJson('POST', { name, add_to_chat: addToChat }), signal }),
  /** `name` goes in the query: Ollama names can contain `/`. */
  deleteInstalledModel: (connectionId: string, name: string) =>
    request<void>(`/api/llm/connections/${connectionId}/installed?name=${encodeURIComponent(name)}`, { method: 'DELETE' }),
  embeddingStatus: () => request<EmbeddingStatus>('/api/embedding'),
  /** The raw response: on success its body is the download's SSE stream (progress…, then done or error). */
  downloadSearchModel: () => fetch('/api/embedding/model', { method: 'POST' }),
  /** `missingOnly`: Settings' Try again, which embeds only the papers not yet on the active source. */
  reindexLibrary: (missingOnly: boolean) =>
    request<{ papers: number }>('/api/embedding/reindex', sendJson('POST', { confirm: true, missing_only: missingOnly })),
  /** Probes the source, then saves it and queues the papers not yet on it: 202 {papers}, 200 for the source in use. */
  switchSearchSource: (body: SearchSourceIn) =>
    request<{ papers: number }>('/api/embedding/source', sendJson('PUT', body)),
  paperEvents: (paperId: string) => request<PaperEvent[]>(`/api/papers/${paperId}/events`),
  noteCounts: (ids: string[]) =>
    request<components['schemas']['NoteCountsOut']>('/api/papers/note-counts', sendJson('POST', { paper_ids: ids })).then((r) => r.counts),
  foundPdfs: () => request<FoundPdf[]>('/api/papers/found-pdfs'),
  markFoundPdfsSeen: (ids: string[]) => request<void>('/api/papers/found-pdfs/seen', sendJson('POST', { ids })),
  paperSources: () => request<PaperSources>('/api/paper-sources'),
  /** Only what `patch` holds changes: a key left out is kept, a null key is removed. */
  updatePaperSources: (patch: PaperSourcesUpdate) =>
    request<PaperSources>('/api/paper-sources', sendJson('PATCH', patch)),
  /** One direction of a paper's references, ranked for this library. */
  references: (paperId: string, direction: ReferencesDirection) =>
    request<References>(`/api/papers/${paperId}/references?direction=${direction}`),
  /** Queues a fetch of both directions; a second call while already fetching is a no-op. */
  refreshReferences: (paperId: string) =>
    request<RefreshOut>(`/api/papers/${paperId}/references/refresh`, { method: 'POST' }),
  /** Downloads a reference's free PDF into the library; with a `workspaceId` it also joins that workspace. */
  importReference: (refId: string, workspaceId?: string) =>
    request<Paper>(`/api/references/${refId}/import`, sendJson('POST', { workspace_id: workspaceId ?? null })),
  /** The whole library's, or one workspace's, To read list and shared references (D121, D166). 404 unknown workspace. */
  referencePage: (workspaceId: string | null) =>
    request<ReferencePage>(workspaceId ? `/api/references?workspace=${workspaceId}` : '/api/references'),
  /** Marks a reference To read; a second call keeps the first time. 404 unknown reference. */
  queueReference: (refId: string) => request<{ queued_at: string | null }>(`/api/references/${refId}/queue`, sendJson('PUT', undefined)),
  /** Takes a reference off To read; harmless when it isn't on it. 404 unknown reference. */
  unqueueReference: (refId: string) => request<{ queued_at: string | null }>(`/api/references/${refId}/queue`, { method: 'DELETE' }),
  /** The folder `docker compose up` ran in, to prefill Connect Claude; null outside Compose. */
  mcpSetup: () => request<McpSetup>('/api/mcp/setup'),
  /** Starts the MCP server as a client would and reads the library through it. Takes up to 30 s. */
  checkMcpServer: () => request<McpCheck>('/api/mcp/check', { method: 'POST' }),
  /** Whether the first-run setup is done: while it isn't, the app opens #/setup on start. */
  setup: () => request<SetupState>('/api/setup'),
  /** Finish and Skip send true; false is for tests. */
  setSetupDone: (done: boolean) => request<SetupState>('/api/setup', sendJson('PUT', { done })),
  /** Every library paper and the links between them, or one workspace's. Capped at 2000 links. */
  libraryGraph: (workspaceId: string | null) =>
    request<LibraryGraph>(workspaceId ? `/api/graph?workspace=${workspaceId}` : '/api/graph'),
  createPaperLink: (fromPaper: string, toPaper: string, label: string) =>
    request<PaperLinkOut>('/api/links', sendJson('POST', { from_paper: fromPaper, to_paper: toPaper, label })),
  renamePaperLink: (id: string, label: string) =>
    request<PaperLinkOut>(`/api/links/${id}`, sendJson('PATCH', { label })),
  deletePaperLink: (id: string) => request<void>(`/api/links/${id}`, { method: 'DELETE' }),
  startSearchRun: (workspaceId: string, body: SearchRunCreate) =>
    request<SearchRun>(`/api/workspaces/${workspaceId}/search/runs`, sendJson('POST', body)),
  stopSearchRun: (workspaceId: string, runId: string) =>
    request<SearchRun>(`/api/workspaces/${workspaceId}/search/runs/${runId}/stop`, { method: 'POST' }),
  continueSearchRun: (workspaceId: string, runId: string) =>
    request<SearchRun>(`/api/workspaces/${workspaceId}/search/runs/${runId}`, { method: 'POST' }),
  getEvidenceCard: (paperId: string) => request<EvidenceCard>(`/api/papers/${paperId}/evidence-card`),
  generateEvidenceCard: (paperId: string, regenerate: boolean, confirm: boolean) =>
    request<EvidenceCard[]>(`/api/papers/${paperId}/evidence-card`, sendJson('POST', { regenerate, confirm })),
  editEvidenceCard: (paperId: string, changes: EvidenceChange[]) =>
    request<EvidenceCard>(`/api/papers/${paperId}/evidence-card`, sendJson('PATCH', { changes })),
  listManuscripts: (workspaceId: string | null) =>
    request<Manuscript[]>(workspaceId ? `/api/workspaces/${workspaceId}/manuscripts` : '/api/manuscripts?orphans=true'),
  listManuscriptTemplates: () => request<ManuscriptTemplate[]>('/api/templates/manuscripts'),
  getManuscript: (id: string) => request<ManuscriptDetail>(`/api/manuscripts/${id}`),
  createManuscript: (body: ManuscriptCreate) => request<ManuscriptDetail>('/api/manuscripts', sendJson('POST', body)),
  /** An Overleaf zip as a new manuscript; `skipped` names the members PaperLab can't hold. */
  importManuscript: (file: File, workspaceId?: string | null) => {
    const form = new FormData()
    form.append('file', file)
    if (workspaceId) form.append('workspace_id', workspaceId)
    return request<ManuscriptImport>('/api/manuscripts/import', { method: 'POST', body: form })
  },
  updateManuscript: (id: string, patch: ManuscriptPatch) =>
    request<ManuscriptDetail>(`/api/manuscripts/${id}`, sendJson('PATCH', patch)),
  deleteManuscript: (id: string) => request<void>(`/api/manuscripts/${id}`, { method: 'DELETE' }),
  getManuscriptFile: (id: string, path: string) =>
    request<ManuscriptFileText>(`/api/manuscripts/${id}/files/${manuscriptPath(path)}`),
  /** `base` is the updated_at the editor last saw; null for a new file. A stale one is a 409 ApiError (file_changed). */
  /** A figure or a text file from the computer, at `path` (a binary overwrites; a text file must be new). */
  uploadManuscriptFile: (id: string, path: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    form.append('path', path)
    return request<ManuscriptFile>(`/api/manuscripts/${id}/uploads`, { method: 'POST', body: form })
  },
  renameManuscriptFile: (id: string, path: string, newPath: string) =>
    request<ManuscriptFile>(`/api/manuscripts/${id}/files/${manuscriptPath(path)}/rename`, sendJson('POST', { new_path: newPath })),
  deleteManuscriptFile: (id: string, path: string) =>
    request<void>(`/api/manuscripts/${id}/files/${manuscriptPath(path)}`, { method: 'DELETE' }),
  manuscriptPapers: (id: string) => request<CitablePaper[]>(`/api/manuscripts/${id}/papers`),
  missingKeys: (id: string) => request<MissingKey[]>(`/api/manuscripts/${id}/missing-keys`),
  startReview: (id: string, body: ReviewStart) =>
    request<ReviewRun>(`/api/manuscripts/${id}/review`, sendJson('POST', body)),
  reviewState: (id: string, file: string) =>
    request<ReviewState>(`/api/manuscripts/${id}/review?file=${encodeURIComponent(file)}`),
  cancelReview: (id: string, runId: string) =>
    request<ReviewRun>(`/api/manuscripts/${id}/review/${runId}/cancel`, { method: 'POST' }),
  locateSentences: (id: string, text: string) =>
    request<{ sentences: ReviewSentence[] }>(`/api/manuscripts/${id}/review/locate`, sendJson('POST', { text })),
  dismissClaim: (id: string, hash: string) =>
    request<void>(`/api/manuscripts/${id}/review/dismissals/${hash}`, { method: 'PUT' }),
  restoreClaim: (id: string, hash: string) =>
    request<void>(`/api/manuscripts/${id}/review/dismissals/${hash}`, { method: 'DELETE' }),
  startSectionReview: (id: string, body: SectionReviewStart) =>
    request<SectionReview>(`/api/manuscripts/${id}/section-review`, sendJson('POST', body)),
  sectionReviews: (id: string, file: string) =>
    request<{ reviews: SectionReview[] }>(`/api/manuscripts/${id}/section-review?file=${encodeURIComponent(file)}`),
  cancelSectionReview: (id: string, reviewId: string) =>
    request<SectionReview>(`/api/manuscripts/${id}/section-review/${reviewId}/cancel`, { method: 'POST' }),
  createDiagram: (id: string, body: DiagramStart) =>
    request<Diagram>(`/api/manuscripts/${id}/diagrams`, sendJson('POST', body)),
  diagram: (id: string, diagramId: string) => request<Diagram>(`/api/manuscripts/${id}/diagrams/${diagramId}`),
  setDiagramCode: (id: string, diagramId: string, code: string) =>
    request<Diagram>(`/api/manuscripts/${id}/diagrams/${diagramId}/code`, sendJson('PUT', { code })),
  cancelDiagram: (id: string, diagramId: string) =>
    request<Diagram>(`/api/manuscripts/${id}/diagrams/${diagramId}/cancel`, { method: 'POST' }),
  deleteDiagram: (id: string, diagramId: string) =>
    request<void>(`/api/manuscripts/${id}/diagrams/${diagramId}`, { method: 'DELETE' }),
  /** `stamp` (the row's updated_at) is in the URL so a new preview is a new URL and pdf.js fetches it again. */
  manuscriptDiagramPdfUrl: (id: string, diagramId: string, stamp: string) =>
    `/api/manuscripts/${id}/diagrams/${diagramId}/pdf?v=${encodeURIComponent(stamp)}`,
  locateSections: (id: string, file: string, text: string) =>
    request<{ sections: SectionSpan[] }>(`/api/manuscripts/${id}/section-review/locate`, sendJson('POST', { file, text })),
  pinPaper: (id: string, paperId: string) => request<{ key: string }>(`/api/manuscripts/${id}/papers/${paperId}/pin`, { method: 'POST' }),
  rankPapers: (id: string, text: string) =>
    request<{ paper_ids: string[] }>(`/api/manuscripts/${id}/papers/rank`, sendJson('POST', { text })),
  findEvidence: (id: string, sentence: string, confirmRemote = false) =>
    request<EvidenceFound>(`/api/manuscripts/${id}/evidence`, sendJson('POST', { sentence, confirm_remote: confirmRemote })),
  evidenceRows: (id: string, hash: string) => request<EvidenceRow[]>(`/api/manuscripts/${id}/evidence/${hash}`),
  addSection: (id: string, title: string, after: string | null) =>
    request<{ path: string }>(`/api/manuscripts/${id}/sections`, sendJson('POST', { title, after })),
  splitSections: (id: string) => request<{ paths: string[] }>(`/api/manuscripts/${id}/sections/split`, { method: 'POST' }),
  retitleSection: (id: string, path: string, title: string) =>
    request<{ path: string }>(`/api/manuscripts/${id}/sections/${manuscriptPath(path)}/retitle`, sendJson('POST', { title })),
  moveSection: (id: string, path: string, to: number) =>
    request<void>(`/api/manuscripts/${id}/sections/${manuscriptPath(path)}/move`, sendJson('POST', { to })),
  deleteSection: (id: string, path: string) =>
    request<void>(`/api/manuscripts/${id}/sections/${manuscriptPath(path)}`, { method: 'DELETE' }),
  saveManuscriptFile: (id: string, path: string, text: string, base: string | null) =>
    request<ManuscriptFile>(`/api/manuscripts/${id}/files/${manuscriptPath(path)}`, sendJson('PUT', { text, base_updated_at: base })),
  compileManuscript: (id: string) => request<{ state: string }>(`/api/manuscripts/${id}/compile`, { method: 'POST' }),
  /** `compiledAt` is in the URL so a new compile is a new URL and pdf.js fetches it again. */
  manuscriptPdfUrl: (id: string, compiledAt?: string | null) =>
    `/api/manuscripts/${id}/pdf${compiledAt ? `?v=${encodeURIComponent(compiledAt)}` : ''}`,
  /** Where a source line lands in the PDF. Rejects 404 no_sync when there is no index or no match. */
  syncForward: (id: string, file: string, line: number) =>
    request<{ page: number; x: number; y: number }>(
      `/api/manuscripts/${id}/synctex/forward?file=${encodeURIComponent(file)}&line=${line}`),
  /** Which source line a PDF spot comes from (page 1-based, x/y in points from the top-left). 404 no_sync too. */
  syncInverse: (id: string, page: number, x: number, y: number) =>
    request<{ file: string; line: number }>(`/api/manuscripts/${id}/synctex/inverse?page=${page}&x=${x}&y=${y}`),
  /** `pdf: false`: the LaTeX source and paperlab.bib alone, without the compiled PDF. */
  manuscriptExportUrl: (id: string, { pdf = true }: { pdf?: boolean } = {}) =>
    `/api/manuscripts/${id}/export.zip${pdf ? '' : '?pdf=false'}`,
  listManuscriptSnapshots: (id: string) => request<ManuscriptSnapshot[]>(`/api/manuscripts/${id}/snapshots`),
  restoreManuscriptSnapshot: (id: string, snapshotId: string) =>
    request<void>(`/api/manuscripts/${id}/snapshots/${snapshotId}/restore`, { method: 'POST' }),
  listEvidenceCards: (workspaceId: string) =>
    request<EvidenceCardRow[]>(`/api/workspaces/${workspaceId}/evidence-cards`),
  generateEvidenceCards: (workspaceId: string) =>
    request<EvidenceCard[]>(`/api/workspaces/${workspaceId}/evidence-cards`, sendJson('POST', {})),
  evidenceCardsCsvUrl: (workspaceId: string) => `/api/workspaces/${workspaceId}/evidence-cards.csv`,
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
  listSearchRuns: (workspaceId: string, limit = 20) =>
    request<SearchRunSummary[]>(`/api/workspaces/${workspaceId}/search/runs?limit=${limit}`),
  getSearchRun: (workspaceId: string, runId: string) =>
    request<SearchRun>(`/api/workspaces/${workspaceId}/search/runs/${runId}`),
  listSearchHits: (
    workspaceId: string,
    params: {
      after?: string; limit?: number; stage1_status?: string; acquisition_status?: string; sort?: 'ai'; min_relevance?: number
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
  rankedSearchHits: (workspaceId: string, limit = 200) =>
    request<RankedHits>(`/api/workspaces/${workspaceId}/search/hits/ranked?limit=${limit}`),
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
  setEligibility: (workspaceId: string, paperId: string, runId: string, body: EligibilityUpdate) =>
    request<EligibilityOut>(
      `/api/workspaces/${workspaceId}/papers/${paperId}/eligibility?run=${runId}`,
      sendJson('PATCH', body),
    ),
  /** What importing `file` would do. Nothing is written. */
  /** With fetching on (the API's default): only `would_fetch` and `disclosure` depend on it, and none on the target. */
  previewImport: (file: File, saveWithoutPdf = true) => {
    const form = new FormData()
    form.append('file', file)
    form.append('save_without_pdf', String(saveWithoutPdf))
    return request<ImportPreview>('/api/citations/import/preview', { method: 'POST', body: form })
  },
  /** Starts an import: 200 gives the result now, 202 a job id to poll (same body shape either way). */
  startImport: (file: File, target: { workspaceId?: string; newWorkspaceName?: string }, fetchFreePdfs: boolean, saveWithoutPdf = true) => {
    const form = new FormData()
    form.append('file', file)
    if (target.workspaceId) form.append('workspace_id', target.workspaceId)
    if (target.newWorkspaceName) form.append('new_workspace_name', target.newWorkspaceName)
    form.append('fetch_free_pdfs', String(fetchFreePdfs))
    form.append('save_without_pdf', String(saveWithoutPdf))
    return request<ImportProgress>('/api/citations/import', { method: 'POST', body: form })
  },
  importProgress: (jobId: string) => request<ImportProgress>(`/api/citations/import/${encodeURIComponent(jobId)}`),
  /** The chosen papers as one citations file (with `workspaceId`, that workspace's tags go in the keywords); resolves to its bytes and the server's file name. */
  exportSelection: async (paperIds: string[], format: 'bibtex' | 'ris', workspaceId?: string): Promise<{ blob: Blob; filename: string }> => {
    const response = await fetch('/api/citations/export', sendJson('POST', { paper_ids: paperIds, format, workspace_id: workspaceId }))
    if (!response.ok) throw new Error(await errorDetail(response))
    const name = /filename="([^"]+)"/.exec(response.headers.get('Content-Disposition') ?? '')?.[1]
    return { blob: await response.blob(), filename: name ?? `citations.${format === 'ris' ? 'ris' : 'bib'}` }
  },
  /** A workspace's citations as text (the apa-html preview and the plain apa to copy). Downloads use the URL directly. */
  citationsText: async (workspaceId: string, format: string): Promise<string> => {
    const response = await fetch(citationsUrl(workspaceId, format))
    if (!response.ok) throw new Error(await errorDetail(response))
    return response.text()
  },
  /** `runs`: a single run id, or `'all'` to combine every run in the workspace. */
  prismaExport: (workspaceId: string, runs: string) =>
    request<PrismaExportOut>(`/api/workspaces/${workspaceId}/search/prisma?runs=${runs}`),
  readingContext: (paperId: string) => request<ReadingContextList>(`/api/papers/${paperId}/reading-context`),
  readingQueue: (workspaceId: string, runId: string) =>
    request<ReadingQueue>(`/api/workspaces/${workspaceId}/search/reading-queue?run=${runId}`),
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

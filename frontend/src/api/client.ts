import type { components } from './schema'

export type Paper = components['schemas']['PaperOut']
export type PaperUpdate = components['schemas']['PaperUpdate']
export type Chunk = components['schemas']['ChunkOut']
export type Note = components['schemas']['NoteOut']
export type NoteCreate = components['schemas']['NoteCreate']
export type NoteUpdate = components['schemas']['NoteUpdate']
export type ChatSource = components['schemas']['ChatSource']
export type NoteSource = components['schemas']['NoteSource']
export type ChatAnswer = components['schemas']['ChatAnswer']
// Prefixed: the DOM already has a global `ErrorEvent`.
export type ChatSourcesEvent = components['schemas']['SourcesEvent']
export type ChatTokenEvent = components['schemas']['TokenEvent']
export type ChatDoneEvent = components['schemas']['DoneEvent']
export type ChatErrorEvent = components['schemas']['ErrorEvent']
export type PromoteRequest = components['schemas']['PromoteRequest']
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
export type Candidate = components['schemas']['CandidateOut']
export type PaperSources = components['schemas']['PaperSourcesOut']
export type PaperSource = components['schemas']['PaperSourceOut']
export type PaperSourceId = PaperSource['id']
export type PaperSourcesUpdate = components['schemas']['PaperSourcesUpdate']

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
  const detail: unknown = await response.json().then((body) => body.detail, () => response.statusText)
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const fields = invalidFields(detail)
    return fields.length > 0 ? `Check these fields: ${fields.join(', ')}.` : 'Some details are invalid.'
  }
  return JSON.stringify(detail)
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) throw new Error(await errorDetail(response))
  return (response.status === 204 ? undefined : await response.json()) as T
}

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
  updatePaper: (id: string, update: PaperUpdate) => request<Paper>(`/api/papers/${id}`, sendJson('PATCH', update)),
  deletePaper: (id: string) => request<void>(`/api/papers/${id}`, { method: 'DELETE' }),
  reingestPaper: (id: string) => request<Paper>(`/api/papers/${id}/reingest`, { method: 'POST' }),
  paperFileUrl: (id: string) => `/api/papers/${id}/file`,
  /** Papers outside the library for a title, DOI, arXiv ID or OpenAlex ID. */
  searchPapers: (query: string) => request<Candidate[]>(`/api/discovery/search?q=${encodeURIComponent(query)}`),
  similarPapers: (paperId: string) => request<Candidate[]>(`/api/papers/${paperId}/similar`),
  /** Downloads a found paper's free PDF into the library; with a `workspaceId` it also joins that workspace. */
  addCandidate: (candidate: Candidate, workspaceId?: string) =>
    request<Paper>('/api/discovery/add', sendJson('POST', { candidate, workspace_id: workspaceId ?? null })),
  listChunks: (paperId: string, page: number) => request<Chunk[]>(`/api/papers/${paperId}/chunks?page=${page}`),
  listNotes: (paperId: string) => request<Note[]>(`/api/papers/${paperId}/notes`),
  createNote: (note: NoteCreate) => request<Note>('/api/notes', sendJson('POST', note)),
  updateNote: (id: string, patch: NoteUpdate) => request<Note>(`/api/notes/${id}`, sendJson('PATCH', patch)),
  deleteNote: (id: string) => request<void>(`/api/notes/${id}`, { method: 'DELETE' }),
  listWorkspaces: () => request<Workspace[]>('/api/workspaces'),
  createWorkspace: (name: string) => request<Workspace>('/api/workspaces', sendJson('POST', { name })),
  renameWorkspace: (id: string, name: string) =>
    request<Workspace>(`/api/workspaces/${id}`, sendJson('PATCH', { name })),
  deleteWorkspace: (id: string) => request<void>(`/api/workspaces/${id}`, { method: 'DELETE' }),
  listWorkspacePapers: (id: string) => request<Paper[]>(`/api/workspaces/${id}/papers`),
  listWorkspaceNotes: (id: string) => request<Note[]>(`/api/workspaces/${id}/notes`),
  addToWorkspace: (workspaceId: string, paperId: string) =>
    request<void>(`/api/workspaces/${workspaceId}/papers/${paperId}`, { method: 'PUT' }),
  removeFromWorkspace: (workspaceId: string, paperId: string) =>
    request<void>(`/api/workspaces/${workspaceId}/papers/${paperId}`, { method: 'DELETE' }),
  listChat: (scope: ChatScope) => request<ChatAnswer[]>(chatUrl(scope)),
  promoteNote: (promote: PromoteRequest) => request<Note>('/api/notes/promote', sendJson('POST', promote)),
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
  /** The raw response: on success its body is the pull's SSE stream (progress…, then done or error). */
  pullModel: (connectionId: string, name: string, signal?: AbortSignal) =>
    fetch(`/api/llm/connections/${connectionId}/pull`, { ...sendJson('POST', { name }), signal }),
  /** `name` goes in the query: Ollama names can contain `/`. */
  deleteInstalledModel: (connectionId: string, name: string) =>
    request<void>(`/api/llm/connections/${connectionId}/installed?name=${encodeURIComponent(name)}`, { method: 'DELETE' }),
  embeddingStatus: () => request<EmbeddingStatus>('/api/embedding'),
  reindexLibrary: () => request<{ papers: number }>('/api/embedding/reindex', sendJson('POST', { confirm: true })),
  paperSources: () => request<PaperSources>('/api/paper-sources'),
  /** Only what `patch` holds changes: a key left out is kept, a null key is removed. */
  updatePaperSources: (patch: PaperSourcesUpdate) =>
    request<PaperSources>('/api/paper-sources', sendJson('PATCH', patch)),
}

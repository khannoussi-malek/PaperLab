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
  /** The raw response: on success its body is the SSE stream that `useChatStream` reads. */
  askChat: (scope: ChatScope, question: string) => fetch(chatUrl(scope), sendJson('POST', { question })),
}

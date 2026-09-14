import type { components } from './schema'

export type Paper = components['schemas']['PaperOut']
export type Chunk = components['schemas']['ChunkOut']
export type Note = components['schemas']['NoteOut']
export type NoteCreate = components['schemas']['NoteCreate']
export type NoteUpdate = components['schemas']['NoteUpdate']
export type ChatSource = components['schemas']['ChatSource']
export type ChatAnswer = components['schemas']['ChatAnswer']
// Prefixed: the DOM already has a global `ErrorEvent`.
export type ChatSourcesEvent = components['schemas']['SourcesEvent']
export type ChatTokenEvent = components['schemas']['TokenEvent']
export type ChatDoneEvent = components['schemas']['DoneEvent']
export type ChatErrorEvent = components['schemas']['ErrorEvent']
export type PromoteRequest = components['schemas']['PromoteRequest']

/** A failed response's `detail` as text. FastAPI sends a string, or a list of validation errors. */
export async function errorDetail(response: Response): Promise<string> {
  const detail: unknown = await response.json().then((body) => body.detail, () => response.statusText)
  return typeof detail === 'string' ? detail : JSON.stringify(detail)
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
  uploadPaper: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<Paper>('/api/papers', { method: 'POST', body: form })
  },
  deletePaper: (id: string) => request<void>(`/api/papers/${id}`, { method: 'DELETE' }),
  reingestPaper: (id: string) => request<Paper>(`/api/papers/${id}/reingest`, { method: 'POST' }),
  paperFileUrl: (id: string) => `/api/papers/${id}/file`,
  listNotes: (paperId: string) => request<Note[]>(`/api/papers/${paperId}/notes`),
  createNote: (note: NoteCreate) => request<Note>('/api/notes', sendJson('POST', note)),
  updateNote: (id: string, patch: NoteUpdate) => request<Note>(`/api/notes/${id}`, sendJson('PATCH', patch)),
  deleteNote: (id: string) => request<void>(`/api/notes/${id}`, { method: 'DELETE' }),
  listChat: (paperId: string) => request<ChatAnswer[]>(`/api/papers/${paperId}/chat`),
  promoteNote: (promote: PromoteRequest) => request<Note>('/api/notes/promote', sendJson('POST', promote)),
  /** The raw response: on success its body is the SSE stream that `useChatStream` reads. */
  askChat: (paperId: string, question: string) =>
    fetch(`/api/papers/${paperId}/chat`, sendJson('POST', { question })),
}

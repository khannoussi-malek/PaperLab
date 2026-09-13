import type { components } from './schema'

export type Paper = components['schemas']['PaperOut']
export type Chunk = components['schemas']['ChunkOut']
export type Note = components['schemas']['NoteOut']
export type NoteCreate = components['schemas']['NoteCreate']

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) {
    const detail: unknown = await response.json().then((body) => body.detail, () => response.statusText)
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
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
  paperFileUrl: (id: string) => `/api/papers/${id}/file`,
  listNotes: (paperId: string) => request<Note[]>(`/api/papers/${paperId}/notes`),
  createNote: (note: NoteCreate) => request<Note>('/api/notes', sendJson('POST', note)),
  updateNote: (id: string, body: string) => request<Note>(`/api/notes/${id}`, sendJson('PATCH', { body })),
  deleteNote: (id: string) => request<void>(`/api/notes/${id}`, { method: 'DELETE' }),
}

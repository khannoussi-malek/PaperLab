import { request, sendJson } from '../http'
import type { AnswerProvenance, Check, FigureNoteCreate, McpNoteProvenance, Note, NoteCreate, NotesImportResult, NoteSuggestionsOut, NoteUpdate, PromoteRequest } from '@/entities'
import type { components } from '@/entities/schema'

export const notesApi = {
  /** Markdown files as unanchored notes, linked to library papers by the DOIs they contain. */
  importNotes: (files: File[]) => {
    const form = new FormData()
    for (const file of files) form.append('files', file)
    return request<NotesImportResult>('/api/notes/import', { method: 'POST', body: form })
  },
  listChecks: (paperId: string) => request<Check[]>(`/api/papers/${paperId}/checks`),
  /** The raw response: on success its body is the check's SSE stream, whose tokens are each one kept line. A remote
   *  model needs `confirmRemote`; null `modelId` asks the default. */
  checkNote: (noteId: string, modelId: string | null, confirmRemote: boolean, signal?: AbortSignal) =>
    fetch(`/api/notes/${noteId}/check`, {
      ...sendJson('POST', { model_id: modelId, confirm_remote: confirmRemote }),
      signal,
    }),
  listNotes: (paperId: string) => request<Note[]>(`/api/papers/${paperId}/notes`),
  createNote: (note: NoteCreate) => request<Note>('/api/notes', sendJson('POST', note)),
  createFigureNote: (note: FigureNoteCreate) => request<Note>('/api/notes/figure', sendJson('POST', note)),
  updateNote: (id: string, patch: NoteUpdate) => request<Note>(`/api/notes/${id}`, sendJson('PATCH', patch)),
  deleteNote: (id: string) => request<void>(`/api/notes/${id}`, { method: 'DELETE' }),
  /** Every note, newest first: all of them (`null`), a paper's (its id), or those on no paper (`'none'`). */
  listAllNotes: (paper: string | null) => request<Note[]>(paper === null ? '/api/notes' : `/api/notes?paper=${paper}`),
  /** Replaces a note's papers; a passage on a paper left out goes with it. */
  setNotePapers: (noteId: string, paperIds: string[]) =>
    request<Note>(`/api/notes/${noteId}/papers`, sendJson('PUT', { paper_ids: paperIds })),
  /** How an AI note was made. A note an MCP client added says only where it came from. */
  noteProvenance: (noteId: string) => request<AnswerProvenance | McpNoteProvenance>(`/api/notes/${noteId}/provenance`),
  promoteNote: (promote: PromoteRequest) => request<Note>('/api/notes/promote', sendJson('POST', promote)),
  /** One-click suggestions, not automatic notes: accept one through promoteNote, unchanged, using this
   * response's own output_id and a suggestion's chunk_id. */
  suggestNotes: (paperId: string) =>
    request<NoteSuggestionsOut>(`/api/papers/${paperId}/notes/suggest`, { method: 'POST' }),
  noteCounts: (ids: string[]) =>
    request<components['schemas']['NoteCountsOut']>('/api/papers/note-counts', sendJson('POST', { paper_ids: ids })).then((r) => r.counts),
  attachChart: (noteId: string, chartId: string) =>
    request<void>(`/api/notes/${noteId}/charts/${chartId}`, { method: 'PUT' }),
  detachChart: (noteId: string, chartId: string) =>
    request<void>(`/api/notes/${noteId}/charts/${chartId}`, { method: 'DELETE' }),
}

import { keepPreviousData, QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/services/api'
import type { FigureNoteCreate, NoteCounts, NoteCreate, NoteUpdate, PromoteRequest } from '@/entities'
import { keys } from './core'

/** Every list that shows notes: the Notes page's, a paper's, a paper's checks (they go stale with a note), every workspace query (its Notes tab and count), and
 * paper chat's history (a saved suggestion's card lives there too). */
export const isNotesList = (queryKey: readonly unknown[]) =>
  queryKey[0] === 'notes' || queryKey[0] === 'noteCounts' || queryKey[2] === 'notes' || queryKey[2] === 'chat' || queryKey[2] === 'checks' || queryKey[0] === 'workspaces'

/** Refetches every list that shows notes: after a note is saved, edited, moved between papers or deleted, or a chart
 * it shows changes. */
export const refreshNotes = (client: QueryClient) =>
  client.invalidateQueries({ predicate: (query) => isNotesList(query.queryKey) })

export const useNotes = (paperId: string) =>
  useQuery({ queryKey: keys.notes(paperId), queryFn: () => api.listNotes(paperId) })

/** The Notes page: every note, one paper's, or those on no paper, newest first. */
export const useAllNotes = (paper: string | null) =>
  useQuery({ queryKey: keys.allNotes(paper), queryFn: () => api.listAllNotes(paper) })

/** Generates note suggestions for one paper (P1 of this feature: cards to accept or dismiss, never saved on
 * their own). No cache to invalidate on success — nothing is written yet, the caller just renders the result;
 * accepting one goes through usePromoteNote, unchanged, which already invalidates the note lists that need it. */
export function useSuggestNotes(paperId: string) {
  return useMutation({ mutationFn: () => api.suggestNotes(paperId) })
}

/** Saves part of a chat answer as an AI note. Resolves once the lists that show it have refetched and include it. */
export function usePromoteNote() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (promote: PromoteRequest) => api.promoteNote(promote),
    // A workspace answer can anchor the note on several papers, and workspace Notes tabs and counts list it too.
    onSuccess: () => refreshNotes(client),
  })
}

/** How an AI note was made; read only when its disclosure opens. */
export const useNoteProvenance = (noteId: string, enabled: boolean) =>
  useQuery({ queryKey: ['notes', noteId, 'provenance'] as const, queryFn: () => api.noteProvenance(noteId), enabled })

/** Create, edit, recolour and delete a note: any of them can change what every notes list shows (reader, workspace
 * Notes tabs and counts, the Notes page). */
export function useNoteMutations() {
  const client = useQueryClient()
  const onSuccess = () => refreshNotes(client)
  return {
    create: useMutation({ mutationFn: (note: NoteCreate) => api.createNote(note), onSuccess }),
    createFigure: useMutation({ mutationFn: (note: FigureNoteCreate) => api.createFigureNote(note), onSuccess }),
    update: useMutation({
      mutationFn: ({ id, ...patch }: { id: string } & NoteUpdate) => api.updateNote(id, patch),
      onSuccess,
    }),
    remove: useMutation({ mutationFn: api.deleteNote, onSuccess }),
  }
}

/** Imports Markdown files as notes: every notes list (and the graph's noted papers) can change. */
export function useImportNotes() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (files: File[]) => api.importNotes(files),
    onSuccess: () => Promise.all([refreshNotes(client), client.invalidateQueries({ queryKey: keys.graph })]),
  })
}

/** Replaces a note's papers. Every notes list can change (a paper's, a workspace's, the Notes page), and the graph's
 * noted papers and "noted together" links with them. Resolves once the lists shown have refetched. */
export function useSetNotePapers() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ noteId, paperIds }: { noteId: string; paperIds: string[] }) => api.setNotePapers(noteId, paperIds),
    onSuccess: () => Promise.all([refreshNotes(client), client.invalidateQueries({ queryKey: keys.graph })]),
  })
}

/** The API takes at most this many paper ids per request. */
export const NOTE_COUNTS_MAX_IDS = 2000
export async function noteCountsChunked(ids: string[]) {
  const chunks: string[][] = []
  for (let i = 0; i < ids.length; i += NOTE_COUNTS_MAX_IDS) chunks.push(ids.slice(i, i + NOTE_COUNTS_MAX_IDS))
  return Object.assign({}, ...(await Promise.all(chunks.map((c) => api.noteCounts(c))))) as NoteCounts
}

/** Notes, highlights and AI notes for many papers (one request per 2000); keyed by the sorted ids. */
export const useNoteCounts = (ids: string[]) => {
  const sorted = [...ids].sort()
  return useQuery({ queryKey: keys.noteCounts(sorted), queryFn: () => noteCountsChunked(sorted), enabled: sorted.length > 0, placeholderData: keepPreviousData })
}

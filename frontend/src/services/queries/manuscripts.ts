import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef } from 'react'
import { api, ApiError } from '@/services/api'
import type { ManuscriptCreate, ManuscriptPatch, SaveResult } from '@/entities'
import { keys } from './core'

const COMPILE_POLL_MS = 1000

/** A workspace's manuscripts, or (null) those with no workspace. */
export const useManuscripts = (workspaceId: string | null) =>
  useQuery({ queryKey: keys.manuscriptList(workspaceId), queryFn: () => api.listManuscripts(workspaceId) })

export const useManuscriptTemplates = () =>
  useQuery({ queryKey: ['manuscripts', 'templates'], queryFn: api.listManuscriptTemplates, staleTime: Infinity })
export const useReportingGuidelines = () =>
  useQuery({ queryKey: ['reporting-guidelines'], queryFn: api.listReportingGuidelines, staleTime: Infinity })

/** Poll while compiling or while another pass is asked for; stop on error so a failing server isn't hammered. */
export const manuscriptPollInterval = (data: { compile_status: string; compile_requested?: boolean } | undefined, failed: boolean) =>
  !failed && (data?.compile_status === 'running' || data?.compile_requested === true) ? COMPILE_POLL_MS : false

/** One manuscript with its files; polls while it compiles. */
export const useManuscript = (id: string) =>
  useQuery({
    queryKey: keys.manuscript(id),
    queryFn: () => api.getManuscript(id),
    refetchInterval: (query) => manuscriptPollInterval(query.state.data, query.state.status === 'error'),
  })

/** The papers a manuscript can cite, with their keys and note counts. */
export const useManuscriptPapers = (id: string) =>
  useQuery({ queryKey: keys.manuscriptPapers(id), queryFn: () => api.manuscriptPapers(id) })

/** Keys the source cites that match no paper or .bib entry; refetched on each compile and on window focus. */
export const useMissingKeys = (id: string, compiledAt: string | null | undefined) =>
  useQuery({
    queryKey: keys.missingKeys(id, compiledAt),
    queryFn: () => api.missingKeys(id),
    refetchOnWindowFocus: 'always',
  })

/** The registry of checks (names, costs, descriptions); fixed per server run, so a save does not refetch it. */
export const useCheckList = (id: string) =>
  useQuery({ queryKey: keys.checkList(id), queryFn: () => api.listManuscriptChecks(id), staleTime: Infinity })

/** The cheap checks, for the toolbar badge; refetched on save (manuscript invalidation), compile and focus, old data kept meanwhile. */
export const useCheckBadge = (id: string, compiledAt: string | null | undefined) =>
  useQuery({
    queryKey: keys.checkBadge(id, compiledAt),
    queryFn: () => api.runChecks(id, { cost: 'cheap' }),
    refetchOnWindowFocus: 'always',
    placeholderData: (previous) => previous,
  })

/** Run every check; the result lives in the panel, so nothing is invalidated. */
export const useRunChecks = () => useMutation({ mutationFn: (id: string) => api.runChecks(id, {}) })

/** The online DOI check; sends DOIs only, and only when asked. */
export const useDoiCheck = () => useMutation({ mutationFn: (id: string) => api.runDoiCheck(id) })

/** A compile pins the keys it cited, so each new compiled_at (not the first one seen) refetches the papers. */
export function usePapersFollowCompile(id: string, compiledAt: string | null | undefined) {
  const client = useQueryClient()
  const seen = useRef(compiledAt)
  useEffect(() => {
    if (seen.current !== undefined && compiledAt !== seen.current) void client.invalidateQueries({ queryKey: keys.manuscriptPapers(id) })
    seen.current = compiledAt
  }, [client, id, compiledAt])
}

export function usePinPaper() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (v: { id: string; paperId: string }) => api.pinPaper(v.id, v.paperId),
    onSuccess: (_key, v) => client.invalidateQueries({ queryKey: keys.manuscriptPapers(v.id) }),
  })
}

export const useManuscriptFile = (id: string, path: string | null) =>
  useQuery({
    queryKey: keys.manuscriptFile(id, path ?? ''),
    queryFn: () => api.getManuscriptFile(id, path!),
    enabled: path !== null,
    refetchOnWindowFocus: false, // the editor re-reads on focus itself, and only while its buffer is clean
  })

/** Saves a text file. A stale save (409 file_changed) resolves to `{ conflict: true, updatedAt }`; other errors throw. */
export function useSaveManuscriptFile() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async (v: { id: string; path: string; text: string; base: string | null }): Promise<SaveResult> => {
      try {
        const saved = await api.saveManuscriptFile(v.id, v.path, v.text, v.base)
        return { conflict: false, updatedAt: saved.updated_at }
      } catch (error) {
        if (error instanceof ApiError && error.code === 'file_changed' && typeof error.body.updated_at === 'string')
          return { conflict: true, updatedAt: error.body.updated_at }
        throw error
      }
    },
    onSuccess: (result, v) =>
      result.conflict ? undefined : client.invalidateQueries({ queryKey: keys.manuscript(v.id) }),
  })
}

export function useCompileManuscript() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api.compileManuscript(id),
    onSuccess: (_state, id) => client.invalidateQueries({ queryKey: keys.manuscript(id) }),
  })
}

export const useManuscriptSnapshots = (id: string) =>
  useQuery({ queryKey: keys.manuscriptSnapshots(id), queryFn: () => api.listManuscriptSnapshots(id) })

export function useRestoreSnapshot() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (v: { id: string; snapshotId: string }) => api.restoreManuscriptSnapshot(v.id, v.snapshotId),
    onSuccess: (_done, v) => client.invalidateQueries({ queryKey: keys.manuscript(v.id) }),
  })
}

function useManuscriptMutation<V, R>(mutationFn: (variables: V) => Promise<R>) {
  const client = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: () =>
      Promise.all([client.invalidateQueries({ queryKey: keys.manuscripts }), client.invalidateQueries({ queryKey: ['manuscriptPapers'] })]),
  })
}

export const useCreateManuscript = () => useManuscriptMutation((body: ManuscriptCreate) => api.createManuscript(body))
export const useImportManuscript = () =>
  useManuscriptMutation((v: { file: File; workspaceId: string | null }) => api.importManuscript(v.file, v.workspaceId))
export const useUpdateManuscript = () =>
  useManuscriptMutation((v: { id: string; patch: ManuscriptPatch }) => api.updateManuscript(v.id, v.patch))
export const useDeleteManuscript = () => useManuscriptMutation((id: string) => api.deleteManuscript(id))
/** A new, empty text file (a PUT with no base: 409 file_exists when there is one). */
export const useCreateManuscriptFile = () =>
  useManuscriptMutation((v: { id: string; path: string }) => api.saveManuscriptFile(v.id, v.path, '', null))
export const useUploadManuscriptFile = () =>
  useManuscriptMutation((v: { id: string; path: string; file: File }) => api.uploadManuscriptFile(v.id, v.path, v.file))
export const useRenameManuscriptFile = () =>
  useManuscriptMutation((v: { id: string; path: string; newPath: string }) => api.renameManuscriptFile(v.id, v.path, v.newPath))
export const useAddSection = () =>
  useManuscriptMutation((v: { id: string; title: string; after: string | null }) => api.addSection(v.id, v.title, v.after))
export const useSplitSections = () => useManuscriptMutation((id: string) => api.splitSections(id))
export const useRetitleSection = () =>
  useManuscriptMutation((v: { id: string; path: string; title: string }) => api.retitleSection(v.id, v.path, v.title))
export const useMoveSection = () =>
  useManuscriptMutation((v: { id: string; path: string; to: number }) => api.moveSection(v.id, v.path, v.to))
export const useDeleteSection = () =>
  useManuscriptMutation((v: { id: string; path: string }) => api.deleteSection(v.id, v.path))
export const useDeleteManuscriptFile = () =>
  useManuscriptMutation((v: { id: string; path: string }) => api.deleteManuscriptFile(v.id, v.path))

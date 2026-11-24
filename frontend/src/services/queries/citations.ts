import { keepPreviousData, useMutation, useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import type { ImportProgress } from '@/entities'
import { api } from '@/services/api'

/** A workspace's reference list as APA HTML, for the export dialog's preview. */
export const useCitationsPreview = (workspaceId: string) =>
  useQuery({
    queryKey: ['citations', workspaceId, 'apa-html'],
    queryFn: () => api.citationsText(workspaceId, 'apa-html'),
    retry: false,
    gcTime: 0,
  })

/** Reads made on a click (Copy as plain text), not shown as their own state. */
export function useCitationRequests(workspaceId: string) {
  return useMemo(() => ({ plainText: () => api.citationsText(workspaceId, 'apa') }), [workspaceId])
}

/** The chosen papers as one BibTeX or RIS file; `save` gets its bytes and the server's file name. */
export const useExportSelection = (
  paperIds: string[],
  workspaceId: string | undefined,
  save: (blob: Blob, filename: string) => void,
) =>
  useMutation({
    mutationFn: async (format: 'bibtex' | 'ris') => {
      const { blob, filename } = await api.exportSelection(paperIds, format, workspaceId)
      save(blob, filename)
    },
  })

/** What importing `file` would do. Once per file: only the save switch changes what the preview counts, so flipping
 * it asks again. ponytail: the file still goes up twice (preview, then Import); upload once by id if that hurts. */
export const useImportPreview = (file: File | null, saveWithoutPdf: boolean) =>
  useQuery({
    queryKey: ['citation-import-preview', file?.name, file?.size, file?.lastModified, saveWithoutPdf],
    queryFn: () => api.previewImport(file!, saveWithoutPdf),
    enabled: file !== null,
    placeholderData: keepPreviousData,
    retry: false,
    gcTime: 0,
  })

export type ImportTarget = { workspaceId?: string; newWorkspaceName?: string }
export type ImportStart = { file: File; target: ImportTarget; fetchPdfs: boolean; saveWithoutPdf: boolean }

/** Starts an import: the result now, or a job id to follow with useImportProgress. `onStart` runs before the upload. */
export const useStartImport = (onStart?: () => void) =>
  useMutation({
    mutationFn: ({ file, target, fetchPdfs, saveWithoutPdf }: ImportStart) => {
      onStart?.()
      return api.startImport(file, target, fetchPdfs, saveWithoutPdf)
    },
  })

/** A running import's progress, polled every `pollMs` while `keepPolling` says so. */
export const useImportProgress = (jobId: string | null | undefined, pollMs: number, keepPolling: (progress: ImportProgress | undefined) => boolean) =>
  useQuery({
    queryKey: ['citation-import', jobId],
    queryFn: () => api.importProgress(jobId!),
    enabled: !!jobId,
    refetchInterval: (q) => (keepPolling(q.state.data) || q.state.data === undefined ? pollMs : false),
  })

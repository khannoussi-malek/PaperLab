import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo } from 'react'
import { api } from '@/services/api'
import type { ChartSpec, DatasetCreate, GridIn, NumberCreate } from '@/entities'
import { keys } from './core'
import { refreshNotes } from './notes'

/** A paper's datasets (captured tables and its numbers), in page order. */
export const usePaperDatasets = (paperId: string) =>
  useQuery({ queryKey: keys.paperDatasets(paperId), queryFn: () => api.listDatasets(paperId) })

/** Every dataset, most recently changed first: the chart builder's list of sources. */
export const useAllDatasets = () => useQuery({ queryKey: [...keys.datasets, 'all'], queryFn: () => api.listDatasets() })

export const useDataset = (id: string | null) =>
  useQuery({ queryKey: keys.dataset(id ?? ''), queryFn: () => api.getDataset(id!), enabled: id !== null })

/** Loads a dataset from an event (the chart builder's data picker), from `useDataset`'s cache when it's there. */
export function useLoadDataset() {
  const client = useQueryClient()
  return (id: string) => client.ensureQueryData({ queryKey: keys.dataset(id), queryFn: () => api.getDataset(id) })
}

/** Data changes redraw charts: every mutation refreshes datasets and charts. */
export function useDatasetMutations() {
  const client = useQueryClient()
  const onSuccess = () =>
    Promise.all([
      client.invalidateQueries({ queryKey: keys.datasets }),
      client.invalidateQueries({ queryKey: keys.charts }),
    ])
  return {
    create: useMutation({ mutationFn: (dataset: DatasetCreate) => api.createDataset(dataset), onSuccess }),
    importFile: useMutation({
      mutationFn: ({ file, name }: { file: File; name?: string }) => api.importDataset(file, name),
      onSuccess,
    }),
    rename: useMutation({ mutationFn: ({ id, name }: { id: string; name: string }) => api.renameDataset(id, name), onSuccess }),
    saveGrid: useMutation({
      mutationFn: ({ id, grid, force = false }: { id: string; grid: GridIn; force?: boolean }) => api.saveGrid(id, grid, force),
      onSuccess,
    }),
    remove: useMutation({
      mutationFn: ({ id, force = false }: { id: string; force?: boolean }) => api.deleteDataset(id, force),
      onSuccess,
    }),
    addNumber: useMutation({
      mutationFn: ({ paperId, number }: { paperId: string; number: NumberCreate }) => api.addNumber(paperId, number),
      onSuccess,
    }),
  }
}

export const useCharts = () => useQuery({ queryKey: keys.charts, queryFn: api.listCharts })

export const useChart = (id: string | null) =>
  useQuery({ queryKey: keys.chart(id ?? ''), queryFn: () => api.getChart(id!), enabled: id !== null })

/** The data a spec draws, paired with that spec. While a changed spec refetches, the placeholder is the previous pair,
 * so the last drawing stays up (compiled from its own spec) instead of a blank chart. */
export const useResolvedChart = (spec: ChartSpec | null) =>
  useQuery({
    queryKey: keys.resolved(spec!),
    queryFn: async () => ({ spec: spec!, data: await api.resolveChart(spec!) }),
    enabled: spec !== null,
    placeholderData: keepPreviousData,
  })

export function useChartMutations() {
  const client = useQueryClient()
  const charts = () => client.invalidateQueries({ queryKey: keys.charts })
  // A chart's links to datasets show on the datasets ("used by"), and notes show the chart's title.
  const everything = () => Promise.all([charts(), client.invalidateQueries({ queryKey: keys.datasets }), refreshNotes(client)])
  return {
    create: useMutation({
      mutationFn: ({ title, spec }: { title: string; spec: ChartSpec }) => api.createChart(title, spec),
      onSuccess: everything,
    }),
    update: useMutation({
      mutationFn: ({ id, ...patch }: { id: string; title?: string; spec?: ChartSpec }) => api.updateChart(id, patch),
      onSuccess: everything,
    }),
    duplicate: useMutation({ mutationFn: api.duplicateChart, onSuccess: everything }),
    remove: useMutation({ mutationFn: api.deleteChart, onSuccess: everything }),
    addToNote: useMutation({ mutationFn: api.addChartToNote, onSuccess: everything }),
    attach: useMutation({
      mutationFn: ({ noteId, chartId }: { noteId: string; chartId: string }) => api.attachChart(noteId, chartId),
      onSuccess: everything,
    }),
    detach: useMutation({
      mutationFn: ({ noteId, chartId }: { noteId: string; chartId: string }) => api.detachChart(noteId, chartId),
      onSuccess: everything,
    }),
  }
}

/** A section's numbers as the model found them (D33). Asked once per opening: the model costs time, so nothing
 * refetches by itself. */
export const useNumberSuggestions = (paperId: string, sectionTitle: string | null) =>
  useQuery({
    queryKey: ['papers', paperId, 'number-suggestions', sectionTitle],
    queryFn: () => api.suggestNumbers(paperId, sectionTitle),
    staleTime: Infinity,
    gcTime: 0,
    refetchOnWindowFocus: false,
    retry: false,
  })

/** One-off reads the capture dialogs make while they open; the dialogs keep what comes back as editable state. */
export function usePaperDataRequests(paperId: string) {
  return useMemo(
    () => ({
      numberCandidates: (text: string) => api.numberCandidates(text),
      previewTable: (page: number, region: [number, number, number, number]) => api.previewTable(paperId, page, region),
    }),
    [paperId],
  )
}

import { request, sendJson } from '../http'
import type { Chart, ChartSpec, ChartSummary, Dataset, DatasetCreate, DatasetSummary, GridIn, Note, NumberAdded, NumberCandidate, NumberCreate, NumberSuggestions, ResolvedData, TablePreview } from '@/entities'

export const datasetsApi = {
  previewTable: (paperId: string, page: number, region: [number, number, number, number]) =>
    request<TablePreview>(`/api/papers/${paperId}/tables/preview`, sendJson('POST', { page, region })),
  /** A section's numbers a model found, kept only when each quote is in the section and holds its value (D33). */
  suggestNumbers: (paperId: string, sectionTitle: string | null) =>
    request<NumberSuggestions>(`/api/papers/${paperId}/numbers/suggestions`, sendJson('POST', { section_title: sectionTitle })),
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
}

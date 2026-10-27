// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { api, type Chart, type ChartSummary, type ResolvedData } from '@/api/client'
import { ChartDialog } from './ChartDialog'
import type { InsertResult } from './useInsertBlock'

const toImage = vi.fn(async () => 'data:image/png;base64,AAAA')
vi.mock('@/features/charts/loadPlotly', () => ({ loadPlotly: async () => ({ toImage }) }))
vi.mock('@/features/charts/ChartView', () => ({ ChartView: () => <div className="js-plotly-plot" /> }))

const data = { datasets: [{ id: 'd1', name: 'D', columns: [{ id: 'x', name: 'X' }, { id: 'y', name: 'Y' }], rows: [{ id: 'r', cells: [{ column_id: 'x', raw: 'a', value: null }, { column_id: 'y', raw: '1', value: 1 }] }] }] } as unknown as ResolvedData
const barSpec = { type: 'bar', series: [{ dataset_id: 'd1', x: 'x', y: 'y', name: '', multiply: 1, trend: null, error: null, row_filter: null }] }
const boxSpec = { type: 'box' }

function setup(spec: unknown, insert = vi.fn(async (): Promise<InsertResult> => ({ ok: true }))) {
  vi.spyOn(api, 'listCharts').mockResolvedValue([{ id: 'c1', title: 'My Chart', type: 'bar' } as unknown as ChartSummary])
  vi.spyOn(api, 'getChart').mockResolvedValue({ id: 'c1', title: 'My Chart', spec } as unknown as Chart)
  vi.spyOn(api, 'resolveChart').mockResolvedValue(data)
  const onOpenChange = vi.fn()
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
      <ChartDialog open onOpenChange={onOpenChange} manuscriptId="m1" labelTexts={() => []} filePaths={() => ['figures/my-chart.png']} onInsert={insert} />
    </QueryClientProvider>,
  )
  return { insert, onOpenChange }
}
afterEach(() => vi.restoreAllMocks())

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} }
Element.prototype.scrollIntoView ??= () => {}

test('a supported chart inserts pgfplots with its package', async () => {
  const { insert } = setup(barSpec)
  fireEvent.click(await screen.findByText('My Chart'))
  const button = screen.getByRole('button', { name: 'Insert' })
  await waitFor(() => expect(button).toBeEnabled())
  fireEvent.click(button)
  await waitFor(() => expect(insert).toHaveBeenCalled())
  const [code, packages] = insert.mock.calls[0] as unknown as [string, string[]]
  expect(code).toContain('\\begin{axis}')
  expect(code).toContain('\\label{fig:my-chart}')
  expect(packages).toEqual(['pgfplots'])
})

test('an unsupported chart says why, uploads a unique png, then inserts the picture', async () => {
  const upload = vi.spyOn(api, 'uploadManuscriptFile').mockResolvedValue({} as never)
  const { insert } = setup(boxSpec)
  fireEvent.click(await screen.findByText('My Chart'))
  expect(await screen.findByText("pgfplots can't draw this chart type, so it goes in as a picture.")).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Insert as a picture' }))
  await waitFor(() => expect(insert).toHaveBeenCalled())
  expect(toImage).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ format: 'png', width: 1950, scale: 1 }))
  expect(upload.mock.calls[0][1]).toBe('figures/my-chart-2.png')
  const [code, packages] = insert.mock.calls[0] as unknown as [string, string[]]
  expect(code).toContain('\\includegraphics[width=\\linewidth]{figures/my-chart-2}')
  expect(packages).toEqual(['graphicx'])
})

test('an upload failure shows inline and inserts nothing', async () => {
  vi.spyOn(api, 'uploadManuscriptFile').mockRejectedValue(new Error('Disk full'))
  const { insert } = setup(boxSpec)
  fireEvent.click(await screen.findByText('My Chart'))
  fireEvent.click(await screen.findByRole('button', { name: 'Insert as a picture' }))
  expect(await screen.findByText('Disk full')).toBeInTheDocument()
  expect(insert).not.toHaveBeenCalled()
})

test('a refused insert after the upload names the saved file', async () => {
  vi.spyOn(api, 'uploadManuscriptFile').mockResolvedValue({} as never)
  setup(boxSpec, vi.fn(async () => ({ ok: false, message: 'The main file changed. Open it and try again.' }) as InsertResult))
  fireEvent.click(await screen.findByText('My Chart'))
  fireEvent.click(await screen.findByRole('button', { name: 'Insert as a picture' }))
  expect(await screen.findByText(/The picture was saved as figures\/my-chart-2\.png; insert it again\./)).toBeInTheDocument()
})

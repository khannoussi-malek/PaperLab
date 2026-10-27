// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { api, type Chart, type ChartSummary, type ResolvedData } from '@/api/client'
import { ChartDialog } from './ChartDialog'
import type { InsertResult } from './useInsertBlock'

const toImage = vi.fn(async (..._a: unknown[]) => 'data:image/png;base64,AAAA')
const newPlot = vi.fn(async (..._a: unknown[]) => undefined)
const purge = vi.fn()
vi.mock('@/features/charts/loadPlotly', () => ({ loadPlotly: async () => ({ toImage, newPlot, purge }) }))
const compileSpy = vi.hoisted(() => vi.fn())
vi.mock('@/features/charts/compile', async (orig) => {
  const real = await orig<typeof import('@/features/charts/compile')>()
  return { compileChart: (...a: Parameters<typeof real.compileChart>) => { compileSpy(...a); return real.compileChart(...a) } }
})
const pgf = vi.hoisted(() => ({ fail: false }))
vi.mock('./pgfplots', async (orig) => {
  const real = await orig<typeof import('./pgfplots')>()
  return { ...real, toPgfplots: (...a: Parameters<typeof real.toPgfplots>) => { if (pgf.fail) throw new Error('Cannot draw this'); return real.toPgfplots(...a) } }
})
vi.mock('@/features/charts/ChartView', () => ({ ChartView: () => <div className="js-plotly-plot" /> }))

const data = { datasets: [{ id: 'd1', name: 'D', columns: [{ id: 'x', name: 'X' }, { id: 'y', name: 'Y' }], rows: [{ id: 'r', cells: [{ column_id: 'x', raw: 'a', value: null }, { column_id: 'y', raw: '1', value: 1 }] }] }] } as unknown as ResolvedData
const barSpec = { type: 'bar', series: [{ dataset_id: 'd1', x: 'x', y: 'y', name: '', multiply: 1, trend: null, error: null, row_filter: null }] }
const boxSpec = { type: 'box', series: [{ dataset_id: 'd1', x: 'x', y: 'y', name: '', multiply: 1, trend: null, error: null, row_filter: null }] }

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
afterEach(() => { vi.restoreAllMocks(); pgf.fail = false; document.documentElement.classList.remove('dark'); toImage.mockClear(); newPlot.mockClear(); purge.mockClear(); compileSpy.mockClear() })

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
  // 650 css px wide at scale 3 is 1950 px, with text about 9 pt in print.
  expect(toImage).toHaveBeenCalledWith(expect.anything(), expect.objectContaining({ format: 'png', width: 650, scale: 3 }))
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

test('the picture is built off-screen in the light theme on white, even when the app is dark', async () => {
  document.documentElement.classList.add('dark')
  vi.spyOn(api, 'uploadManuscriptFile').mockResolvedValue({} as never)
  setup(boxSpec)
  fireEvent.click(await screen.findByText('My Chart'))
  fireEvent.click(await screen.findByRole('button', { name: 'Insert as a picture' }))
  await waitFor(() => expect(purge).toHaveBeenCalled())
  expect(compileSpy.mock.calls.at(-1)?.[2]).toBe('light')
  const [div, , layout] = newPlot.mock.calls[0] as unknown as [HTMLElement, unknown, Record<string, unknown>]
  expect(layout).toMatchObject({ paper_bgcolor: '#ffffff', plot_bgcolor: '#ffffff', width: 650 })
  expect(toImage.mock.calls[0][0]).toBe(div)
  expect(div.isConnected).toBe(false)
})

test('a pgfplots failure is shown, never offered as LaTeX, and Insert is disabled', async () => {
  pgf.fail = true
  const { insert } = setup(barSpec)
  fireEvent.click(await screen.findByText('My Chart'))
  expect(await screen.findByText('Cannot draw this')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Insert' })).toBeDisabled()
  expect(insert).not.toHaveBeenCalled()
})

test('Insert as a picture waits for the chart data', async () => {
  vi.spyOn(api, 'listCharts').mockResolvedValue([{ id: 'c1', title: 'My Chart', type: 'box' } as unknown as ChartSummary])
  vi.spyOn(api, 'getChart').mockResolvedValue({ id: 'c1', title: 'My Chart', spec: boxSpec } as unknown as Chart)
  vi.spyOn(api, 'resolveChart').mockReturnValue(new Promise(() => {}))
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ChartDialog open onOpenChange={() => {}} manuscriptId="m1" labelTexts={() => []} filePaths={() => []} onInsert={async () => ({ ok: true })} />
    </QueryClientProvider>,
  )
  fireEvent.click(await screen.findByText('My Chart'))
  await waitFor(() => expect(api.resolveChart).toHaveBeenCalled())
  expect(screen.queryByRole('button', { name: 'Insert as a picture' })).toBeNull()
  expect(screen.getByRole('button', { name: 'Insert' })).toBeDisabled()
})

// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { api, ApiError, type Dataset, type DatasetSummary } from '@/api/client'
import { TableDialog } from './TableDialog'
import type { InsertResult } from './useInsertBlock'

const summary = (id: string, name: string) => ({ id, name, kind: 'table', paper_id: 'p1', paper_title: 'A_Paper' }) as unknown as DatasetSummary
const detail = {
  id: 'd1', name: 'Main results', kind: 'table', paper_id: 'p1', paper_title: 'A_Paper',
  columns: [{ id: 'c1', position: 0, name: 'Model', unit: null }, { id: 'c2', position: 1, name: 'F1', unit: null }],
  rows: [{ id: 'r1', position: 0, cells: [{ column_id: 'c1', raw: 'BERT', value: null, error: null }, { column_id: 'c2', raw: '88', value: 88, error: null }] }],
} as unknown as Dataset

function setup(texts: string[] = [], insert = vi.fn(async (): Promise<InsertResult> => ({ ok: true }))) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const onOpenChange = vi.fn()
  render(
    <QueryClientProvider client={client}>
      <TableDialog open onOpenChange={onOpenChange} manuscriptId="m1" labelTexts={() => texts} onInsert={insert} />
    </QueryClientProvider>,
  )
  return { insert, onOpenChange }
}

// cmdk measures and scrolls; jsdom has neither.
globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} }
Element.prototype.scrollIntoView ??= () => {}

afterEach(() => vi.restoreAllMocks())

function withDataset() {
  vi.spyOn(api, 'listDatasets').mockResolvedValue([summary('d1', 'Main results')])
  vi.spyOn(api, 'getDataset').mockResolvedValue(detail)
}

async function pick() {
  fireEvent.click(await screen.findByText('Main results'))
}

test('a paste previews as a table and as LaTeX, and inserts booktabs with the packages', async () => {
  vi.spyOn(api, 'listDatasets').mockResolvedValue([])
  const { insert, onOpenChange } = setup()
  expect(screen.getByRole('button', { name: 'Insert' })).toBeDisabled()
  fireEvent.mouseDown(screen.getByRole('tab', { name: 'Paste' }))
  fireEvent.change(screen.getByLabelText('Paste a table'), { target: { value: 'Model\tF1\nBERT\t88' } })
  expect(screen.getByRole('table')).toHaveTextContent('BERT')
  fireEvent.mouseDown(screen.getByRole('tab', { name: 'LaTeX' }))
  expect(screen.getByText(/\\toprule/)).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Caption'), { target: { value: 'Scores & more.' } })
  fireEvent.click(screen.getByRole('button', { name: 'Insert' }))
  await waitFor(() => expect(insert).toHaveBeenCalled())
  const [code, packages] = insert.mock.calls[0] as unknown as [string, string[]]
  expect(code).toContain('\\caption{Scores \\& more.}')
  expect(code).toContain('\\label{tab:table}')
  expect(packages).toEqual(['booktabs'])
  await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false))
})

test('the label is made unique against the manuscript', async () => {
  vi.spyOn(api, 'listDatasets').mockResolvedValue([])
  setup(['\\label{tab:table}'])
  fireEvent.mouseDown(screen.getByRole('tab', { name: 'Paste' }))
  expect(screen.getByLabelText('Label')).toHaveValue('tab:table-2')
})

test('a saved captured table pins its paper and cites it in the caption', async () => {
  const pin = vi.spyOn(api, 'pinPaper').mockResolvedValue({ key: 'smith2020' })
  withDataset()
  const { insert } = setup()
  await pick()
  expect(await screen.findByLabelText('Label')).toHaveValue('tab:main-results')
  fireEvent.click(screen.getByRole('button', { name: 'Insert' }))
  await waitFor(() => expect(insert).toHaveBeenCalled())
  expect(pin).toHaveBeenCalledWith('m1', 'p1')
  expect((insert.mock.calls[0] as unknown as [string])[0]).toContain('Source: \\citep{smith2020}')
})

test('when the paper is not citable the caption names its title and nothing is pinned', async () => {
  vi.spyOn(api, 'pinPaper').mockRejectedValue(new ApiError('unknown_paper', 404, { detail: 'unknown_paper' }))
  withDataset()
  const { insert } = setup()
  await pick()
  fireEvent.click(await screen.findByRole('button', { name: 'Insert' }))
  await waitFor(() => expect(insert).toHaveBeenCalled())
  expect((insert.mock.calls[0] as unknown as [string])[0]).toContain('Source: A\\_Paper')
})

test('an insert that is refused stays open and shows why', async () => {
  vi.spyOn(api, 'listDatasets').mockResolvedValue([])
  const { onOpenChange } = setup([], vi.fn(async (): Promise<InsertResult> => ({ ok: false, message: 'The main file changed. Open it and try again.' })))
  fireEvent.mouseDown(screen.getByRole('tab', { name: 'Paste' }))
  fireEvent.change(screen.getByLabelText('Paste a table'), { target: { value: 'a,b\n1,2' } })
  fireEvent.click(screen.getByRole('button', { name: 'Insert' }))
  expect(await screen.findByText('The main file changed. Open it and try again.')).toBeInTheDocument()
  expect(onOpenChange).not.toHaveBeenCalledWith(false)
})

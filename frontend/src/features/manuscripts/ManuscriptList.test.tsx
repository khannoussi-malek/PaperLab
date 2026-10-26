// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { api, type Manuscript } from '@/api/client'
import { ManuscriptList } from './ManuscriptList'

const ms = (over: Partial<Manuscript>): Manuscript => ({
  id: 'm1', workspace_id: 'w1', title: 'My thesis', main_file: 'main.tex', checklist: {}, compile_status: 'ok',
  compile_requested: false, compiled_at: null, compile_log: null, compile_errors: [],
  created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-02T00:00:00Z', ...over,
})

function renderList() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><ManuscriptList workspaceId="w1" /></QueryClientProvider>)
}

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
  vi.spyOn(api, 'listManuscripts').mockResolvedValue([ms({}), ms({ id: 'm2', title: 'Draft two', compile_status: 'failed' })])
  vi.spyOn(api, 'listManuscriptTemplates').mockResolvedValue([{ name: 'article', label: 'Article' }, { name: 'ieee', label: 'IEEE' }])
})
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

test('lists title and compile state', async () => {
  renderList()
  const link = await screen.findByRole('link', { name: /My thesis/ })
  expect(link).toHaveAttribute('href', '#/manuscripts/m1')
  expect(screen.getByText('Compiled')).toBeInTheDocument()
  expect(screen.getByText('Last compile failed')).toBeInTheDocument()
})

test('New opens the template picker', async () => {
  renderList()
  fireEvent.click(await screen.findByRole('button', { name: 'New manuscript' }))
  expect(await screen.findByRole('radio', { name: /IEEE/ })).toBeInTheDocument()
  expect(screen.getByLabelText('Title')).toBeInTheDocument()
})

test('Import accepts .zip only', async () => {
  const { container } = renderList()
  await screen.findByRole('button', { name: 'New manuscript' })
  expect(container.querySelector('input[type=file]')).toHaveAttribute('accept', '.zip,application/zip')
})

test('an import says which files were skipped', async () => {
  vi.spyOn(api, 'importManuscript').mockResolvedValue({ ...ms({ id: 'm3' }), files: [], skipped: ['README', 'fig.eps'] })
  const { container } = renderList()
  await screen.findByRole('button', { name: 'New manuscript' })
  const input = container.querySelector('input[type=file]') as HTMLInputElement
  fireEvent.change(input, { target: { files: [new File(['x'], 'paper.zip', { type: 'application/zip' })] } })
  expect(await screen.findByText("Imported. Skipped 2 files PaperLab can't use yet: README, fig.eps.")).toBeInTheDocument()
})

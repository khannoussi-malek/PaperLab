// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { api, type Manuscript } from '@/api/client'
import { ManuscriptList } from './ManuscriptList'

const ms = (over: Partial<Manuscript>): Manuscript => ({
  id: 'm1', workspace_id: 'w1', title: 'My thesis', main_file: 'main.tex', checklist: {}, compile_status: 'ok',
  compile_requested: false, compiled_at: null, compile_log: null, compile_friendly: null, compile_errors: [],
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

test('Move picks a workspace, or none, and saves it', async () => {
  vi.spyOn(api, 'listWorkspaces').mockResolvedValue([{ id: 'w1', name: 'Sleep' }, { id: 'w2', name: 'Memory' }] as never)
  const update = vi.spyOn(api, 'updateManuscript').mockResolvedValue({ ...ms({ workspace_id: null }), files: [] })
  renderList()
  fireEvent.click(await screen.findByRole('button', { name: 'Move My thesis' }))
  const picker = await screen.findByLabelText('Workspace')
  await screen.findByRole('option', { name: 'Memory' })
  expect(picker).toHaveValue('w1')
  fireEvent.change(picker, { target: { value: '' } })
  fireEvent.click(screen.getByRole('button', { name: 'Move' }))
  await waitFor(() => expect(update).toHaveBeenCalledWith('m1', { workspace_id: null }))
})

test('Delete asks in the app before deleting the manuscript', async () => {
  const confirm = vi.spyOn(window, 'confirm')
  const remove = vi.spyOn(api, 'deleteManuscript').mockResolvedValue(undefined)
  renderList()
  fireEvent.click(await screen.findByRole('button', { name: 'Delete Draft two' }))
  expect(await screen.findByText('Delete “Draft two”?')).toBeInTheDocument()
  expect(remove).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Delete manuscript' }))
  await waitFor(() => expect(remove).toHaveBeenCalledWith('m2'))
  expect(confirm).not.toHaveBeenCalled()
})

test('the library lists manuscripts without a workspace with the same actions', async () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const list = vi.spyOn(api, 'listManuscripts').mockResolvedValue([ms({ workspace_id: null })])
  render(<QueryClientProvider client={client}><ManuscriptList workspaceId={null} /></QueryClientProvider>)
  expect(await screen.findByRole('button', { name: 'Move My thesis' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Delete My thesis' })).toBeInTheDocument()
  expect(list).toHaveBeenCalledWith(null)
})

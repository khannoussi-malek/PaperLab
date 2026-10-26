// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { api, ApiError } from '@/api/client'
import { FileList, pathProblem } from './FileList'

const T = '2026-10-02T00:00:00Z'
const FILES = [
  { path: 'fig/plot.png', size: 9, updated_at: T },
  { path: 'main.tex', size: 5, updated_at: T },
  { path: 'sections/intro.tex', size: 3, updated_at: T },
]

function renderList(current = 'main.tex', flushCurrent = vi.fn(async () => true)) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  render(
    <QueryClientProvider client={client}>
      <FileList manuscriptId="m1" files={FILES} current={current} main="main.tex" flushCurrent={flushCurrent} />
    </QueryClientProvider>,
  )
  return flushCurrent
}

beforeEach(() => { window.location.hash = '' })
afterEach(() => {
  vi.restoreAllMocks()
  window.location.hash = ''
})

test('the main file has no Delete, figures are listed but not opened, and paperlab.bib is read-only', () => {
  renderList()
  expect(screen.getByRole('button', { name: 'Rename main.tex' })).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Delete main.tex' })).toBeNull()
  expect(screen.getByRole('button', { name: 'Delete sections/intro.tex' })).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: 'fig/plot.png' })).toBeNull()
  expect(screen.getByText('fig/plot.png')).toBeInTheDocument()
  expect(screen.queryByRole('link', { name: /paperlab\.bib/ })).toBeNull()
  expect(screen.getByText('paperlab.bib')).toBeInTheDocument()
  expect(screen.getByText(/generated from the workspace's papers when you compile/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /paperlab\.bib/ })).toBeNull() // no rename or delete for it
})

test('New file creates an empty text file and opens it', async () => {
  const save = vi.spyOn(api, 'saveManuscriptFile').mockResolvedValue({ path: 'sections/methods.tex', size: 0, updated_at: T })
  renderList()
  fireEvent.click(screen.getByRole('button', { name: 'New file' }))
  fireEvent.change(screen.getByLabelText('New file name'), { target: { value: 'sections/methods.tex' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  await waitFor(() => expect(window.location.hash).toBe('#/manuscripts/m1?file=sections%2Fmethods.tex'))
  expect(save).toHaveBeenCalledWith('m1', 'sections/methods.tex', '', null)
})

test('a name the server would refuse is caught before any request', () => {
  const save = vi.spyOn(api, 'saveManuscriptFile')
  renderList()
  fireEvent.click(screen.getByRole('button', { name: 'New file' }))
  fireEvent.change(screen.getByLabelText('New file name'), { target: { value: 'my notes.tex' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  expect(screen.getByRole('alert')).toHaveTextContent('The file name "my notes.tex" isn\'t allowed.')
  expect(save).not.toHaveBeenCalled()
})

test('a server refusal shows its sentence', async () => {
  vi.spyOn(api, 'saveManuscriptFile').mockRejectedValue(new ApiError('file_exists', 409, { detail: 'file_exists' }))
  renderList()
  fireEvent.click(screen.getByRole('button', { name: 'New file' }))
  fireEvent.change(screen.getByLabelText('New file name'), { target: { value: 'main.tex' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('A file with that name already exists.')
})

test('Upload sends the chosen figure through the uploads route', async () => {
  const upload = vi.spyOn(api, 'uploadManuscriptFile').mockResolvedValue({ path: 'chart.png', size: 4, updated_at: T })
  renderList()
  const file = new File(['\x89PNG'], 'chart.png', { type: 'image/png' })
  fireEvent.change(screen.getByTestId('upload-input'), { target: { files: [file] } })
  await waitFor(() => expect(upload).toHaveBeenCalledWith('m1', 'chart.png', file))
})

test('Rename saves the open file first, renames it and follows it', async () => {
  const order: string[] = []
  const flush = vi.fn(async () => { order.push('flush'); return true })
  vi.spyOn(api, 'renameManuscriptFile').mockImplementation(async () => { order.push('rename'); return { path: 'intro2.tex', size: 3, updated_at: T } })
  renderList('sections/intro.tex', flush)
  fireEvent.click(screen.getByRole('button', { name: 'Rename sections/intro.tex' }))
  fireEvent.change(screen.getByLabelText('New name for sections/intro.tex'), { target: { value: 'intro2.tex' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  await waitFor(() => expect(window.location.hash).toBe('#/manuscripts/m1?file=intro2.tex'))
  expect(order).toEqual(['flush', 'rename'])
})

test('Rename does nothing when the open file could not be saved', async () => {
  const rename = vi.spyOn(api, 'renameManuscriptFile')
  renderList('sections/intro.tex', vi.fn(async () => false))
  fireEvent.click(screen.getByRole('button', { name: 'Rename sections/intro.tex' }))
  fireEvent.change(screen.getByLabelText('New name for sections/intro.tex'), { target: { value: 'intro2.tex' } })
  fireEvent.click(screen.getByRole('button', { name: 'Save' }))
  await new Promise((r) => setTimeout(r, 20))
  expect(rename).not.toHaveBeenCalled()
})

test('Delete asks in the page first, then deletes', async () => {
  const confirm = vi.spyOn(window, 'confirm')
  const remove = vi.spyOn(api, 'deleteManuscriptFile').mockResolvedValue(undefined)
  renderList()
  fireEvent.click(screen.getByRole('button', { name: 'Delete sections/intro.tex' }))
  const ask = screen.getByRole('group', { name: 'Delete sections/intro.tex?' })
  expect(remove).not.toHaveBeenCalled()
  fireEvent.click(within(ask).getByRole('button', { name: 'Delete' }))
  await waitFor(() => expect(remove).toHaveBeenCalledWith('m1', 'sections/intro.tex'))
  expect(confirm).not.toHaveBeenCalled()
})

test('deleting the open file goes back to the main file', async () => {
  vi.spyOn(api, 'deleteManuscriptFile').mockResolvedValue(undefined)
  renderList('sections/intro.tex')
  fireEvent.click(screen.getByRole('button', { name: 'Delete sections/intro.tex' }))
  fireEvent.click(within(screen.getByRole('group', { name: 'Delete sections/intro.tex?' })).getByRole('button', { name: 'Delete' }))
  await waitFor(() => expect(window.location.hash).toBe('#/manuscripts/m1?file=main.tex'))
})

test('pathProblem mirrors the server rules', () => {
  expect(pathProblem('a/b.tex', ['tex'])).toBeNull()
  expect(pathProblem('../a.tex', ['tex'])).toBe('bad_path')
  expect(pathProblem('a/b/c/d/e.tex', ['tex'])).toBe('bad_path')
  expect(pathProblem('sub/PaperLab.bib', ['bib'])).toBe('reserved_path')
  expect(pathProblem('a.exe', ['tex'])).toBe('unsupported_file_type')
  expect(pathProblem('latexmkrc', ['tex'])).toBeNull()
})

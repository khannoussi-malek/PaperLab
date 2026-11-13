// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { sileo } from 'sileo'
import { afterEach, expect, test, vi } from 'vitest'
import { api, ApiError, type ManuscriptTemplate } from '@/api/client'
import { BlueprintPanel } from './BlueprintPanel'

const T = '2026-11-10T00:00:00Z'
const file = (path: string) => ({ path, size: 1, updated_at: T })
const ARTICLE = { name: 'article', label: 'Article', official: false, page_limit: null, references_count: true, provenance: '', section_words: { introduction: [400, 900] } }

function renderPanel({ files, title = 'My paper', template = 'article' }: { files: { path: string }[]; title?: string; template?: string }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  render(
    <QueryClientProvider client={client}>
      <BlueprintPanel manuscriptId="m1" files={files.map((f) => file(f.path))} mainFile="main.tex" title={title} template={template} />
    </QueryClientProvider>,
  )
  return { invalidate }
}

function mockFile(path: string, text: string) {
  return vi.spyOn(api, 'getManuscriptFile').mockResolvedValue({ path, updated_at: T, text })
}

function mockSave() {
  return vi.spyOn(api, 'saveManuscriptFile').mockResolvedValue(file('blueprint.json'))
}

function mockTemplates() {
  vi.spyOn(api, 'listManuscriptTemplates').mockResolvedValue([ARTICLE] as never as ManuscriptTemplate[])
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

test('no blueprint.json: the section offers Create and never reads a file', () => {
  const read = vi.spyOn(api, 'getManuscriptFile')
  mockTemplates()
  renderPanel({ files: [{ path: 'main.tex' }] })
  expect(screen.getByRole('region', { name: 'Paper plan' })).toBeInTheDocument()
  expect(screen.getByText('No paper plan yet.')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Create blueprint' })).toBeInTheDocument()
  expect(read).not.toHaveBeenCalled()
})

test('shows the plan read-only', async () => {
  mockFile('blueprint.json', '{"title":"Fast retrieval","contributions":["A graph"],"notation":[{"symbol":"\\\\alpha","meaning":"weight"}],"target_words":{"method":[600,1500]}}')
  renderPanel({ files: [{ path: 'main.tex' }, { path: 'blueprint.json' }] })
  expect(await screen.findByText('Fast retrieval')).toBeInTheDocument()
  expect(screen.getByText('A graph')).toBeInTheDocument()
  expect(screen.getByText('weight')).toBeInTheDocument()
  expect(screen.getByText(/600 to 1500/)).toBeInTheDocument()
  expect(screen.queryByRole('textbox')).toBeNull() // read-only
})

test('an unreadable file is one muted line', async () => {
  mockFile('blueprint.json', 'not json')
  renderPanel({ files: [{ path: 'blueprint.json' }] })
  expect(await screen.findByText("blueprint.json can't be read. Open it in All files to fix it.")).toBeInTheDocument()
})

test('the Create button shows only when there is no blueprint', async () => {
  mockTemplates()
  renderPanel({ files: [{ path: 'blueprint.json' }] })
  mockFile('blueprint.json', '{}')
  expect(await screen.findByText('Paper plan')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Create blueprint' })).toBeNull()
})

test('it writes the starter with a null base and the template bands', async () => {
  mockTemplates()
  const save = mockSave()
  mockFile('main.tex', '\\section{A}')
  renderPanel({ files: [{ path: 'main.tex' }] })
  const button = screen.getByRole('button', { name: 'Create blueprint' })
  await waitFor(() => expect(button).toBeEnabled()) // the template bands have loaded
  fireEvent.click(button)
  await waitFor(() => expect(save).toHaveBeenCalledTimes(1))
  const [id, path, text, base] = save.mock.calls[0]
  expect([id, path, base]).toEqual(['m1', 'blueprint.json', null])
  expect(JSON.parse(text)).toEqual({ title: 'My paper', contributions: [], notation: [], target_words: { introduction: [400, 900] } })
})

test('the starter takes the title from the main file\'s \\title, not the stored name', async () => {
  mockTemplates()
  const save = mockSave()
  mockFile('main.tex', '% \\title{Old}\n\\title[Short]{Real \\\\ \\large Title\\thanks{Funded}}')
  renderPanel({ files: [{ path: 'main.tex' }], title: 'Stored name' })
  const button = screen.getByRole('button', { name: 'Create blueprint' })
  await waitFor(() => expect(button).toBeEnabled())
  fireEvent.click(button)
  await waitFor(() => expect(save).toHaveBeenCalledTimes(1))
  expect(JSON.parse(save.mock.calls[0][2]).title).toBe('Real Title')
})

test('a custom template writes empty targets', async () => {
  mockTemplates()
  const save = mockSave()
  mockFile('main.tex', '\\section{A}')
  renderPanel({ files: [{ path: 'main.tex' }], title: 'T', template: 'custom' })
  const button = screen.getByRole('button', { name: 'Create blueprint' })
  await waitFor(() => expect(button).toBeEnabled())
  fireEvent.click(button)
  await waitFor(() => expect(save).toHaveBeenCalledTimes(1))
  expect(JSON.parse(save.mock.calls[0][2]).target_words).toEqual({})
})

test('after creating, the manuscript and its blueprint are refetched', async () => {
  mockTemplates()
  mockSave()
  mockFile('main.tex', '\\section{A}')
  const { invalidate } = renderPanel({ files: [{ path: 'main.tex' }] })
  const button = screen.getByRole('button', { name: 'Create blueprint' })
  await waitFor(() => expect(button).toBeEnabled())
  fireEvent.click(button)
  await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['manuscripts', 'm1', 'file', 'blueprint.json'] }))
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ['manuscripts', 'm1'] })
})

test('it never overwrites: a 409 file_exists refreshes and shows no error', async () => {
  mockTemplates()
  const save = vi.spyOn(api, 'saveManuscriptFile').mockRejectedValue(new ApiError('file_exists', 409, { detail: 'file_exists' }))
  mockFile('main.tex', '\\section{A}')
  const toast = vi.spyOn(sileo, 'error').mockReturnValue('' as never)
  const { invalidate } = renderPanel({ files: [{ path: 'main.tex' }] })
  const button = screen.getByRole('button', { name: 'Create blueprint' })
  await waitFor(() => expect(button).toBeEnabled())
  fireEvent.click(button)
  await waitFor(() => expect(save).toHaveBeenCalledTimes(1))
  await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['manuscripts', 'm1', 'file', 'blueprint.json'] }))
  expect(toast).not.toHaveBeenCalled()
})

test('another failure shows the Sileo error', async () => {
  mockTemplates()
  vi.spyOn(api, 'saveManuscriptFile').mockRejectedValue(new ApiError('boom', 500, { detail: 'boom' }))
  mockFile('main.tex', '\\section{A}')
  const toast = vi.spyOn(sileo, 'error').mockReturnValue('' as never)
  renderPanel({ files: [{ path: 'main.tex' }] })
  const button = screen.getByRole('button', { name: 'Create blueprint' })
  await waitFor(() => expect(button).toBeEnabled())
  fireEvent.click(button)
  await waitFor(() => expect(toast).toHaveBeenCalledWith({ title: "Couldn't create the blueprint" }))
})

const NO_TARGETS_LINE = 'No word targets yet: this template has none. Add them under target_words.'

test('a plan with no targets on a template with no bands says so', async () => {
  mockTemplates()
  mockFile('blueprint.json', '{"title":"T"}')
  renderPanel({ files: [{ path: 'blueprint.json' }], template: 'custom' })
  expect(await screen.findByText(NO_TARGETS_LINE)).toBeInTheDocument()
})

test('no such line when the template has bands, or when there are targets', async () => {
  mockTemplates()
  mockFile('blueprint.json', '{"title":"T"}')
  renderPanel({ files: [{ path: 'blueprint.json' }], template: 'article' })
  expect(await screen.findByText('T')).toBeInTheDocument()
  expect(screen.queryByText(NO_TARGETS_LINE)).toBeNull()
})

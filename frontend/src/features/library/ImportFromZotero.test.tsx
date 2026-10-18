// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, type MockInstance, test, vi } from 'vitest'
import { api, type ImportPreview, type ImportProgress, type ImportResult } from '@/api/client'
import * as clipboard from '@/lib/clipboard'
import { ImportFromZoteroButton } from './ImportFromZoteroButton'

vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })

const preview = (over: Partial<ImportPreview> = {}): ImportPreview => ({
  total: 12, already_in_library: 3, with_bundled_pdf: 5, would_fetch: 4, cannot_import_without_fetch: 0,
  disclosure: 'Fetching contacts free-copy sources by DOI for 4 entries.', ...over,
})
const result = (over: Partial<ImportResult> = {}): ImportResult => ({
  imported: 7, already_in_library: 3, pdfs_attached: 5, notes: 2, needs_pdf: [], failed: [], not_reached: [], stopped: '', ...over,
})
const progress = (over: Partial<ImportProgress> = {}): ImportProgress => ({ state: 'finished', result: result(), ...over })

const file = new File(['@article{a}'], 'refs.bib')
let previewSpy: MockInstance<typeof api.previewImport>
let startSpy: MockInstance<typeof api.startImport>

beforeEach(() => {
  previewSpy = vi.spyOn(api, 'previewImport').mockResolvedValue(preview())
  startSpy = vi.spyOn(api, 'startImport').mockResolvedValue(progress())
})
afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.useRealTimers()
})

function open(workspaceId?: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const view = render(
    <QueryClientProvider client={client}>
      <ImportFromZoteroButton workspaceId={workspaceId} />
    </QueryClientProvider>,
  )
  fireEvent.click(screen.getByRole('button', { name: 'Import from Zotero' }))
  return { client, view }
}
const invalidated = (client: QueryClient) => vi.spyOn(client, 'invalidateQueries')
const pick = () => fireEvent.change(screen.getByLabelText('References file'), { target: { files: [file] } })
const importButton = () => screen.getByRole('button', { name: 'Import' })

test('steps: the file input accepts the four kinds and the helper names both limits', () => {
  open()
  const input = screen.getByLabelText('References file') as HTMLInputElement
  expect(input.accept).toBe('.bib,.ris,.json,.zip')
  expect(screen.getByText(/20 MB/)).toBeTruthy()
  expect(screen.getByText(/200 MB/)).toBeTruthy()
  expect((importButton() as HTMLButtonElement).disabled).toBe(true)
  expect((screen.getByRole('switch', { name: /Fetch free PDFs/ }) as HTMLElement).getAttribute('aria-checked')).toBe('true')
})

test('the preview is said in words, with the disclosure above the Import button when something will be fetched', async () => {
  open()
  pick()
  expect(await screen.findByText(/12 references/)).toBeTruthy()
  expect(screen.getByText(/3 already in your library/)).toBeTruthy()
  expect(screen.getByText(/5 with a PDF in the zip/)).toBeTruthy()
  const disclosure = screen.getByText(preview().disclosure!)
  expect(disclosure.compareDocumentPosition(importButton()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(previewSpy).toHaveBeenCalledWith(file, undefined, true)
})

test('no disclosure when nothing will be fetched; turning the switch off re-runs the preview', async () => {
  previewSpy.mockImplementation(async (_f, _w, fetchPdfs) =>
    fetchPdfs ? preview() : preview({ would_fetch: 0, disclosure: null }))
  open()
  pick()
  await screen.findByText(/Fetching contacts/)
  fireEvent.click(screen.getByRole('switch', { name: /Fetch free PDFs/ }))
  await waitFor(() => expect(previewSpy).toHaveBeenLastCalledWith(file, undefined, false))
  await waitFor(() => expect(screen.queryByText(/Fetching contacts/)).toBeNull())
})

test('from a workspace the workspace target is preselected and sent', async () => {
  open('w1')
  expect((screen.getByLabelText('This workspace') as HTMLInputElement).checked).toBe(true)
  pick()
  await screen.findByText(/12 references/)
  expect(previewSpy).toHaveBeenCalledWith(file, 'w1', true)
  fireEvent.click(importButton())
  await screen.findByText(/7 new papers/)
  expect(startSpy).toHaveBeenCalledWith(file, { workspaceId: 'w1' }, true)
})

test('a new workspace needs a name and sends it', async () => {
  open()
  pick()
  fireEvent.click(screen.getByLabelText('A new workspace'))
  await screen.findByText(/12 references/)
  expect((importButton() as HTMLButtonElement).disabled).toBe(true)
  fireEvent.change(screen.getByLabelText('Workspace name'), { target: { value: 'Sleep' } })
  fireEvent.click(importButton())
  await screen.findByText(/7 new papers/)
  expect(startSpy).toHaveBeenCalledWith(file, { newWorkspaceName: 'Sleep' }, true)
})

test('an inline result is summarised in words', async () => {
  open()
  pick()
  await screen.findByText(/12 references/)
  fireEvent.click(importButton())
  const summary = await screen.findByText(/7 new papers/)
  expect(summary.textContent).toMatch(/3 were already in your library/)
  expect(summary.textContent).toMatch(/5 PDFs attached/)
  expect(summary.textContent).toMatch(/2 notes/)
})

test('202 polls every 2 seconds with a progress line, then shows the result', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  startSpy.mockResolvedValue({ state: 'queued', job_id: 'j1' })
  const poll = vi.spyOn(api, 'importProgress')
    .mockResolvedValueOnce({ state: 'running', job_id: 'j1', counts: { total: 10, done: 4, imported: 3, already_in_library: 1, pdfs_attached: 2, notes: 0, needs_pdf: 0, failed: 0 } } as ImportProgress)
    .mockResolvedValue(progress())
  open()
  pick()
  await screen.findByText(/12 references/)
  fireEvent.click(importButton())
  expect(await screen.findByText(/4 of 10/)).toBeTruthy()
  expect(screen.getByRole('status').textContent).toMatch(/4 of 10/)
  await act(() => vi.advanceTimersByTimeAsync(2100))
  await screen.findByText(/7 new papers/)
  const calls = poll.mock.calls.length
  await act(() => vi.advanceTimersByTimeAsync(6000))
  expect(poll.mock.calls.length).toBe(calls) // stopped on the terminal state
})

test.each([
  ['restarted', 'PaperLab restarted before it finished.'],
  ['expired', 'That import is too old to look up.'],
  ['unavailable', 'Progress can not be read just now.'],
  ['failed', 'The import broke: disk full.'],
] as const)('%s shows its message and Try again resubmits the same file', async (state, message) => {
  startSpy.mockResolvedValueOnce({ state, message, result: null })
  open()
  pick()
  await screen.findByText(/12 references/)
  fireEvent.click(importButton())
  expect(await screen.findByText(message)).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
  await screen.findByText(/7 new papers/)
  expect(startSpy).toHaveBeenCalledTimes(2)
  expect(startSpy.mock.calls[1][0]).toBe(file)
})

test.each([
  [413, 'That file is over the 20 MB limit.'],
  [422, 'No references found in that file.'],
])('a %s on import is shown plainly in the dialog', async (_code, message) => {
  startSpy.mockRejectedValue(new Error(message))
  open()
  pick()
  await screen.findByText(/12 references/)
  fireEvent.click(importButton())
  expect((await screen.findByRole('alert')).textContent).toContain(message)
})

test('a refused preview is shown plainly and does not block importing', async () => {
  previewSpy.mockRejectedValue(new Error('That file is over the 200 MB limit.'))
  open()
  pick()
  expect((await screen.findByRole('alert')).textContent).toContain('200 MB limit')
})

test('needs-a-PDF and couldn\'t-import lists, and Copy list copies title and DOI link', async () => {
  const copy = vi.spyOn(clipboard, 'copyText').mockResolvedValue()
  startSpy.mockResolvedValue(progress({
    result: result({
      needs_pdf: [
        { title: 'Sleep and memory', doi: '10.1/abc', tried: [], free_copies: [] },
        { title: 'No DOI paper', tried: [], free_copies: [] },
      ] as unknown as ImportResult['needs_pdf'],
      failed: [{ title: 'Broken entry', reason: 'No title' }],
    }),
  }))
  open()
  pick()
  await screen.findByText(/12 references/)
  fireEvent.click(importButton())
  await screen.findByText(/Needs a PDF \(2\)/)
  const link = screen.getByRole('link', { name: '10.1/abc' })
  expect(link.getAttribute('href')).toBe('https://doi.org/10.1/abc')
  expect(screen.getByText(/Couldn't import \(1\)/)).toBeTruthy()
  expect(screen.getByText(/No title/)).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: 'Copy list' }))
  await waitFor(() => expect(copy).toHaveBeenCalledWith('Sleep and memory - https://doi.org/10.1/abc\nNo DOI paper'))
})

test('Import waits for the preview of the current inputs, and keeps the old one visible meanwhile', async () => {
  open()
  pick()
  await screen.findByText(/Fetching contacts/)
  let release!: (p: ImportPreview) => void
  previewSpy.mockReturnValue(new Promise((resolve) => { release = resolve }))
  fireEvent.click(screen.getByRole('switch', { name: /Fetch free PDFs/ }))
  await waitFor(() => expect((importButton() as HTMLButtonElement).disabled).toBe(true))
  expect(screen.getByText(/12 references/)).toBeTruthy()
  expect(screen.getByText(/Updating/)).toBeTruthy()
  await act(async () => release(preview({ would_fetch: 0, disclosure: null })))
  await waitFor(() => expect((importButton() as HTMLButtonElement).disabled).toBe(false))
  expect(screen.queryByText(/Updating/)).toBeNull()
})

test('a preview error still lets you import', async () => {
  previewSpy.mockRejectedValue(new Error('Could not read it.'))
  open()
  pick()
  await screen.findByRole('alert')
  expect((importButton() as HTMLButtonElement).disabled).toBe(false)
})

test('with the switch off, entries that would be left out are said in words', async () => {
  previewSpy.mockResolvedValue(preview({ would_fetch: 0, disclosure: null, cannot_import_without_fetch: 3 }))
  open()
  pick()
  fireEvent.click(screen.getByRole('switch', { name: /Fetch free PDFs/ }))
  expect(await screen.findByText(/3 references have no PDF in the file and won't be imported unless fetching is on/)).toBeTruthy()
})

test('a file over its cap is refused before any upload', async () => {
  open()
  const big = new File(['x'], 'big.bib')
  Object.defineProperty(big, 'size', { value: 21 * 1024 * 1024 })
  fireEvent.change(screen.getByLabelText('References file'), { target: { files: [big] } })
  expect((await screen.findByRole('alert')).textContent).toContain('20 MB')
  expect(previewSpy).not.toHaveBeenCalled()
  expect((importButton() as HTMLButtonElement).disabled).toBe(true)
  const zip = new File(['x'], 'big.zip')
  Object.defineProperty(zip, 'size', { value: 150 * 1024 * 1024 })
  fireEvent.change(screen.getByLabelText('References file'), { target: { files: [zip] } })
  await screen.findByText(/12 references/)
})

test('a state with no server message falls back to words', async () => {
  startSpy.mockResolvedValueOnce({ state: 'restarted', result: null })
  open()
  pick()
  await screen.findByText(/12 references/)
  fireEvent.click(importButton())
  expect(await screen.findByText('PaperLab restarted before the import finished.')).toBeTruthy()
})

test('the finished result is announced and takes focus on its heading', async () => {
  open()
  pick()
  await screen.findByText(/12 references/)
  fireEvent.click(importButton())
  const heading = await screen.findByRole('heading', { name: 'Import finished' })
  expect(document.activeElement).toBe(heading)
  expect(heading.closest('[aria-live]')).toBeTruthy()
})

test('a closed running import says it keeps running, and closing refreshes papers and workspaces', async () => {
  startSpy.mockResolvedValue({ state: 'queued', job_id: 'j1' })
  vi.spyOn(api, 'importProgress').mockResolvedValue({ state: 'running', job_id: 'j1' } as ImportProgress)
  const { client, view } = open()
  const spy = invalidated(client)
  pick()
  await screen.findByText(/12 references/)
  fireEvent.click(importButton())
  expect(await screen.findByText(/keeps running/)).toBeTruthy()
  view.unmount()
  expect(spy).toHaveBeenCalledWith({ queryKey: ['papers'] })
  expect(spy).toHaveBeenCalledWith({ queryKey: ['workspaces'] })
})

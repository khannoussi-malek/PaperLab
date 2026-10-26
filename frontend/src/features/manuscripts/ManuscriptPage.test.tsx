// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { api, ApiError, type ManuscriptDetail } from '@/api/client'
import { ManuscriptPage } from './ManuscriptPage'

// jsdom can't host CodeMirror (no layout), so the editor is a textarea with the same props.
vi.mock('./LatexEditor', () => ({
  LatexEditor: ({ value, onChange }: { value: string; onChange: (v: string) => void }) => (
    <textarea aria-label="LaTeX source" value={value} onChange={(e) => onChange(e.target.value)} />
  ),
}))
vi.mock('@/components/AppShell', () => ({
  AppShell: ({ title, actions, status, children }: { title: string; actions?: React.ReactNode; status?: React.ReactNode; children: React.ReactNode }) => (
    <div><h1>{title}</h1>{actions}<main>{children}</main>{status}</div>
  ),
}))
vi.mock('../reader/usePdfDocument', () => ({ usePdfDocument: () => ({ doc: null, error: null }) }))
vi.mock('../reader/PdfPage', () => ({ PdfPage: () => null }))

const detail = (over: Partial<ManuscriptDetail> = {}): ManuscriptDetail => ({
  id: 'm1', workspace_id: 'w1', title: 'Thesis', main_file: 'main.tex', checklist: {}, compile_status: 'idle',
  compile_requested: false, compiled_at: null, compile_log: null, compile_errors: [],
  created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-02T00:00:00Z',
  files: [{ path: 'main.tex', size: 5, updated_at: '2026-10-02T00:00:00Z' }], ...over,
})

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><ManuscriptPage manuscriptId="m1" file={null} /></QueryClientProvider>)
}

async function typeAndSave(text: string) {
  const box = await screen.findByLabelText('LaTeX source')
  await waitFor(() => expect(box).toHaveValue('hello'))
  fireEvent.change(box, { target: { value: text } })
  fireEvent.keyDown(box, { key: 's', ctrlKey: true })
}

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
  vi.spyOn(api, 'getManuscript').mockResolvedValue(detail())
  vi.spyOn(api, 'getManuscriptFile').mockResolvedValue({ path: 'main.tex', text: 'hello', updated_at: '2026-10-02T00:00:00Z' })
  vi.spyOn(api, 'listManuscriptSnapshots').mockResolvedValue([])
})
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

test('shows the conflict banner with Reload', async () => {
  vi.spyOn(api, 'saveManuscriptFile').mockRejectedValue(
    new ApiError('file_changed', 409, { detail: 'file_changed', updated_at: '2026-10-03T00:00:00Z' }),
  )
  renderPage()
  await typeAndSave('hello world')
  const banner = await screen.findByRole('alert')
  expect(banner).toHaveTextContent('changed somewhere else')
  expect(screen.getByRole('button', { name: 'Reload' })).toBeInTheDocument()
  expect(screen.getByText('Changed in another tab')).toBeInTheDocument()
})

test('Ctrl+S saves then compiles', async () => {
  const order: string[] = []
  vi.spyOn(api, 'saveManuscriptFile').mockImplementation(async () => {
    order.push('save')
    return { path: 'main.tex', size: 11, updated_at: '2026-10-03T00:00:00Z' }
  })
  vi.spyOn(api, 'compileManuscript').mockImplementation(async () => {
    order.push('compile')
    return { state: 'queued' }
  })
  renderPage()
  await typeAndSave('hello world')
  await waitFor(() => expect(order).toEqual(['save', 'compile']))
  expect(api.saveManuscriptFile).toHaveBeenCalledWith('m1', 'main.tex', 'hello world', '2026-10-02T00:00:00Z')
})

test('shows the friendly message for needs_download', async () => {
  vi.spyOn(api, 'getManuscript').mockResolvedValue(
    detail({ compile_status: 'failed', compile_log: "error: this bundle isn't cached", compiled_at: '2026-10-03T00:00:00Z' }),
  )
  renderPage()
  const alert = await screen.findByRole('alert')
  expect(alert).toHaveTextContent('LaTeX needs to download packages once. Connect to the internet and compile again.')
})

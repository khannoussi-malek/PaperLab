// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { api, ApiError, type Diagram } from '@/api/client'
import { DiagramDialog } from './DiagramDialog'
import type { InsertResult } from './useInsertBlock'

const urls = vi.hoisted(() => [] as (string | null)[])
vi.mock('@/features/reader/usePdfDocument', () => ({
  usePdfDocument: (url: string | null) => {
    urls.push(url)
    return { doc: url ? { numPages: 1, getPage: async () => ({ getViewport: () => ({ width: 200, height: 80 }) }) } : null, error: null }
  },
}))
vi.mock('@/features/reader/PdfPage', () => ({ PdfPage: () => <div data-testid="pdf-page" /> }))
globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} }

const DESC = 'A pipeline: "Raw data" → "Cleaning" → "Model" → "Report"'
const PIC = '\\begin{tikzpicture}\n\\node {Raw data};\n\\end{tikzpicture}'
const row = (status: Diagram['status'], o: Partial<Diagram> = {}) =>
  ({ id: 'd1', description: DESC, status, code: null, libraries: [], compiled: null, errors: [], labels_not_in_description: [], reason: null, model: 'qwen', ai: true, created_at: 't0', updated_at: 't1', ...o }) as Diagram
const drawn = (o: Partial<Diagram> = {}) => row('done', { code: PIC, libraries: ['arrows.meta'], compiled: true, updated_at: 't2', ...o })
const remote = new ApiError('remote_model_needs_confirm', 409, { detail: 'remote_model_needs_confirm', model: 'Cloud', host: 'api.example.com' })

let create: ReturnType<typeof vi.fn>
let poll: ReturnType<typeof vi.fn>
let del: ReturnType<typeof vi.fn>
beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  urls.length = 0
  create = vi.spyOn(api, 'createDiagram').mockResolvedValue(row('queued')) as never
  poll = vi.spyOn(api, 'diagram').mockResolvedValue(drawn()) as never
  del = vi.spyOn(api, 'deleteDiagram').mockResolvedValue(undefined) as never
})
afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers() })

function setup(texts: () => string[] = () => [], insert = vi.fn(async (..._a: unknown[]): Promise<InsertResult> => ({ ok: true }))) {
  const onOpenChange = vi.fn()
  const view = render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
      <DiagramDialog open onOpenChange={onOpenChange} manuscriptId="m1" labelTexts={texts} onInsert={insert} />
    </QueryClientProvider>,
  )
  return { insert, onOpenChange, ...view }
}
const tick = () => act(() => vi.advanceTimersByTimeAsync(2100))
const button = (name: string) => screen.getByRole('button', { name })
async function generate(desc = DESC) {
  fireEvent.change(screen.getByLabelText('Describe your diagram in a few words'), { target: { value: desc } })
  await act(async () => fireEvent.click(button('Generate')))
  await tick()
}

test('a labelled dialog: the example and note show, and Generate needs a description', () => {
  setup()
  expect(screen.getByRole('dialog', { name: 'Draw a diagram' })).toBeInTheDocument()
  expect(screen.getByText('A pipeline: "Raw data" → "Cleaning" → "Model" → "Report"', { exact: false })).toBeInTheDocument()
  expect(screen.getByText("Use the words you want on the boxes — they're used as the labels.")).toBeInTheDocument()
  expect(button('Generate')).toBeDisabled()
  fireEvent.change(screen.getByLabelText('Describe your diagram in a few words'), { target: { value: '   ' } })
  expect(button('Generate')).toBeDisabled()
})

test('a remote model asks first, and Send starts with confirm_remote', async () => {
  create.mockRejectedValueOnce(remote)
  setup()
  await generate()
  expect(create).toHaveBeenCalledWith('m1', { description: DESC, confirm_remote: false })
  expect(screen.getByText('Your text will be sent to api.example.com and may cost money. Send it?')).toBeInTheDocument()
  await act(async () => fireEvent.click(button('Send')))
  expect(create).toHaveBeenLastCalledWith('m1', { description: DESC, confirm_remote: true })
})

test('a refused start says why in plain words', async () => {
  create.mockRejectedValueOnce(new ApiError('no_model', 409, { detail: 'no_model' }))
  setup()
  await generate()
  expect(screen.getByText('Add a model in Settings to draw a diagram.')).toBeInTheDocument()
})

test('progress with Cancel, then the preview (named, stamped by updated_at), the AI badge and Insert', async () => {
  poll.mockResolvedValueOnce(row('running')).mockResolvedValue(drawn())
  const cancel = vi.spyOn(api, 'cancelDiagram').mockResolvedValue(row('failed', { reason: 'cancelled' }))
  setup()
  fireEvent.change(screen.getByLabelText('Describe your diagram in a few words'), { target: { value: DESC } })
  await act(async () => fireEvent.click(button('Generate')))
  expect(screen.getByRole('status')).toHaveTextContent('Drawing your diagram…')
  expect(button('Cancel drawing')).toBeInTheDocument()
  expect(button('Insert')).toBeDisabled()
  await tick()
  await tick()
  expect(await screen.findByRole('img', { name: 'Diagram preview' })).toBeInTheDocument()
  expect(urls).toContain('/api/manuscripts/m1/diagrams/d1/pdf?v=t2')
  expect(screen.getByText('AI')).toBeInTheDocument()
  expect(button('Insert')).toBeEnabled()
  expect(cancel).not.toHaveBeenCalled()
})

test('Cancel drawing stops the run; a stopped run offers Regenerate, not the editor', async () => {
  poll.mockResolvedValue(row('running'))
  const cancel = vi.spyOn(api, 'cancelDiagram').mockResolvedValue(row('failed', { reason: 'cancelled' }))
  setup()
  await generate()
  await act(async () => fireEvent.click(button('Cancel drawing')))
  expect(cancel).toHaveBeenCalledWith('m1', 'd1')
  expect(screen.getByText('Stopped.')).toBeInTheDocument()
  expect(button('Regenerate')).toBeEnabled()
})

test.each([
  ['failed', 'model_error', "The model didn't give a usable answer. Try again or describe it differently."],
  ['interrupted', null, 'The diagram stopped before it finished. Try again.'],
] as const)('a %s generation (no code) offers Regenerate, never the LaTeX editor or Update preview', async (status, reason, words) => {
  poll.mockResolvedValue(row(status, { reason }))
  setup()
  await generate()
  expect(await screen.findByText(words)).toBeInTheDocument()
  expect(screen.queryByRole('tab', { name: 'LaTeX' })).toBeNull()
  expect(screen.queryByRole('textbox', { name: 'LaTeX' })).toBeNull()
  expect(screen.queryByRole('button', { name: 'Update preview' })).toBeNull()
  expect(button('Regenerate')).toBeEnabled()
  expect(button('Insert')).toBeDisabled()
})

test('a diagram that does not compile shows its errors with their line, and Insert stays disabled', async () => {
  poll.mockResolvedValue(drawn({ compiled: false, reason: 'compile_timeout', errors: [{ line: 3, message: 'Undefined control sequence.' }] }))
  setup()
  await generate()
  expect(await screen.findByText('The diagram took too long to draw.')).toBeInTheDocument()
  expect(screen.getByText('Line 3: Undefined control sequence.')).toBeInTheDocument()
  expect(screen.queryByRole('img', { name: 'Diagram preview' })).toBeNull()
  expect(button('Insert')).toBeDisabled()
})

test('the tabs follow the tab pattern; editing the code and Update preview re-polls and enables Insert once it compiles', async () => {
  poll.mockResolvedValue(drawn({ compiled: false, errors: [{ line: 2, message: 'Bad.' }] }))
  const put = vi.spyOn(api, 'setDiagramCode').mockResolvedValue(row('queued', { code: 'NEW', libraries: [] }))
  const { insert } = setup()
  await generate()
  const preview = screen.getByRole('tab', { name: 'Preview' })
  expect(preview).toHaveAttribute('aria-selected', 'true')
  act(() => preview.focus())
  fireEvent.keyDown(preview, { key: 'ArrowRight' })
  const latex = screen.getByRole('tab', { name: 'LaTeX' })
  await waitFor(() => expect(latex).toHaveAttribute('aria-selected', 'true'))
  const code = screen.getByRole('textbox', { name: 'LaTeX' })
  expect(code).toHaveValue(`\\usetikzlibrary{arrows.meta}\n${PIC}`)
  fireEvent.change(code, { target: { value: 'NEW' } })
  expect(button('Insert')).toBeDisabled()
  poll.mockReset().mockResolvedValueOnce(row('running', { code: 'NEW' })).mockResolvedValue(drawn({ code: 'NEW', libraries: [], updated_at: 't3' }))
  await act(async () => fireEvent.click(button('Update preview')))
  expect(put).toHaveBeenCalledWith('m1', 'd1', 'NEW')
  expect(screen.getByRole('status')).toHaveTextContent('Updating the preview…')
  await tick()
  await tick()
  await waitFor(() => expect(button('Insert')).toBeEnabled())
  expect(poll).toHaveBeenCalledTimes(2)
  expect(insert).not.toHaveBeenCalled()
})

test('labels that were not in the description are listed before insert', async () => {
  poll.mockResolvedValue(drawn({ labels_not_in_description: ['Storage', 'Cache'] }))
  setup()
  await generate()
  expect(await screen.findByText("These labels weren't in your description: Storage, Cache")).toBeInTheDocument()
})

test('Regenerate starts a new run from the same description and drops the old draft', async () => {
  create.mockResolvedValueOnce(row('queued')).mockResolvedValueOnce(row('queued', { id: 'd2' }))
  const { insert } = setup()
  await generate()
  await waitFor(() => expect(button('Regenerate')).toBeEnabled())
  await act(async () => fireEvent.click(button('Regenerate')))
  expect(create).toHaveBeenCalledTimes(2)
  expect(create).toHaveBeenLastCalledWith('m1', { description: DESC, confirm_remote: false })
  expect(del).toHaveBeenCalledWith('m1', 'd1')
  expect(insert).not.toHaveBeenCalled()
})

test('Insert calls onInsert once (even on a double click) with the AI-marked block and packages, closes and drops the draft; the same description again gets -2', async () => {
  const texts: string[] = []
  const insert = vi.fn(async (code: unknown): Promise<InsertResult> => { texts.push(code as string); return { ok: true } })
  const first = setup(() => texts, insert)
  await generate()
  await waitFor(() => expect(button('Insert')).toBeEnabled())
  await act(async () => { fireEvent.click(button('Insert')); fireEvent.click(button('Insert')) })
  expect(insert).toHaveBeenCalledTimes(1)
  expect(insert).toHaveBeenCalledWith(
    `% diagram drawn by PaperLab AI from your description\n\\begin{figure}[t]\n\\centering\n${PIC}\n\\caption{}\n\\label{fig:diagram-a-pipeline-raw-data}\n\\end{figure}`,
    ['tikz', 'tikzlibrary:arrows.meta'],
  )
  expect(first.onOpenChange).toHaveBeenCalledWith(false)
  expect(del).toHaveBeenCalledWith('m1', 'd1')
  first.unmount()

  setup(() => texts, insert)
  await generate()
  await waitFor(() => expect(button('Insert')).toBeEnabled())
  await act(async () => fireEvent.click(button('Insert')))
  expect(insert.mock.calls[1][0]).toContain('\\label{fig:diagram-a-pipeline-raw-data-2}')
})

test('a failed insert keeps the dialog, the draft and the code, and says why', async () => {
  const insert = vi.fn(async (): Promise<InsertResult> => ({ ok: false, message: 'The main file changed. Open it and try again.' }))
  const { onOpenChange } = setup(() => [], insert)
  await generate()
  await waitFor(() => expect(button('Insert')).toBeEnabled())
  await act(async () => fireEvent.click(button('Insert')))
  expect(screen.getByText('The main file changed. Open it and try again.')).toBeInTheDocument()
  expect(onOpenChange).not.toHaveBeenCalled()
  expect(del).not.toHaveBeenCalled()
  expect(button('Insert')).toBeEnabled()
  fireEvent.mouseDown(screen.getByRole('tab', { name: 'LaTeX' }))
  expect(await screen.findByRole('textbox', { name: 'LaTeX' })).toHaveValue(`\\usetikzlibrary{arrows.meta}\n${PIC}`)
})

test.each([
  ['Esc', () => fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })],
  ['Cancel', () => fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' }))],
])('%s deletes the draft and inserts nothing', async (_, close) => {
  const { insert, onOpenChange } = setup()
  await generate()
  await waitFor(() => expect(button('Insert')).toBeEnabled())
  await act(async () => close())
  expect(onOpenChange).toHaveBeenCalledWith(false)
  expect(del).toHaveBeenCalledWith('m1', 'd1')
  expect(insert).not.toHaveBeenCalled()
})

function pendingInsert() {
  let settle!: (r: InsertResult) => void
  const insert = vi.fn((..._a: unknown[]) => new Promise<InsertResult>((r) => { settle = r }))
  return { insert, settle: (r: InsertResult) => act(async () => settle(r)) }
}
const esc = () => fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
const cancelButton = () => fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Cancel' }))

test.each([['Esc', esc], ['Cancel', cancelButton]])('%s during an Insert is ignored; a successful insert then closes with one DELETE', async (_, close) => {
  const { insert, settle } = pendingInsert()
  const { onOpenChange } = setup(() => [], insert)
  await generate()
  await waitFor(() => expect(button('Insert')).toBeEnabled())
  await act(async () => fireEvent.click(button('Insert')))
  await act(async () => close())
  expect(onOpenChange).not.toHaveBeenCalled()
  expect(del).not.toHaveBeenCalled()
  await settle({ ok: true })
  expect(onOpenChange).toHaveBeenCalledTimes(1)
  expect(onOpenChange).toHaveBeenCalledWith(false)
  expect(del).toHaveBeenCalledTimes(1)
})

test('Esc during an Insert that then fails keeps the dialog and shows why', async () => {
  const { insert, settle } = pendingInsert()
  const { onOpenChange } = setup(() => [], insert)
  await generate()
  await waitFor(() => expect(button('Insert')).toBeEnabled())
  await act(async () => fireEvent.click(button('Insert')))
  await act(async () => esc())
  await settle({ ok: false, message: 'The main file changed. Open it and try again.' })
  expect(screen.getByText('The main file changed. Open it and try again.')).toBeInTheDocument()
  expect(onOpenChange).not.toHaveBeenCalled()
  expect(del).not.toHaveBeenCalled()
})

test('a poll that fails stops the spinner and says the run was lost', async () => {
  poll.mockRejectedValue(new Error('404'))
  setup()
  await generate()
  expect(await screen.findByText('PaperLab lost touch with this run. Close and try again.')).toBeInTheDocument()
  expect(screen.getByRole('status')).not.toHaveTextContent('Drawing your diagram…')
  expect(screen.queryByRole('button', { name: 'Cancel drawing' })).toBeNull()
})

test('one polite status region, there before Generate, goes from drawing to done', async () => {
  poll.mockResolvedValueOnce(row('running')).mockResolvedValue(drawn())
  setup()
  const region = screen.getByRole('status')
  expect(region).toHaveTextContent(/^$/)
  fireEvent.change(screen.getByLabelText('Describe your diagram in a few words'), { target: { value: DESC } })
  await act(async () => fireEvent.click(button('Generate')))
  expect(screen.getByRole('status')).toBe(region)
  expect(region).toHaveTextContent('Drawing your diagram…')
  await tick()
  await tick()
  await waitFor(() => expect(region).toHaveTextContent('Your diagram is ready.'))
  expect(screen.getByRole('status')).toBe(region)
})

test('the status region says so when a run fails', async () => {
  poll.mockResolvedValue(row('failed', { reason: 'model_error' }))
  setup()
  const region = screen.getByRole('status')
  await generate()
  await waitFor(() => expect(region).toHaveTextContent("Your diagram couldn't be drawn."))
})

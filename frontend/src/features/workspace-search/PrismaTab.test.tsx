// @vitest-environment jsdom
import { render, screen, fireEvent, within } from '@testing-library/react'
import { expect, test, vi, afterEach } from 'vitest'
import { PrismaTab } from './PrismaTab'
import * as queries from '@/api/queries'
import type { PrismaExportOut } from '@/api/client'

const combinedData: PrismaExportOut = {
  identified: 120,
  duplicates_removed: 20,
  stage1_screened: 100,
  stage1_excluded: 42,
  stage1_excluded_by_reason: { 'off topic': 42 },
  sought: 58,
  not_retrieved: 6,
  stage2_assessed: 52,
  stage2_excluded: 14,
  stage2_excluded_by_reason: { 'wrong population': 14 },
  included: 38,
  runs: [
    { id: 'run-1', query_text: 'transformer efficiency', filters_json: {}, started_at: '2026-09-24T00:00:00Z' },
    { id: 'run-2', query_text: 'llm evaluation', filters_json: {}, started_at: '2026-09-24T00:05:00Z' },
  ],
  automation: [],
  screening_criteria: null,
}

// Per-run export, mirroring the real backend (workspace_search.py:784): `runs` is always [] on this branch,
// since the caller already knows which run it asked for.
const perRunData: PrismaExportOut = {
  ...combinedData,
  identified: 60,
  included: 19,
  runs: [],
}

// Mirrors ScreeningTab.test.tsx's idiom: spy on the hook itself so the assertion can check the exact args
// usePrismaExport was re-invoked with, not just what the <select> displays. Keyed by the `runs` arg, like the
// real backend, so switching runs returns `runs: []` and the toggle test can catch a picker that desyncs.
function mockPrismaExport() {
  return vi.spyOn(queries, 'usePrismaExport').mockImplementation(
    (_workspaceId: string, runs: string) => ({ data: runs === 'all' ? combinedData : perRunData }) as ReturnType<typeof queries.usePrismaExport>,
  )
}

const realClipboard = Object.getOwnPropertyDescriptor(navigator, 'clipboard')
afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
  if (realClipboard) Object.defineProperty(navigator, 'clipboard', realClipboard)
  else delete (navigator as { clipboard?: unknown }).clipboard
})

test('shows the full funnel with counts from usePrismaExport', () => {
  mockPrismaExport()
  render(<PrismaTab workspaceId="ws-1" />)

  expect(screen.getByText('Identified')).toBeInTheDocument()
  expect(screen.getByText('120')).toBeInTheDocument()
  expect(screen.getByText('Duplicates removed')).toBeInTheDocument()
  expect(screen.getByText('20')).toBeInTheDocument()
  expect(screen.getByText('Screened on title & abstract')).toBeInTheDocument()
  expect(screen.getByText('100')).toBeInTheDocument()
  expect(screen.getByText('Excluded on title & abstract')).toBeInTheDocument()
  expect(screen.getByText('42')).toBeInTheDocument()
  expect(screen.getByText('Reports sought')).toBeInTheDocument()
  expect(screen.getByText('58')).toBeInTheDocument()
  expect(screen.getByText('Not retrieved')).toBeInTheDocument()
  expect(screen.getByText('6')).toBeInTheDocument()
  expect(screen.getByText('Full texts assessed')).toBeInTheDocument()
  expect(screen.getByText('52')).toBeInTheDocument()
  expect(screen.getByText('Excluded after full text')).toBeInTheDocument()
  expect(screen.getByText('14')).toBeInTheDocument()
  expect(screen.getByText('Included')).toBeInTheDocument()
  expect(screen.getByText('38')).toBeInTheDocument()
})

test('no raw reason code renders', () => {
  vi.spyOn(queries, 'usePrismaExport').mockImplementation(
    () => ({ data: { ...combinedData, stage1_excluded_by_reason: { wrong_topic: 6, unspecified: 1 } } }) as unknown as ReturnType<typeof queries.usePrismaExport>,
  )
  const { container } = render(<PrismaTab workspaceId="ws-1" />)
  expect(screen.getByText('Wrong topic: 6')).toBeInTheDocument()
  expect(screen.getByText('No reason given: 1')).toBeInTheDocument()
  expect(container.textContent).not.toMatch(/\b[a-z]+_[a-z_]+\b/)
})

test('the official box names carry explained terms', () => {
  mockPrismaExport()
  render(<PrismaTab workspaceId="ws-1" />)
  for (const name of ['Identified', 'Duplicates removed', 'Screened on title & abstract', 'Excluded on title & abstract', 'Reports sought', 'Not retrieved', 'Full texts assessed', 'Excluded after full text', 'Eligibility']) {
    expect(screen.getByRole('button', { name })).toBeInTheDocument()
  }
})

test('toggles between combined and a specific run, re-querying usePrismaExport with the new runs value', () => {
  const spy = mockPrismaExport()
  render(<PrismaTab workspaceId="ws-1" />)

  expect(spy).toHaveBeenCalledWith('ws-1', 'all')
  const select = screen.getByRole('combobox', { name: 'Runs' })
  expect(screen.getByRole('option', { name: 'llm evaluation' })).toBeInTheDocument()

  fireEvent.change(select, { target: { value: 'run-2' } })

  // Not toHaveBeenLastCalledWith: the component also holds a steady `usePrismaExport(workspaceId, 'all')`
  // call for the picker's own options (finding 1's fix), so the *last* render's last hook call stays 'all'.
  expect(spy).toHaveBeenCalledWith('ws-1', 'run-2')
})

test('run picker stays populated after selecting a run, even though the per-run export returns runs: []', () => {
  mockPrismaExport()
  render(<PrismaTab workspaceId="ws-1" />)

  const select = screen.getByRole('combobox', { name: 'Runs' })
  fireEvent.change(select, { target: { value: 'run-2' } })

  // The funnel numbers reflect the per-run export (runs: [])...
  expect(screen.getByText('19')).toBeInTheDocument()
  // ...but the picker's own options still come from the combined export, so every run stays
  // selectable and the controlled value still matches an existing option.
  expect((select as HTMLSelectElement).value).toBe('run-2')
  expect(screen.getByRole('option', { name: 'transformer efficiency' })).toBeInTheDocument()
  expect(screen.getByRole('option', { name: 'llm evaluation' })).toBeInTheDocument()

  fireEvent.change(select, { target: { value: 'run-1' } })
  expect((select as HTMLSelectElement).value).toBe('run-1')
})

// Item 5a: the reasons behind stage-1/stage-2 exclusions, straight off PrismaExportOut's own
// *_excluded_by_reason maps — no extra fetch.
test('shows the stage-1 and stage-2 exclusion reason breakdowns', () => {
  mockPrismaExport()
  render(<PrismaTab workspaceId="ws-1" />)

  expect(screen.getByText('off topic: 42')).toBeInTheDocument()
  expect(screen.getByText('wrong population: 14')).toBeInTheDocument()
})

// Item 5b: selecting a specific run shows that run's own recorded query/filters/date, from the combined
// export's `runs[]` metadata the picker already fetched — no extra request.
test("shows the selected run's query, filters and date from the combined export's runs metadata", () => {
  mockPrismaExport()
  render(<PrismaTab workspaceId="ws-1" />)

  // Nothing shown for the combined view — there's no single run to describe.
  expect(screen.queryByLabelText('Selected run details')).not.toBeInTheDocument()

  const select = screen.getByRole('combobox', { name: 'Runs' })
  fireEvent.change(select, { target: { value: 'run-2' } })

  const details = within(screen.getByLabelText('Selected run details'))
  expect(details.getByText('llm evaluation')).toBeInTheDocument()
  expect(details.getByText('2026-09-24T00:05:00Z')).toBeInTheDocument()
  expect(details.getByText('None')).toBeInTheDocument() // filters_json is {} for both fixture runs
})

// Item 5c: a loading state and an error state, same inline `role="alert"` pattern ScreeningTab/
// ManualAcquisitionTab use for their own mutation errors.
test('shows a loading state before the export arrives', () => {
  vi.spyOn(queries, 'usePrismaExport').mockReturnValue(
    { data: undefined, isPending: true, isError: false, error: null } as ReturnType<typeof queries.usePrismaExport>,
  )
  render(<PrismaTab workspaceId="ws-1" />)

  expect(screen.getByText(/loading/i)).toBeInTheDocument()
})

test('shows the error and a Retry that refetches when the export request fails', () => {
  const refetch = vi.fn()
  vi.spyOn(queries, 'usePrismaExport').mockReturnValue(
    {
      data: undefined, isPending: false, isError: true, error: new Error('Could not load the PRISMA export.'), refetch,
    } as unknown as ReturnType<typeof queries.usePrismaExport>,
  )
  render(<PrismaTab workspaceId="ws-1" />)

  expect(screen.getByRole('alert')).toHaveTextContent('Could not load the PRISMA export.')
  fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
  expect(refetch).toHaveBeenCalled()
})

test('lists methods notes: criteria and automation lines', () => {
  vi.spyOn(queries, 'usePrismaExport').mockReturnValue(
    {
      data: {
        ...combinedData,
        automation: ['Screening order was prioritised…'],
        screening_criteria: 'RCTs on sleep in adults',
      },
    } as ReturnType<typeof queries.usePrismaExport>,
  )
  render(<PrismaTab workspaceId="ws-1" />)

  const notes = screen.getByRole('region', { name: 'Methods notes' })
  expect(within(notes).getByText('RCTs on sleep in adults')).toBeInTheDocument()
  expect(within(notes).getByText('Screening order was prioritised…')).toBeInTheDocument()
})

test('shows no methods notes when there is nothing to report', () => {
  mockPrismaExport()
  render(<PrismaTab workspaceId="ws-1" />)

  expect(screen.getByText('Identified')).toBeInTheDocument()
  expect(screen.queryByRole('region', { name: 'Methods notes' })).toBeNull()
})

test('says plainly that identified is partial when a run was cut short (D266)', () => {
  vi.spyOn(queries, 'usePrismaExport').mockReturnValue(
    { data: { ...combinedData, notes: ['The identified count is partial: 1 search run(s) stopped at their time limit.'] } } as ReturnType<
      typeof queries.usePrismaExport
    >,
  )
  render(<PrismaTab workspaceId="ws-1" />)
  const notes = screen.getByRole('region', { name: 'Methods notes' })
  expect(within(notes).getByText(/identified count is partial/)).toBeInTheDocument()
})

test('while loading it shows a skeleton, not the empty copy', () => {
  vi.spyOn(queries, 'usePrismaExport').mockReturnValue({ data: undefined, isPending: true } as ReturnType<typeof queries.usePrismaExport>)
  render(<PrismaTab workspaceId="ws-1" />)
  expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true')
  expect(screen.queryByText('Your PRISMA flow will appear here')).not.toBeInTheDocument()
})

test('an empty workspace shows no zero funnel', () => {
  const empty: PrismaExportOut = {
    ...combinedData, identified: 0, duplicates_removed: 0, stage1_screened: 0, stage1_excluded: 0, stage1_excluded_by_reason: {},
    sought: 0, not_retrieved: 0, stage2_assessed: 0, stage2_excluded: 0, stage2_excluded_by_reason: {}, included: 0, runs: [],
  }
  vi.spyOn(queries, 'usePrismaExport').mockReturnValue({ data: empty } as ReturnType<typeof queries.usePrismaExport>)
  render(<PrismaTab workspaceId="ws-1" />)
  expect(screen.getByRole('heading', { name: 'Your PRISMA flow will appear here' })).toBeInTheDocument()
  expect(screen.getByText('It fills in as you search and screen.')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Go to 1 · Search & screen' })).toBeInTheDocument()
  expect(screen.queryByText('Identified')).not.toBeInTheDocument()
  expect(screen.queryByText('Runs')).not.toBeInTheDocument()
  expect(screen.queryByLabelText('Methods notes')).not.toBeInTheDocument()
})

function setClipboard(writeText: unknown) {
  Object.defineProperty(navigator, 'clipboard', { value: writeText === undefined ? undefined : { writeText }, configurable: true })
}

test('explains which papers count', () => {
  mockPrismaExport()
  render(<PrismaTab workspaceId="ws-1" />)
  expect(screen.getByText("Counts cover your search runs and their results. Papers added on the Papers tab aren't counted.")).toBeInTheDocument()
})

test('Copy as text says Copied', async () => {
  mockPrismaExport()
  const writeText = vi.fn().mockResolvedValue(undefined)
  setClipboard(writeText)
  render(<PrismaTab workspaceId="ws-1" />)
  fireEvent.click(screen.getByRole('button', { name: 'Copy as text' }))
  expect(await screen.findByRole('status')).toHaveTextContent('Copied')
  expect(writeText.mock.calls[0][0]).toContain('Identified: 120')
})

test.each([['rejects', vi.fn().mockRejectedValue(new Error('no'))], ['is missing', undefined]])(
  'a refused clipboard says so and shows the text (%s)',
  async (_n, writeText) => {
    mockPrismaExport()
    setClipboard(writeText)
    const { container } = render(<PrismaTab workspaceId="ws-1" />)
    fireEvent.click(screen.getByRole('button', { name: 'Copy as text' }))
    expect(await screen.findByText("Couldn't copy. Select the text instead.")).toBeInTheDocument()
    expect(screen.queryByText('Copied')).toBeNull()
    expect(container.querySelector('pre')?.textContent).toContain('Identified: 120')
  },
)

test('Download CSV offers a csv file', async () => {
  vi.useFakeTimers()
  mockPrismaExport()
  const create = vi.fn(() => 'blob:x')
  const revoke = vi.fn()
  Object.assign(URL, { createObjectURL: create, revokeObjectURL: revoke })
  let attached = false
  const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    expect(this.download).toBe('prisma-ws-1-all.csv')
    attached = document.body.contains(this)
  })
  render(<PrismaTab workspaceId="ws-1" />)
  fireEvent.click(screen.getByRole('button', { name: 'Download CSV' }))
  expect(click).toHaveBeenCalledTimes(1)
  expect(attached).toBe(true)
  expect(document.querySelector('a[download]')).toBeNull()
  const blob = (create.mock.calls[0] as unknown as [Blob])[0]
  expect(blob.type).toContain('text/csv')
  expect(revoke).not.toHaveBeenCalled()
  vi.advanceTimersByTime(1000)
  expect(revoke).toHaveBeenCalledWith('blob:x')
  vi.useRealTimers()
  // Blob.text() strips the BOM on decode, so check the raw bytes.
  expect([...new Uint8Array(await blob.arrayBuffer()).slice(0, 3)]).toEqual([0xef, 0xbb, 0xbf])
})

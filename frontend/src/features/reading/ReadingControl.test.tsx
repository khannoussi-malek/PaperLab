// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { api, type Paper, type TriageEvent } from '@/api/client'
import { ReadingControl } from './ReadingControl'

const paper = { id: 'p1', title: 'T', reading_pass: 0, triage: null } as unknown as Paper
const row = (id: string, over: Partial<TriageEvent>): TriageEvent =>
  ({ id, paper_id: 'p1', source: 'reader', pile: null, before_triage: null, after_triage: null, before_pass: 0, after_pass: 0,
    reason: null, pdf_opened: false, pdf_ms: null, created_at: new Date(2026, 9, 29, 10, 0).toISOString(), ...over }) as TriageEvent
const setup = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ReadingControl paper={paper} onOpenReferences={() => {}} />
    </QueryClientProvider>
  )
afterEach(() => vi.restoreAllMocks())

it('fetches the history only once the popover opens', async () => {
  const events = vi.spyOn(api, 'triageEvents').mockResolvedValue([])
  setup()
  expect(events).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: /Reading/ }))
  expect(await screen.findByText('No changes recorded yet.')).toBeInTheDocument()
  expect(events).toHaveBeenCalledTimes(1)
})

it('refetches the history after a decision, and the new row appears', async () => {
  const stored: TriageEvent[] = []
  vi.spyOn(api, 'triageEvents').mockImplementation(async () => [...stored])
  const put = vi.spyOn(api, 'setReading').mockImplementation(async () => {
    stored.push(row('e1', { after_triage: 'later' }))
    return { ...paper, triage: 'later' } as Paper
  })
  setup()
  fireEvent.click(screen.getByRole('button', { name: /Reading/ }))
  await screen.findByText('No changes recorded yet.')
  fireEvent.click(screen.getByRole('radio', { name: 'Later' }))
  await waitFor(() => expect(put).toHaveBeenCalledWith('p1', { triage: 'later' }, undefined))
  expect(await screen.findByText(/Undecided → Later · from the reader/)).toBeInTheDocument()
})

const setupExit = (over: Partial<Paper> = {}, props: Record<string, unknown> = {}) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ReadingControl paper={{ ...paper, ...over } as Paper} onOpenReferences={() => {}} {...props} />
    </QueryClientProvider>
  )

it('pass 0 shows the five Cs exit test under Done when', async () => {
  vi.spyOn(api, 'triageEvents').mockResolvedValue([])
  vi.spyOn(api, 'listNotes').mockResolvedValue([])
  vi.spyOn(api, 'listChecks').mockResolvedValue([])
  setupExit()
  fireEvent.click(screen.getByRole('button', { name: /Reading/ }))
  expect(await screen.findByText('Your five Cs: not written yet')).toBeInTheDocument()
})

it('at level 3 the reconstruction test sits under the finished line', async () => {
  vi.spyOn(api, 'triageEvents').mockResolvedValue([])
  vi.spyOn(api, 'listNotes').mockResolvedValue([])
  vi.spyOn(api, 'listChecks').mockResolvedValue([])
  setupExit({ reading_pass: 3 })
  fireEvent.click(screen.getByRole('button', { name: /Reading/ }))
  expect(screen.getByText(/finished all three passes/)).toBeInTheDocument()
  expect(await screen.findByText('Your reconstruction: not written yet')).toBeInTheDocument()
})

it('Write it closes the popover and passes the kind, and changes no level', async () => {
  vi.spyOn(api, 'triageEvents').mockResolvedValue([])
  vi.spyOn(api, 'listNotes').mockResolvedValue([])
  vi.spyOn(api, 'listChecks').mockResolvedValue([])
  const put = vi.spyOn(api, 'setReading')
  const onWriteNote = vi.fn()
  setupExit({}, { onWriteNote })
  fireEvent.click(screen.getByRole('button', { name: /Reading/ }))
  fireEvent.click(await screen.findByRole('button', { name: 'Write it' }))
  expect(onWriteNote).toHaveBeenCalledWith('five_cs')
  await waitFor(() => expect(screen.queryByText('Your five Cs: not written yet')).toBeNull())
  expect(put).not.toHaveBeenCalled()
})

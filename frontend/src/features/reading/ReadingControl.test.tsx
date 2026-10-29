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

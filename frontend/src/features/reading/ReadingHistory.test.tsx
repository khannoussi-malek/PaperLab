// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { api, type TriageEvent } from '@/api/client'
import { ReadingHistory } from './ReadingHistory'

const ev = (id: string, h: number, over: Partial<TriageEvent> = {}): TriageEvent => ({
  id, paper_id: 'p1', session_id: null, client_id: null, source: 'desk', pile: 'skim',
  before_triage: null, after_triage: 'keep', before_pass: 0, after_pass: 1, reason: null, note: null, fivecs: null,
  pdf_opened: false, pdf_ms: null, card_ms: null, undone_event_id: null, created_at: new Date(2026, 9, 29, h, 0).toISOString(), ...over,
})
const show = (enabled = true) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ReadingHistory paperId="p1" enabled={enabled} />
    </QueryClientProvider>
  )
afterEach(() => vi.restoreAllMocks())

it('lists the changes newest first in a labelled list', async () => {
  vi.spyOn(api, 'triageEvents').mockResolvedValue([ev('a', 9), ev('b', 15, { pile: 'later', after_triage: 'later' })])
  show()
  const items = await within(screen.getByRole('region', { name: 'History' })).findAllByRole('listitem')
  expect(items[0]).toHaveTextContent('29 Oct, 15:00 · Later')
  expect(items[1]).toHaveTextContent('29 Oct, 09:00 · Skim')
})

it('says so when nothing was recorded', async () => {
  vi.spyOn(api, 'triageEvents').mockResolvedValue([])
  show()
  expect(await screen.findByText('No changes recorded yet.')).toBeInTheDocument()
})

it('shows the shared error alert when the fetch fails', async () => {
  vi.spyOn(api, 'triageEvents').mockRejectedValue(new Error('boom'))
  show()
  expect(await screen.findByRole('alert')).toHaveTextContent('boom')
})

it('does not fetch while disabled', () => {
  const spy = vi.spyOn(api, 'triageEvents').mockResolvedValue([])
  show(false)
  expect(spy).not.toHaveBeenCalled()
})

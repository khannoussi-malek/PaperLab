// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { api, type Paper } from '@/api/client'
import { PaperProvenance } from './PaperProvenance'

afterEach(() => vi.restoreAllMocks())

const show = (over: Partial<Paper>, events: unknown[] = []) => {
  vi.spyOn(api, 'paperEvents').mockResolvedValue(events as never)
  const paper = { id: 'p1', has_pdf: false, field_sources: {}, manual_fields: [], ...over } as unknown as Paper
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <PaperProvenance paper={paper} />
    </QueryClientProvider>,
  )
}

it('lists where the details came from', () => {
  show({ field_sources: { bibliographic: 'openalex' } })
  expect(screen.getByText('Where these details came from')).toBeInTheDocument()
  expect(screen.getByText('Title, authors and venue: from OpenAlex')).toBeInTheDocument()
})

it('hides the section when no group has a source', () => {
  show({})
  expect(screen.queryByText('Where these details came from')).toBeNull()
})

it.each([
  ['none', 'none found'],
  ['found', 'found'],
  ['error', 'the check failed'],
] as const)('last checked, result %s', (result, text) => {
  show({ pdf_checked_at: '2026-10-14T12:00:00Z', pdf_check_result: result })
  expect(screen.getByText(new RegExp(`^Last checked for a free copy: .+, ${text}$`))).toBeInTheDocument()
})

it('has no last-checked line for a paper with a PDF', () => {
  show({ has_pdf: true, pdf_checked_at: '2026-10-14T12:00:00Z', pdf_check_result: 'none' })
  expect(screen.queryByText(/Last checked/)).toBeNull()
})

it('lists the history, newest first as served', async () => {
  show({}, [
    { id: 'e2', kind: 'pdf_attached', detail: { how: 'found' }, created_at: '2026-10-15T12:00:00Z' },
    { id: 'e1', kind: 'pdf_found', detail: {}, created_at: '2026-10-14T12:00:00Z' },
    { id: 'e0', kind: 'pdf_attached', detail: { how: 'uploaded' }, created_at: '2026-10-13T12:00:00Z' },
  ])
  const items = await screen.findAllByRole('listitem')
  expect(items.map((li) => li.textContent)).toEqual([
    expect.stringMatching(/^PDF added .+ \(found\)$/),
    expect.stringMatching(/^Free PDF found /),
    expect.stringMatching(/^PDF added .+ \(uploaded\)$/),
  ])
})

it('hides History when there are no events', async () => {
  show({})
  await vi.waitFor(() => expect(api.paperEvents).toHaveBeenCalled())
  expect(screen.queryByText('History')).toBeNull()
})

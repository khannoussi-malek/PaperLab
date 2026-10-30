// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { api } from '@/api/client'
import { TriageDone } from './TriageDone'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

const SUMMARY = { per_pile: { read_closely: 12, skim: 20, later: 8, not_relevant: 6 }, skipped: 3, card_ms: 14 * 60_000 + 20_000, pdf_opened: 31, decided: 46 }
function show(over = {}) {
  vi.spyOn(api, 'triageSummary').mockResolvedValue(SUMMARY as never)
  const p = { sessionId: 's1', skipped: 3, canReviewSkipped: true, canStartOver: true, newSince: 0, undo: { label: "Skim 'Lewis 2020'", count: 2 }, onUndo: vi.fn(), onReviewSkipped: vi.fn(), onShowKept: vi.fn(), onAddNew: vi.fn(), onStartOver: vi.fn(), onBack: vi.fn(), ...over }
  render(<QueryClientProvider client={new QueryClient()}><TriageDone {...p} /></QueryClientProvider>)
  return p
}

it('reports the session in the piles\' own words, with the time and the PDF fact', async () => {
  show()
  expect(await screen.findByText('12 Read closely')).toBeInTheDocument()
  expect(screen.getByText('20 Skim')).toBeInTheDocument()
  expect(screen.getByText('8 Later')).toBeInTheDocument()
  expect(screen.getByText('6 Not relevant')).toBeInTheDocument()
  expect(screen.getByText('3 skipped')).toBeInTheDocument()
  expect(screen.getByText('about 14 min')).toBeInTheDocument()
  expect(screen.getByText('PDF opened for 31 of 46')).toBeInTheDocument()
})

it('offers Review the skipped only when any, and disables it while a write is pending', () => {
  const p = show()
  fireEvent.click(screen.getByRole('button', { name: 'Review the skipped (3)' }))
  expect(p.onReviewSkipped).toHaveBeenCalled()
  cleanup()
  show({ canReviewSkipped: false })
  expect(screen.getByRole('button', { name: 'Review the skipped (3)' })).toBeDisabled()
  cleanup()
  show({ skipped: 0 })
  expect(screen.queryByRole('button', { name: /Review the skipped/ })).toBeNull()
})

it('Add N new papers only when there are some; the other buttons call back', () => {
  const p = show({ newSince: 2 })
  fireEvent.click(screen.getByRole('button', { name: 'Add 2 new papers' }))
  fireEvent.click(screen.getByRole('button', { name: 'Show kept papers in the list' }))
  fireEvent.click(screen.getByRole('button', { name: 'Back to the list' }))
  fireEvent.click(screen.getByRole('button', { name: /Undo: Skim 'Lewis 2020'/ }))
  expect([p.onAddNew, p.onShowKept, p.onBack, p.onUndo].map((f) => f.mock.calls.length)).toEqual([1, 1, 1, 1])
  cleanup()
  show()
  expect(screen.queryByRole('button', { name: /new paper/ })).toBeNull()
})

it('says "1 new paper" for one', () => {
  show({ newSince: 1 })
  expect(screen.getByRole('button', { name: 'Add 1 new paper' })).toBeInTheDocument()
})

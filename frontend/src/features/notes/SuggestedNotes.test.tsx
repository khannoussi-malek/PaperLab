// @vitest-environment jsdom
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { SuggestedNotes } from './SuggestedNotes'
import { api, type Note, type NoteSuggestionsOut } from '@/api/client'

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return { client, ...render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>) }
}

const result: NoteSuggestionsOut = {
  output_id: 'output-1',
  suggestions: [
    { body: 'First suggested note.', chunk_id: 'chunk-1', page: 1, section: null, bbox: [] },
    { body: 'Second suggested note.', chunk_id: 'chunk-2', page: 2, section: null, bbox: [] },
  ],
}

beforeEach(() => {
  vi.spyOn(api, 'suggestNotes')
  vi.spyOn(api, 'promoteNote')
})

afterEach(() => {
  vi.restoreAllMocks()
})

test('clicking "Suggest notes" shows each suggestion as its own card', async () => {
  vi.spyOn(api, 'suggestNotes').mockResolvedValue(result)
  renderWithClient(<SuggestedNotes paperId="p1" />)

  fireEvent.click(screen.getByRole('button', { name: 'Suggest notes' }))

  expect(await screen.findByText('First suggested note.')).toBeInTheDocument()
  expect(screen.getByText('Second suggested note.')).toBeInTheDocument()
  expect(api.suggestNotes).toHaveBeenCalledWith('p1')
})

const promotedNote: Note = {
  id: 'note-1', body: 'First suggested note.', provenance: 'llm', color: '#fff', source_id: 'output-1',
  created_at: '2026-09-24T00:00:00Z', updated_at: '2026-09-24T00:00:00Z', anchors: [], charts: [],
}

test('accepting a suggestion promotes it through the existing endpoint and removes its card', async () => {
  vi.spyOn(api, 'suggestNotes').mockResolvedValue(result)
  vi.spyOn(api, 'promoteNote').mockResolvedValue(promotedNote)
  renderWithClient(<SuggestedNotes paperId="p1" />)
  fireEvent.click(screen.getByRole('button', { name: 'Suggest notes' }))
  await screen.findByText('First suggested note.')

  const [firstAccept] = screen.getAllByRole('button', { name: 'Accept' })
  fireEvent.click(firstAccept)

  await waitFor(() =>
    expect(api.promoteNote).toHaveBeenCalledWith({
      output_id: 'output-1', body: 'First suggested note.', chunk_ids: ['chunk-1'],
    }),
  )
  await waitFor(() => expect(screen.queryByText('First suggested note.')).not.toBeInTheDocument())
  expect(screen.getByText('Second suggested note.')).toBeInTheDocument() // the other card is untouched
})

test('dismissing a suggestion removes its card without calling the API', async () => {
  vi.spyOn(api, 'suggestNotes').mockResolvedValue(result)
  renderWithClient(<SuggestedNotes paperId="p1" />)
  fireEvent.click(screen.getByRole('button', { name: 'Suggest notes' }))
  await screen.findByText('First suggested note.')

  const [firstDismiss] = screen.getAllByRole('button', { name: 'Dismiss' })
  fireEvent.click(firstDismiss)

  expect(screen.queryByText('First suggested note.')).not.toBeInTheDocument()
  expect(screen.getByText('Second suggested note.')).toBeInTheDocument()
  expect(api.promoteNote).not.toHaveBeenCalled()
})

test('no suggestions says so instead of showing nothing', async () => {
  vi.spyOn(api, 'suggestNotes').mockResolvedValue({ output_id: 'output-1', suggestions: [] })
  renderWithClient(<SuggestedNotes paperId="p1" />)

  fireEvent.click(screen.getByRole('button', { name: 'Suggest notes' }))

  expect(await screen.findByRole('status')).toHaveTextContent('Nothing stood out')
})

test('a failed generation shows an error message', async () => {
  vi.spyOn(api, 'suggestNotes').mockRejectedValue(new Error('Suggest failed'))
  renderWithClient(<SuggestedNotes paperId="p1" />)

  fireEvent.click(screen.getByRole('button', { name: 'Suggest notes' }))

  expect(await screen.findByRole('alert')).toHaveTextContent('Suggest failed')
})

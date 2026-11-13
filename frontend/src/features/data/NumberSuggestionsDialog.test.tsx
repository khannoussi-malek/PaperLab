// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import { api } from '@/api/client'
import { NumberSuggestionsDialog } from './NumberSuggestionsDialog'

const suggestion = {
  label: 'Accuracy (ours)', raw: '92.3', unit: '%', quote: 'reaches an accuracy of 92.3% on the test set', page: 5,
  bbox: [[72, 200, 300, 220]] as [number, number, number, number][],
}

function open() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <NumberSuggestionsDialog paperId="p1" sectionTitle="5 Results" onClose={() => {}} />
    </QueryClientProvider>,
  )
}

test('lists what the model found with its quote, and Add saves it marked as a suggestion', async () => {
  const suggest = vi.spyOn(api, 'suggestNumbers').mockResolvedValue({ suggestions: [suggestion], dropped: 2 })
  const add = vi.spyOn(api, 'addNumber').mockResolvedValue({ dataset_id: 'd1', row_id: 'r1' })
  open()
  expect(await screen.findByText('Accuracy (ours)')).toBeInTheDocument()
  expect(suggest).toHaveBeenCalledWith('p1', '5 Results')
  expect(screen.getByText(/reaches an accuracy of 92.3% on the test set/)).toBeInTheDocument()
  expect(screen.getByText(/2 more weren’t kept/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Add Accuracy (ours)' }))
  await waitFor(() => expect(add).toHaveBeenCalledWith('p1', {
    label: 'Accuracy (ours)', raw: '92.3', unit: '%', page: 5, bbox: suggestion.bbox, suggested: true,
  }))
  expect(await screen.findByText('Added')).toBeInTheDocument()
})

test('a section with nothing to suggest says so', async () => {
  vi.spyOn(api, 'suggestNumbers').mockResolvedValue({ suggestions: [], dropped: 0 })
  open()
  expect(await screen.findByText('No numbers found in this section.')).toBeInTheDocument()
})

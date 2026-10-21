// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import type { Paper } from '@/api/client'
import { PaperDetailsPanel } from './PaperDetailsPanel'

test('the details panel of a paper without a PDF offers Upload PDF and Find free copy', () => {
  const paper = { id: 'p1', title: 'Sleep and memory', authors: [], year: null, venue: null, doi: null, abstract: 'A.', has_pdf: false, details_source: null, field_sources: {} } as unknown as Paper
  render(
    <QueryClientProvider client={new QueryClient()}>
      <PaperDetailsPanel paper={paper} />
    </QueryClientProvider>,
  )
  expect(screen.getByLabelText('Upload PDF for Sleep and memory')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Find free copy for Sleep and memory' })).toBeInTheDocument()
})

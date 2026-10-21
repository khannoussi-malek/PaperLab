// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { Paper } from '@/api/client'
import { PaperDetailsDialog } from './PaperDetailsDialog'

// jsdom has no ResizeObserver, which the Radix dialog's form controls ask for
globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} }

const open =  (over: Partial<Paper>) => {
  const paper = { id: 'p1', title: 'T', authors: [], abstract: '', manual_fields: [], field_sources: {}, has_pdf: true, ...over } as unknown as Paper
  render(
    <QueryClientProvider client={new QueryClient()}>
      <PaperDetailsDialog paper={paper} />
    </QueryClientProvider>,
  )
  fireEvent.click(screen.getByRole('button', { name: /edit details/i }))
}

describe('PaperDetailsDialog', () => {
  it('shows the published version with a DOI link', () => {
    open({ published_venue: 'STOC', published_doi: '10.1145/3717823.3718108' })
    expect(screen.getByText(/Published version: STOC/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '10.1145/3717823.3718108' })).toHaveAttribute(
      'href',
      'https://doi.org/10.1145/3717823.3718108',
    )
  })

  it('shows nothing about a published version when there is none', () => {
    open({})
    expect(screen.queryByText(/Published version/)).toBeNull()
  })
})

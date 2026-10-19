// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import type { Paper } from '@/api/client'
import { PaperPreview } from './PaperPreview'

const firstPage = vi.hoisted(() => vi.fn(() => null))
vi.mock('./FirstPage', () => ({ FirstPage: firstPage })) // the real one loads the PDF

const paper = (over: Partial<Paper>) =>
  ({
    id: 'p1', title: 'Sleep and memory', authors: ['Ada Lee'], year: 2020, venue: 'Sleep', page_count: null,
    status: 'ready', status_error: null, doi: null, abstract: 'Sleep helps memory.', created_at: '2026-10-18T10:00:00Z',
    has_pdf: true, details_source: null, ...over,
  }) as Paper

test('a paper without a PDF shows no first page: it says so, and leads with the abstract', () => {
  render(<PaperPreview paper={paper({ has_pdf: false, details_source: 'crossref' })} />)
  expect(firstPage).not.toHaveBeenCalled()
  expect(screen.getByText('No PDF yet')).toBeInTheDocument()
  expect(screen.getByText('Details from Crossref')).toBeInTheDocument()
  expect(screen.getByText('Sleep helps memory.')).toBeInTheDocument()
  expect(screen.queryByText(/Processing/)).toBeNull()
})

test('a ready paper with a PDF still shows its first page', () => {
  render(<PaperPreview paper={paper({})} />)
  expect(firstPage).toHaveBeenCalled()
  expect(screen.queryByText('No PDF yet')).toBeNull()
})

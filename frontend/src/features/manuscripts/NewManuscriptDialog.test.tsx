// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import { api } from '@/api/client'
import { NewManuscriptDialog } from './NewManuscriptDialog'

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
  vi.spyOn(api, 'listManuscriptTemplates').mockResolvedValue([
    { name: 'article', label: 'Plain article', official: false, provenance: '', page_limit: null, references_count: false, section_words: {} },
    { name: 'ieee', label: 'IEEE conference', official: true, provenance: '', page_limit: 6, references_count: true, section_words: {} },
    { name: 'acm', label: 'ACM (sigconf)', official: true, provenance: '', page_limit: 9, references_count: false, section_words: {} },
    { name: 'elsevier', label: 'Elsevier', official: true, provenance: '', page_limit: null, references_count: false, section_words: {} },
  ])
})
afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

function open() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <NewManuscriptDialog workspaceId={null} open onOpenChange={() => {}} />
    </QueryClientProvider>,
  )
}

test('each template says its page limit', async () => {
  open()
  expect(await screen.findByText('Page limit 6 pages, references included')).toBeInTheDocument()
  expect(screen.getByText('Page limit 9 pages, references not counted')).toBeInTheDocument()
})

test('an official template without a limit says only that', async () => {
  open()
  await screen.findByText('Elsevier')
  expect(screen.getByText('No page limit')).toBeInTheDocument()
})

test('an unlimited, unofficial template says so', async () => {
  open()
  await screen.findByText('Plain article')
  expect(screen.getByText("No page limit. Generic layout, not a venue's official style.")).toBeInTheDocument()
})

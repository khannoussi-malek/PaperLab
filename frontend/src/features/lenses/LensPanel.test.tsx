// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { Lens, Section } from '@/api/client'
import { LensPanel } from './LensPanel'
import { SectionRow } from './SectionRow'
import type { LensReader } from './useLensReader'

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} }

const section = (over: Partial<Section> = {}): Section =>
  ({ title: '2 Method', role: 'method', source: 'auto', page: 2, preview: 'We train.', first_chunk_id: 'c2', chunk_ids: ['c2'], ...over }) as Section
const lens = { id: 'full', label: 'Full paper', chunk_ids: ['c2'], positional_fallback: false, missing_roles: [] } as unknown as Lens

function panel(hasPdf: boolean, jumpToChunk = vi.fn()) {
  const reader = { lens, sections: [section()], sectionsQuery: { error: null }, jumpToChunk } as unknown as LensReader
  render(
    <QueryClientProvider client={new QueryClient()}>
      <LensPanel paperId="p1" reader={reader} hasPdf={hasPdf} />
    </QueryClientProvider>,
  )
  return jumpToChunk
}

describe('LensPanel', () => {
  it('without a PDF says only that lenses need one', () => {
    panel(false)
    expect(screen.getByRole('complementary', { name: 'Lens' })).toHaveTextContent(
      "Lenses read a paper's sections. Attach its PDF to use them.",
    )
    expect(screen.queryByRole('list', { name: 'Sections' })).toBeNull()
    expect(screen.queryByRole('heading')).toBeNull()
  })

  it('with a PDF lists the sections and jumps to the clicked one', () => {
    const jump = panel(true)
    expect(screen.getByRole('heading', { name: 'Full paper' })).toBeInTheDocument()
    fireEvent.click(screen.getByText('2 Method'))
    expect(jump).toHaveBeenCalledWith('c2')
  })
})

describe('SectionRow', () => {
  const row = (s: Section) =>
    render(<SectionRow section={s} busy={false} onJump={() => {}} onRoleChange={() => {}} />)

  it('marks a fixed role with "you" and shows its page', () => {
    row(section({ source: 'user' }))
    expect(screen.getByText('you')).toBeInTheDocument()
    expect(screen.getByText('p. 2')).toBeInTheDocument()
  })

  it('offers no menu on text before the first heading', () => {
    row(section({ title: null }))
    expect(screen.getByText('Before the first heading')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Section actions/ })).toBeNull()
  })
})

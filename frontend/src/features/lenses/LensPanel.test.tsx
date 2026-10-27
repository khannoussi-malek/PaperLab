// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { Lens, Role, Section } from '@/api/client'
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

describe('LensPanel states', () => {
  it('keeps the Lens region while the sections load', () => {
    const reader = { lens: null, sections: [], sectionsQuery: { error: null } } as unknown as LensReader
    render(<QueryClientProvider client={new QueryClient()}><LensPanel paperId="p1" reader={reader} hasPdf /></QueryClientProvider>)
    expect(screen.getByRole('complementary', { name: 'Lens' })).toHaveTextContent('Reading the sections')
  })

  it('keeps the Lens region when the sections fail to load', () => {
    const reader = { lens: null, sections: [], sectionsQuery: { error: new Error('boom'), refetch: vi.fn() } } as unknown as LensReader
    render(<QueryClientProvider client={new QueryClient()}><LensPanel paperId="p1" reader={reader} hasPdf /></QueryClientProvider>)
    expect(screen.getByRole('complementary', { name: 'Lens' })).toHaveTextContent('boom')
  })
})

describe('SectionRow', () => {
  const row = (s: Section, onRoleChange: (role: Role | null) => void = () => {}, busy = false) =>
    render(<SectionRow section={s} busy={busy} onJump={() => {}} onRoleChange={onRoleChange} />)
  const openMenu = () => fireEvent.keyDown(screen.getByRole('button', { name: 'Section actions for 2 Method, page 2' }), { key: 'Enter' })

  it('marks a fixed role with "you" and shows its page', () => {
    row(section({ source: 'user' }))
    expect(screen.getByText('you')).toBeInTheDocument()
    expect(screen.getByText('p. 2')).toBeInTheDocument()
  })

  it('shows "you" only for a role the reader fixed', () => {
    row(section({ source: 'keyword' }))
    expect(screen.queryByText('you')).toBeNull()
  })

  it('Change role reports the picked role, and Automatic reports null', () => {
    const onRoleChange = vi.fn()
    row(section({ source: 'user', role: 'results' }), onRoleChange)
    openMenu()
    expect(screen.getByRole('menuitemradio', { name: 'Results' })).toBeChecked()
    fireEvent.click(screen.getByRole('menuitemradio', { name: 'Conclusion' }))
    expect(onRoleChange).toHaveBeenLastCalledWith('conclusion')
    openMenu()
    fireEvent.click(screen.getByRole('menuitemradio', { name: 'Automatic' }))
    expect(onRoleChange).toHaveBeenLastCalledWith(null)
  })

  it('keeps the menu trigger enabled while a save is pending, so focus is not lost', () => {
    row(section(), () => {}, true)
    expect(screen.getByRole('button', { name: 'Section actions for 2 Method, page 2' })).not.toBeDisabled()
    openMenu()
    expect(screen.getByRole('menuitemradio', { name: 'Conclusion' })).toHaveAttribute('aria-disabled', 'true')
  })

  it('says what the "you" marker means', () => {
    row(section({ source: 'user' }))
    expect(screen.getByText('fixed by')).toBeInTheDocument()
  })

  it('names each menu by its heading and page, so a repeated heading still has a unique button', () => {
    render(
      <ul>
        <SectionRow section={section({ title: 'Results', page: 4, first_chunk_id: 'a' })} busy={false} onJump={() => {}} onRoleChange={() => {}} />
        <SectionRow section={section({ title: 'Results', page: 9, first_chunk_id: 'b' })} busy={false} onJump={() => {}} onRoleChange={() => {}} />
      </ul>,
    )
    expect(screen.getByRole('button', { name: 'Section actions for Results, page 4' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Section actions for Results, page 9' })).toBeInTheDocument()
  })

  it('offers no menu on text before the first heading', () => {
    row(section({ title: null }))
    expect(screen.getByText('Before the first heading')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Section actions/ })).toBeNull()
  })
})

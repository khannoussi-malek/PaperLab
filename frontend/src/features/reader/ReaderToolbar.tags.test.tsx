// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import type { Paper } from '@/api/client'
import { ReaderToolbar } from './ReaderToolbar'

vi.mock('../reading/ReadingControl', () => ({ ReadingControl: () => null }))
vi.mock('./PaperDetailsDialog', () => ({ PaperDetailsDialog: () => null }))
vi.mock('@/components/mode-toggle', () => ({ ModeToggle: () => null }))

const paper = { title: 'T', source_type: 'preprint', peer_reviewed: 'false', evidence_access: 'full_text' } as Paper
const renderToolbar = () =>
  render(<ReaderToolbar paper={paper} zoomIndex={0} onZoomChange={vi.fn()} capturing={false} onCaptureChange={vi.fn()} onOpenReferences={vi.fn()} tags={<i>chips</i>} />)

it('renders the tags it is given in the header group and in the small-screen row', () => {
  renderToolbar()
  const chips = screen.getAllByText('chips')
  expect(chips.some((c) => c.closest('header'))).toBe(true)
  expect(chips.some((c) => c.closest('.md\\:hidden'))).toBe(true)
})

// jsdom has no layout, so the squeeze itself can't be measured: pin the classes that prevent it.
it('caps and clips the header tag group so the title can shrink but never be squeezed out', () => {
  renderToolbar()
  const group = screen.getAllByText('chips').find((c) => c.closest('header'))!.parentElement!
  expect(group.className).toContain('max-w-[40%]')
  expect(group.className).toContain('overflow-hidden')
  expect(group.className).not.toContain('shrink-0')
  expect(screen.getByRole('heading', { level: 1 }).className).toContain('min-w-0')
})

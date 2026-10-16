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

it('shows the tags in their own wrapping row, and the header group only holds the source badges', () => {
  renderToolbar()
  const chips = screen.getByText('chips')
  expect(chips.closest('header')).toBeNull()
  const row = chips.parentElement!
  expect(row.className).toContain('flex-wrap')
  expect(row.className).toContain('md:has-[a]:flex')
  expect(row.className).toContain('md:hidden')
  expect(row.querySelector('span.md\\:hidden')).not.toBeNull()
})

it('keeps the header badge group from shrinking and lets the title be the one that shrinks', () => {
  renderToolbar()
  const group = document.querySelector('header .md\\:flex')!
  expect(group.className).toContain('shrink-0')
  expect(group.className).not.toContain('max-w')
  expect(group.textContent).not.toContain('chips')
  expect(screen.getByRole('heading', { level: 1 }).className).toContain('min-w-0')
})

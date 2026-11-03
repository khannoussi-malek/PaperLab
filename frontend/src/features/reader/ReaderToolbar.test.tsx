// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import type { Paper } from '@/api/client'
import { ReaderToolbar } from './ReaderToolbar'

vi.mock('../reading/ReadingControl', () => ({ ReadingControl: () => null }))
vi.mock('./PaperDetailsDialog', () => ({ PaperDetailsDialog: () => null }))
vi.mock('@/components/mode-toggle', () => ({ ModeToggle: () => null }))

it('shows the source chips in a row of their own on small screens, and in the header from md up', () => {
  const paper = { title: 'T', source_type: 'preprint', peer_reviewed: 'false', evidence_access: 'full_text' } as Paper
  render(<ReaderToolbar paper={paper} zoomIndex={0} onZoomChange={vi.fn()} capturing={false} onCaptureChange={vi.fn()} onOpenReferences={vi.fn()} />)
  const chips = screen.getAllByText('Full text')
  expect(chips).toHaveLength(2)
  expect(chips.some((c) => c.closest('.md\\:hidden'))).toBe(true)
  expect(chips.some((c) => c.closest('header'))).toBe(true)
  expect(screen.getAllByText('Preprint · not peer-reviewed')).toHaveLength(2)
})

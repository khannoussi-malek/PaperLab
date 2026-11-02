// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import type { Paper } from '@/api/client'
import { ReaderToolbar } from './ReaderToolbar'

vi.mock('../reading/ReadingControl', () => ({ ReadingControl: () => null }))
vi.mock('./PaperDetailsDialog', () => ({ PaperDetailsDialog: () => null }))
vi.mock('@/components/mode-toggle', () => ({ ModeToggle: () => null }))

const paper = (extra: Partial<Paper> = {}) =>
  ({ title: 'T', source_type: 'preprint', peer_reviewed: 'false', evidence_access: 'full_text', ...extra }) as Paper
const renderToolbar = (p: Paper, drawingFigure: boolean, onDrawingFigureChange: ((on: boolean) => void) | null = vi.fn()) =>
  render(
    <ReaderToolbar paper={p} zoomIndex={0} onZoomChange={vi.fn()} capturing={false} onCaptureChange={vi.fn()}
      drawingFigure={drawingFigure} onDrawingFigureChange={onDrawingFigureChange ?? undefined} onOpenReferences={vi.fn()} />,
  )

it('shows Note on figure with its pressed state and calls back with the opposite', () => {
  const change = vi.fn()
  renderToolbar(paper(), false, change)
  const toggle = screen.getByRole('button', { name: 'Note on figure' })
  expect(toggle).toHaveAttribute('aria-pressed', 'false')
  fireEvent.click(toggle)
  expect(change).toHaveBeenCalledWith(true)
})

it('shows it pressed while drawing', () => {
  renderToolbar(paper(), true)
  expect(screen.getByRole('button', { name: 'Note on figure' })).toHaveAttribute('aria-pressed', 'true')
})

it('hides it for a paper without a PDF', () => {
  renderToolbar(paper({ has_pdf: false }), false)
  expect(screen.queryByRole('button', { name: 'Note on figure' })).toBeNull()
})

it('hides it when nobody listens for it', () => {
  renderToolbar(paper(), false, null)
  expect(screen.queryByRole('button', { name: 'Note on figure' })).toBeNull()
})

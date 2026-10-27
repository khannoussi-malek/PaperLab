// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import type { Paper } from '@/api/client'
import { ReaderToolbar } from './ReaderToolbar'

vi.mock('../reading/ReadingControl', () => ({ ReadingControl: () => null }))
vi.mock('./PaperDetailsDialog', () => ({ PaperDetailsDialog: () => null }))
vi.mock('@/components/mode-toggle', () => ({ ModeToggle: () => null }))

const toolbar = (hasPdf: boolean) =>
  render(
    <ReaderToolbar
      paper={{ title: 'T', has_pdf: hasPdf, source_type: 'preprint', peer_reviewed: 'false', evidence_access: 'full_text' } as Paper}
      zoomIndex={0}
      onZoomChange={vi.fn()}
      capturing={false}
      onCaptureChange={vi.fn()}
      onOpenReferences={vi.fn()}
      lensControl={<span>lens picker</span>}
    />,
  )

it('shows the lens picker for a paper with a PDF', () => {
  toolbar(true)
  expect(screen.getByText('lens picker')).toBeTruthy()
})

it('does not render the lens picker when the paper has no PDF', () => {
  toolbar(false)
  expect(screen.queryByText('lens picker')).toBeNull()
})

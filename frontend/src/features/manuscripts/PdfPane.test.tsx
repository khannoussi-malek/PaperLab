// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react'
import { expect, test, vi } from 'vitest'
import type { ManuscriptDetail } from '@/api/client'
import { PdfPane } from './PdfPane'

vi.mock('../reader/usePdfDocument', () => ({ usePdfDocument: () => ({ doc: { numPages: 3 }, error: null }) }))
vi.mock('../reader/PdfPage', () => ({ PdfPage: () => null }))

const m = { id: 'm1', compile_status: 'ok', compiled_at: '2026-10-03T00:00:00Z', compile_errors: [], compile_friendly: null, compile_log: null } as unknown as ManuscriptDetail
const SCALE = (612 + 24 - 24) / 612 // width 636 -> scale 1

test('a target scrolls its point into the pane', () => {
  render(<PdfPane manuscript={m} width={636} target={{ page: 2, y: 300, n: 1 }} onSourceAt={() => {}} />)
  expect(screen.getByLabelText('PDF pages').scrollTop).toBe(300 * SCALE)
  expect(document.querySelector('[data-page="2"]')).not.toBeNull()
})

test('ctrl-click reports page and points (offset / scale)', () => {
  const at = vi.fn()
  render(<PdfPane manuscript={m} width={636} target={null} onSourceAt={at} />)
  fireEvent.click(document.querySelector('[data-page="3"]')!, { ctrlKey: true, clientX: 40, clientY: 90 })
  expect(at).toHaveBeenCalledWith(3, 40 / SCALE, 90 / SCALE)
  fireEvent.click(document.querySelector('[data-page="3"]')!)
  expect(at).toHaveBeenCalledTimes(1)
})

test('Enter on the pages uses the visible centre', () => {
  const at = vi.fn()
  render(<PdfPane manuscript={m} width={636} target={null} onSourceAt={at} />)
  fireEvent.keyDown(screen.getByLabelText('PDF pages'), { key: 'Enter' })
  expect(at).toHaveBeenCalledTimes(1)
})

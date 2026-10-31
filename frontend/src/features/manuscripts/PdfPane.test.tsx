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

const rect = (top: number, bottom: number) => ({ top, bottom, left: 0, right: 100, width: 100, height: bottom - top, x: 0, y: top, toJSON: () => ({}) }) as DOMRect

test('Enter in a gap between pages picks the nearest page', () => {
  const at = vi.fn()
  render(<PdfPane manuscript={m} width={636} target={null} onSourceAt={at} />)
  const box = screen.getByLabelText('PDF pages')
  Object.defineProperty(box, 'clientHeight', { value: 200, configurable: true })
  vi.spyOn(box, 'getBoundingClientRect').mockReturnValue(rect(0, 200))
  ;[[1, 0, 60], [2, 110, 300], [3, 310, 500]].forEach(([n, t, b]) =>
    vi.spyOn(document.querySelector(`[data-page="${n}"]`)!, 'getBoundingClientRect').mockReturnValue(rect(t, b)))
  fireEvent.keyDown(box, { key: 'Enter' }) // centre y = 100, between page 1 and page 2
  expect(at).toHaveBeenCalledWith(2, expect.any(Number), expect.any(Number))
})

test('the target is placed again when pages change size under it, until the user scrolls', () => {
  let fire = () => {}
  vi.stubGlobal('ResizeObserver', class { constructor(cb: () => void) { fire = cb } observe() {} disconnect() {} })
  render(<PdfPane manuscript={m} width={636} target={{ page: 2, y: 0, n: 1 }} onSourceAt={() => {}} />)
  const box = screen.getByLabelText('PDF pages')
  vi.spyOn(document.querySelector('[data-page="2"]')!, 'getBoundingClientRect').mockReturnValue(rect(1600, 2400)) // page 1 grew to A4
  fire()
  expect(box.scrollTop).toBe(1600)
  fireEvent.wheel(box)
  box.scrollTop = 5
  fire()
  expect(box.scrollTop).toBe(5)
  vi.unstubAllGlobals()
})

test('double-click reports the word, its page point and a rect', () => {
  const edit = vi.fn()
  vi.spyOn(window, 'getSelection').mockReturnValue({ toString: () => ' Dogs ', rangeCount: 0 } as unknown as Selection)
  render(<PdfPane manuscript={m} width={636} target={null} onSourceAt={() => {}} onEditAt={edit} />)
  fireEvent.doubleClick(document.querySelector('[data-page="2"]')!, { clientX: 40, clientY: 90 })
  expect(edit).toHaveBeenCalledWith(2, 40 / SCALE, 90 / SCALE, 'Dogs', expect.objectContaining({ left: 40, bottom: 90 }))
})

test('E on the pages opens the edit box at the visible centre, with no word', () => {
  const edit = vi.fn()
  const at = vi.fn()
  render(<PdfPane manuscript={m} width={636} target={null} onSourceAt={at} onEditAt={edit} />)
  const box = screen.getByLabelText('PDF pages')
  Object.defineProperty(box, 'clientHeight', { value: 200, configurable: true })
  vi.spyOn(box, 'getBoundingClientRect').mockReturnValue(rect(0, 200))
  ;[[1, -400, 60], [2, 90, 300], [3, 310, 500]].forEach(([n, t, b]) =>
    vi.spyOn(document.querySelector(`[data-page="${n}"]`)!, 'getBoundingClientRect').mockReturnValue(rect(t, b)))
  fireEvent.keyDown(box, { key: 'e', metaKey: true }) // not ours
  expect(edit).not.toHaveBeenCalled()
  fireEvent.keyDown(box, { key: 'e' }) // centre (50, 100) is 10 pt into page 2
  expect(edit).toHaveBeenCalledWith(2, 50 / SCALE, 10 / SCALE, '', expect.objectContaining({ left: 50, top: 100 }))
  expect(at).not.toHaveBeenCalled() // Enter stays "jump to source"
  fireEvent.keyDown(box, { key: 'Enter' })
  expect(at).toHaveBeenCalledWith(2, 50 / SCALE, 10 / SCALE)
})

test('the PDF an edit made keeps its scroll; any other new PDF goes back to the target', () => {
  const target = { page: 2, y: 300, n: 1 }
  const ui = (at: string, still: string | null) => (
    <PdfPane manuscript={{ ...m, compiled_at: at }} width={636} target={target} stillStamp={still} onSourceAt={() => {}} />
  )
  const view = render(ui('2026-10-03T00:00:00Z', null))
  const box = screen.getByLabelText('PDF pages')
  expect(box.scrollTop).toBe(300 * SCALE)
  fireEvent.wheel(box)
  box.scrollTop = 42
  view.rerender(ui('2026-10-04T00:00:00Z', '2026-10-04T00:00:00Z')) // the edit's compile: a new doc, same target
  expect(box.scrollTop).toBe(42)
  view.rerender(ui('2026-10-05T00:00:00Z', '2026-10-04T00:00:00Z')) // a later compile follows the target again
  expect(box.scrollTop).toBe(42 + 300 * SCALE) // jsdom rects are all 0, so placing adds the current scroll
})

test('a shown PDF can be downloaded from the pane, named after the manuscript', () => {
  render(<PdfPane manuscript={{ ...m, title: 'My Paper' } as ManuscriptDetail} width={636} target={null} onSourceAt={() => {}} />)
  const link = screen.getByRole('link', { name: 'Download PDF' })
  expect(link).toHaveAttribute('href', '/api/manuscripts/m1/pdf?v=2026-10-03T00%3A00%3A00Z')
  expect(link).toHaveAttribute('download', 'My Paper.pdf')
})

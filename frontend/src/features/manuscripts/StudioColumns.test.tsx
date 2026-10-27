// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react'
import { act } from '@testing-library/react'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import type { PanelLimits } from '@/components/panelWidth'
import { StudioColumns, type StudioColumn } from './StudioColumns'

const limits = (storageKey: string): PanelLimits => ({ storageKey, defaultWidth: 200, minWidth: 100, maxShare: 0.4 })
const columns: StudioColumn[] = [
  { id: 'sections', label: 'Sections', content: <button>one</button>, limits: limits('t-sections') },
  { id: 'editor', label: 'Editor', content: <button>two</button> },
  { id: 'pdf', label: 'PDF', content: <button>three</button>, limits: limits('t-pdf') },
]
beforeEach(() => localStorage.clear())

test('collapsing shows a rail with an expand button, and the choice is remembered', () => {
  const { unmount } = render(<StudioColumns columns={columns} />)
  fireEvent.click(screen.getByRole('button', { name: 'Collapse Sections' }))
  expect(screen.getByText('one')).not.toBeVisible()
  expect(screen.getByRole('button', { name: 'Expand Sections' })).toHaveAttribute('aria-expanded', 'false')
  unmount()
  render(<StudioColumns columns={columns} />)
  expect(screen.getByText('one')).not.toBeVisible() // restored
  fireEvent.click(screen.getByRole('button', { name: 'Expand Sections' }))
  expect(screen.getByText('one')).toBeVisible()
  expect(JSON.parse(localStorage.getItem('paperlab-studio-collapsed')!)).toEqual([])
})

test('F6 and Shift+F6 cycle the expanded regions and skip collapsed ones', () => {
  render(<StudioColumns columns={columns} />)
  fireEvent.click(screen.getByRole('button', { name: 'Collapse Editor' }))
  const region = (n: string) => screen.getByRole('region', { name: n })
  region('Sections').focus()
  fireEvent.keyDown(document, { key: 'F6' })
  expect(region('PDF')).toHaveFocus()
  fireEvent.keyDown(document, { key: 'F6' })
  expect(region('Sections')).toHaveFocus()
  fireEvent.keyDown(document, { key: 'F6', shiftKey: true })
  expect(region('PDF')).toHaveFocus()
})

test('F6 is left alone once the studio is gone', () => {
  const { unmount } = render(<StudioColumns columns={columns} />)
  unmount()
  const e = new KeyboardEvent('keydown', { key: 'F6', cancelable: true })
  document.dispatchEvent(e)
  expect(e.defaultPrevented).toBe(false)
})

const wide = window.innerWidth
const setWidth = (w: number) => act(() => { Object.defineProperty(window, 'innerWidth', { value: w, configurable: true }); window.dispatchEvent(new Event('resize')) })
afterEach(() => setWidth(wide))
const shared: StudioColumn[] = [
  { id: 'editor', label: 'Editor', content: <button>ed</button> },
  { id: 'pdf', label: 'PDF', content: <button>pdf page</button>, limits: limits('t-pdf'), shareWith: 'papers' },
  { id: 'papers', label: 'Papers', content: <button>deck</button>, limits: limits('t-papers') },
]

test('wide enough, the PDF and the papers are two columns', () => {
  setWidth(1400)
  render(<StudioColumns columns={shared} />)
  expect(screen.getByRole('region', { name: 'PDF' })).toBeInTheDocument()
  expect(screen.getByRole('region', { name: 'Papers' })).toBeInTheDocument()
  expect(screen.queryByRole('tab')).toBeNull()
})

test('under 1280 px they share one column as tabs, and the chosen tab is remembered', () => {
  setWidth(1000)
  const { unmount } = render(<StudioColumns columns={shared} />)
  expect(screen.getAllByRole('region')).toHaveLength(2)
  expect(screen.getByRole('tab', { name: 'PDF' })).toHaveAttribute('aria-selected', 'true')
  expect(screen.getByText('deck')).not.toBeVisible()
  fireEvent.click(screen.getByRole('tab', { name: 'Papers' }))
  expect(screen.getByText('deck')).toBeVisible()
  expect(screen.getByText('pdf page')).not.toBeVisible()
  unmount()
  render(<StudioColumns columns={shared} />)
  expect(screen.getByRole('tab', { name: 'Papers' })).toHaveAttribute('aria-selected', 'true')
})

test('crossing the breakpoint while open switches layout', () => {
  setWidth(1400)
  render(<StudioColumns columns={shared} />)
  setWidth(900)
  expect(screen.getByRole('tab', { name: 'Papers' })).toBeInTheDocument()
})

test('reveal opens the Papers tab', () => {
  setWidth(1000)
  const { rerender } = render(<StudioColumns columns={shared} />)
  rerender(<StudioColumns columns={shared} reveal={{ id: 'papers', n: 1 }} />)
  expect(screen.getByText('deck')).toBeVisible()
})

test('widening past the breakpoint keeps a valid grid (no undefined width)', () => {
  setWidth(1000)
  const { container } = render(<StudioColumns columns={shared} />)
  setWidth(1400)
  const template = (container.firstChild as HTMLElement).style.gridTemplateColumns
  expect(template).not.toBe('')
  expect(template).not.toContain('undefined')
})

test('revealing Papers on a wide screen leaves the PDF and the remembered tab alone', () => {
  setWidth(1400)
  localStorage.setItem('paperlab-studio-collapsed', JSON.stringify(['pdf', 'papers']))
  const { rerender } = render(<StudioColumns columns={shared} />)
  rerender(<StudioColumns columns={shared} reveal={{ id: 'papers', n: 1 }} />)
  expect(JSON.parse(localStorage.getItem('paperlab-studio-collapsed')!)).toEqual(['pdf'])
  expect(localStorage.getItem('paperlab-studio-tab')).not.toBe('papers')
})

// The studio's own width (not the window's) decides: a ResizeObserver on the grid, driven by hand here.
let measure: (w: number) => void
const measured = (container: number, inner = 1280) => {
  vi.stubGlobal('ResizeObserver', class { constructor(cb: (e: unknown[]) => void) { measure = (w) => act(() => cb([{ contentRect: { width: w } }])) } observe() {} unobserve() {} disconnect() {} })
  setWidth(inner)
  const view = render(<StudioColumns columns={sectioned} />)
  measure(container)
  return view
}
const sectioned: StudioColumn[] = [
  { id: 'sections', label: 'Sections', content: <button>nav</button>, limits: { storageKey: 'm-s', defaultWidth: 240, minWidth: 180, maxShare: 0.25 } },
  { id: 'editor', label: 'Editor', content: <button>ed</button> },
  { id: 'pdf', label: 'PDF', content: <button>pdf page</button>, limits: { storageKey: 'm-p', defaultWidth: 520, minWidth: 360, maxShare: 0.6 }, shareWith: 'papers' },
  { id: 'papers', label: 'Papers', content: <button>deck</button>, limits: { storageKey: 'm-k', defaultWidth: 320, minWidth: 260, maxShare: 0.3 } },
]
const grid = (c: HTMLElement) => (c.firstChild as HTMLElement).style.gridTemplateColumns
afterEach(() => vi.unstubAllGlobals())

test('a 1044 px studio cannot fit all four columns plus a 420 px editor: PDF and Papers share, the editor flexes', () => {
  const { container } = measured(1044, 1280) // a 1280 window, so the old window rule would have said "wide"
  expect(screen.getByRole('tab', { name: 'Papers' })).toBeInTheDocument()
  expect(grid(container)).toContain('minmax(0,1fr)')
  expect(grid(container)).not.toContain('420px')
})

test('a 1500 px studio shows four columns, the editor never under 420 px', () => {
  const { container } = measured(1500, 1500)
  expect(screen.queryByRole('tab')).toBeNull()
  expect(screen.getAllByRole('region')).toHaveLength(4)
  expect(grid(container)).toContain('minmax(420px,1fr)')
})

test('collapsing Sections frees only 208 px: at 1044 the rest still needs more than that, at 1300 it fits', () => {
  measured(1044, 1280)
  fireEvent.click(screen.getByRole('button', { name: 'Collapse Sections' }))
  // 32 rail + 520 + 320 + 420 = 1292 > 1044: still shared
  expect(screen.getByRole('tab', { name: 'Papers' })).toBeInTheDocument()
  measure(1300) // 1292 <= 1300: now four columns
  expect(screen.queryByRole('tab')).toBeNull() // (the grid string is not asserted: jsdom drops a template with a rail in it)
  expect(screen.getAllByRole('region')).toHaveLength(3)
})
